#!/usr/bin/env python3
"""Select a compact anchor set for the multi-query-length extension."""
import argparse,csv,json
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument("design_csv");ap.add_argument("recommendation_json");ap.add_argument("--output",required=True);args=ap.parse_args()
with open(args.design_csv,newline="") as f: rows=list(csv.DictReader(f))
rec=json.load(open(args.recommendation_json));byid={r["config_id"]:r for r in rows};sel=[];reason={}
def add(r,w):
    if r and r["config_id"] not in {x["config_id"] for x in sel}:sel.append(r);reason[r["config_id"]]=w
def near(b,g):return min(rows,key=lambda r:abs(float(r["base"])-b)*20+abs(float(r["groups"])-g))
add(byid.get(rec["config_id"]),"recommendation")
add(near(1.1,1),"one-group")
add(near(1.1,20),"kmhelpers-default-like")
add(max(rows,key=lambda r:float(r["groups"])),"many-groups")
fields=list(sel[0])+["extension_reason"];out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
with open(out,"w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for r in sel:w.writerow({**r,"extension_reason":reason[r["config_id"]]})
print(out)
