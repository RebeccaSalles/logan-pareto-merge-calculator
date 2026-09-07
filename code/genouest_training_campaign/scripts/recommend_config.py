#!/usr/bin/env python3
"""Rank unbuilt designs using a fitted query-cost model and storage constraints."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path


def pareto(rows):
    out=[]
    for r in rows:
        dominated=False
        for q in rows:
            if q is r: continue
            if (q["predicted_seconds"] <= r["predicted_seconds"] and q["total_size_bytes"] <= r["total_size_bytes"] and
                (q["predicted_seconds"] < r["predicted_seconds"] or q["total_size_bytes"] < r["total_size_bytes"])):
                dominated=True; break
        if not dominated: out.append(r)
    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("design_csv")
    ap.add_argument("model_json")
    ap.add_argument("--query-length",type=int,default=1000)
    ap.add_argument("--max-total-bytes",type=float,default=float("inf"))
    ap.add_argument("--max-max-group-bytes",type=float,default=float("inf"))
    ap.add_argument("--output-dir",required=True)
    args=ap.parse_args()
    models=json.load(open(args.model_json)); m=models.get(str(args.query_length))
    if not m: raise SystemExit(f"no model for query length {args.query_length}")
    c=m["coefficients"]
    rows=[]
    with open(args.design_csv,newline="") as f:
        for r in csv.DictReader(f):
            total=float(r["total_size_bytes"]); mx=float(r["max_group_size_bytes"]); g=float(r["groups"])
            if total>args.max_total_bytes or mx>args.max_max_group_bytes: continue
            pred=(c["intercept_s"]+c["a_groups_s_per_group"]*g+c["b_total_s_per_TB"]*(total/1e12)+c["c_max_group_s_per_TB"]*(mx/1e12))
            rr=dict(r); rr["predicted_seconds"]=pred; rr["pareto_time_storage"]=""; rows.append(rr)
    if not rows: raise SystemExit("no feasible designs")
    rows.sort(key=lambda r:r["predicted_seconds"])
    pf={r["config_id"] for r in pareto(rows)}
    for rank,r in enumerate(rows,1):
        r["rank"]=rank; r["pareto_time_storage"]="yes" if r["config_id"] in pf else "no"
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0].keys())
    with open(out/"ranked_configs.csv","w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    best=rows[0]
    rec={"query_length":args.query_length,"config_id":best["config_id"],"base":float(best["base"]),"groups":int(float(best["groups"])),"predicted_seconds":float(best["predicted_seconds"]),"total_size_bytes":int(float(best["total_size_bytes"])),"max_group_size_bytes":int(float(best["max_group_size_bytes"])),"model":m}
    with open(out/"recommendation.json","w") as f: json.dump(rec,f,indent=2)
    print(json.dumps(rec,indent=2))

if __name__=="__main__": main()
