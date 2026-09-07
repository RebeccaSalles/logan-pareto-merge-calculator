#!/usr/bin/env python3
"""Evaluate a frozen training model on validation-phase timing data."""
from __future__ import annotations
import argparse,csv,json,statistics
from collections import defaultdict
from pathlib import Path

ap=argparse.ArgumentParser();ap.add_argument("timings_csv");ap.add_argument("model_json");ap.add_argument("--output",required=True);args=ap.parse_args()
models=json.load(open(args.model_json));vals=defaultdict(list);meta={}
with open(args.timings_csv,newline="") as f:
    for r in csv.DictReader(f):
        if r.get("phase")!="validation":continue
        key=(r["config_id"],int(r["query_length"]));vals[key].append(float(r["elapsed_seconds"]));meta[key]=r
rows=[]
for key,times in vals.items():
    cid,L=key
    if str(L) not in models:continue
    r=meta[key];c=models[str(L)]["coefficients"]
    g=float(r["groups"]);S=float(r["estimated_total_bytes"])/1e12;M=float(r["estimated_max_group_bytes"])/1e12
    obs=statistics.median(times);pred=c["intercept_s"]+c["a_groups_s_per_group"]*g+c["b_total_s_per_TB"]*S+c["c_max_group_s_per_TB"]*M
    rows.append({"config_id":cid,"query_length":L,"observed_seconds":obs,"predicted_seconds":pred,"absolute_error_seconds":abs(obs-pred),"relative_error":abs(obs-pred)/obs if obs else 0,"n_runs":len(times)})
out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
if rows:
    with open(out,"w",newline="") as f:
        fields=list(rows[0]);w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    print(f"validation_points={len(rows)} median_relative_error={statistics.median(r['relative_error'] for r in rows):.4f}")
else:
    print("no validation rows")
