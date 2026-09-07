#!/usr/bin/env python3
"""Fit the query-cost model T = d + a*G + b*S + c*M.

S and M are design-time storage estimates in decimal TB. The fitted coefficients
for G/S/M are constrained non-negative for physical interpretability; the
intercept is unconstrained. One model is fitted per query length.

--reps controls which repeat(s) of each query feed the fit. Default "1"
(cold only): there is no active cache-eviction (config.env's
CACHE_DROP_CMD is empty -- root access to drop OS page cache generally
isn't available on this cluster), so within a real run the first repeat
of a given query against a freshly-touched index is a natural cold read,
and later repeats are naturally warm from OS filesystem cache. For a
broad, low-concurrency search tool where most real users are not relying
on someone else's very-recent query to have warmed the exact same
Bloom-filter files, a single cold read is the more representative
real-world case, not an average across cold+warm. Pass "--reps all" for
the previous behavior (median across every repeat, which -- with the
typical 1-cold/2-warm split -- was implicitly warm-leaning), or e.g.
"--reps 2,3" to fit a dedicated warm-cache comparison model. This needs
no new data collection: every repeat's `elapsed_seconds` is already
recorded per-row in the timings CSV.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import lsq_linear

FEATURES = ["groups", "total_size_tb", "max_group_size_tb"]


def parse_reps(spec: str) -> set[int] | None:
    """"1" -> {1}; "2,3" -> {2,3}; "all" -> None (no filtering)."""
    if spec.strip().lower() == "all":
        return None
    return {int(x) for x in spec.split(",") if x.strip()}


def load_aggregated(path: str, phase: str | None = "training", reps: set[int] | None = None):
    raw = defaultdict(list)
    meta = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if phase and "phase" in r and r.get("phase") != phase:
                continue
            if reps is not None and int(r["repeat"]) not in reps:
                continue
            key = (r["config_id"], int(r["query_length"]))
            raw[key].append(float(r["elapsed_seconds"]))
            meta[key] = {
                "config_id": r["config_id"],
                "query_length": int(r["query_length"]),
                "groups": float(r["groups"]),
                "total_size_tb": float(r["estimated_total_bytes"]) / 1e12,
                "max_group_size_tb": float(r["estimated_max_group_bytes"]) / 1e12,
                "base": float(r["base"]),
            }
    rows = []
    for key, vals in raw.items():
        r = dict(meta[key])
        r["elapsed_seconds"] = statistics.median(vals)
        r["n_runs"] = len(vals)
        r["run_mad_seconds"] = statistics.median([abs(v - r["elapsed_seconds"]) for v in vals])
        rows.append(r)
    return sorted(rows, key=lambda r: (r["query_length"], r["config_id"]))


def design_matrix(rows):
    X = np.array([[1.0, r["groups"], r["total_size_tb"], r["max_group_size_tb"]] for r in rows], dtype=float)
    y = np.array([r["elapsed_seconds"] for r in rows], dtype=float)
    return X, y


def fit_constrained(X, y):
    lb = np.array([-np.inf, 0.0, 0.0, 0.0])
    ub = np.array([ np.inf, np.inf, np.inf, np.inf])
    return lsq_linear(X, y, bounds=(lb, ub), method="trf").x


def metrics(y, p):
    err = y - p
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    denom = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - float(np.sum(err ** 2)) / denom if denom else 0.0
    return mae, rmse, r2


def loo(rows):
    if len(rows) <= 4:
        return float("nan"), float("nan")
    actual=[]; pred=[]
    for i in range(len(rows)):
        train = rows[:i] + rows[i+1:]
        X, y = design_matrix(train)
        coef = fit_constrained(X, y)
        xi = np.array([1.0, rows[i]["groups"], rows[i]["total_size_tb"], rows[i]["max_group_size_tb"]])
        actual.append(rows[i]["elapsed_seconds"])
        pred.append(float(xi @ coef))
    a=np.array(actual); p=np.array(pred)
    return float(np.mean(np.abs(a-p))), float(np.sqrt(np.mean((a-p)**2)))


def bootstrap(rows, n, seed):
    if len(rows) < 5 or n <= 0:
        return None
    rng=np.random.default_rng(seed)
    coefs=[]
    for _ in range(n):
        idx=rng.integers(0, len(rows), size=len(rows))
        sample=[rows[int(i)] for i in idx]
        X,y=design_matrix(sample)
        try:
            coefs.append(fit_constrained(X,y))
        except Exception:
            pass
    if not coefs:
        return None
    a=np.vstack(coefs)
    return np.percentile(a, [2.5,50,97.5], axis=0)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("timings_csv")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--phase", default="training")
    ap.add_argument("--seed", type=int, default=20260818)
    ap.add_argument("--reps", default="1",
                     help="Which repeat(s) to fit on: '1' (default, cold-only -- "
                          "see module docstring), a comma-separated list e.g. "
                          "'2,3' (warm-cache comparison), or 'all' (previous "
                          "behavior, median across every repeat).")
    args=ap.parse_args()
    reps=parse_reps(args.reps)
    rows=load_aggregated(args.timings_csv, args.phase, reps)
    if not rows:
        raise SystemExit("no timing rows")
    out=Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)

    agg_fields=["config_id","query_length","base","groups","total_size_tb","max_group_size_tb","elapsed_seconds","n_runs","run_mad_seconds"]
    with open(out/"aggregated_timings.csv","w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=agg_fields); w.writeheader(); w.writerows(rows)

    models={}
    coef_rows=[]; metric_rows=[]; pred_rows=[]
    for L in sorted({r["query_length"] for r in rows}):
        rr=[r for r in rows if r["query_length"]==L]
        if len(rr) < 4:
            print(f"skip L={L}: need at least 4 configurations")
            continue
        X,y=design_matrix(rr)
        coef=fit_constrained(X,y)
        p=X@coef
        mae,rmse,r2=metrics(y,p)
        loo_mae,loo_rmse=loo(rr)
        cond=float(np.linalg.cond(X))
        ci=bootstrap(rr,args.bootstrap,args.seed+L)
        names=["intercept_s","a_groups_s_per_group","b_total_s_per_TB","c_max_group_s_per_TB"]
        model={"query_length":L,"features":FEATURES,"reps_used":args.reps,"coefficients":dict(zip(names,map(float,coef))),"n_configs":len(rr),"mae_s":mae,"rmse_s":rmse,"r2":r2,"loo_mae_s":loo_mae,"loo_rmse_s":loo_rmse,"condition_number":cond}
        if ci is not None:
            model["bootstrap_95pct"]={name:{"low":float(ci[0,i]),"median":float(ci[1,i]),"high":float(ci[2,i])} for i,name in enumerate(names)}
        models[str(L)]=model
        for i,name in enumerate(names):
            coef_rows.append({"query_length":L,"coefficient":name,"value":float(coef[i]),"ci_low":float(ci[0,i]) if ci is not None else "","ci_high":float(ci[2,i]) if ci is not None else ""})
        metric_rows.append({k:model[k] for k in ("query_length","n_configs","mae_s","rmse_s","r2","loo_mae_s","loo_rmse_s","condition_number")})
        for r,pp in zip(rr,p):
            pred_rows.append({**r,"predicted_seconds":float(pp),"residual_seconds":float(r["elapsed_seconds"]-pp)})

    with open(out/"cost_models.json","w") as f: json.dump(models,f,indent=2)
    with open(out/"coefficients.csv","w",newline="") as f:
        fields=["query_length","coefficient","value","ci_low","ci_high"]; w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(coef_rows)
    with open(out/"model_metrics.csv","w",newline="") as f:
        fields=["query_length","n_configs","mae_s","rmse_s","r2","loo_mae_s","loo_rmse_s","condition_number"]; w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(metric_rows)
    if pred_rows:
        with open(out/"training_predictions.csv","w",newline="") as f:
            fields=list(pred_rows[0].keys()); w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(pred_rows)
    print(out/"cost_models.json")

if __name__=="__main__": main()
