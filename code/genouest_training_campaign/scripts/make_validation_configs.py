#!/usr/bin/env python3
"""Create post-fit validation/baseline configurations, marking training leakage."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path


def load(path):
    with open(path,newline="") as f:return list(csv.DictReader(f))

def add(selected,reasons,r,why):
    if r and r["config_id"] not in {x["config_id"] for x in selected}:
        selected.append(r); reasons[r["config_id"]]=why

def nearest(rows,b,g):
    return min(rows,key=lambda r:abs(float(r["base"])-b)*20+abs(float(r["groups"])-g))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("design_csv")
    ap.add_argument("recommendation_json")
    ap.add_argument("--training-csv",default="")
    ap.add_argument("--ranked-csv",default="")
    ap.add_argument("--unseen-top",type=int,default=3)
    ap.add_argument("--old-ble",default="",help="BASE:GROUPS")
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    rows=load(args.design_csv); byid={r["config_id"]:r for r in rows}; rec=json.load(open(args.recommendation_json))
    train_ids={r["config_id"] for r in load(args.training_csv)} if args.training_csv else set()
    sel=[]; reasons={}
    add(sel,reasons,byid.get(rec["config_id"]),"model-recommendation")
    if args.ranked_csv:
        unseen=0
        for r in load(args.ranked_csv):
            if r["config_id"] not in train_ids:
                add(sel,reasons,byid[r["config_id"]],"top-ranked-unseen")
                unseen += 1
                if unseen >= args.unseen_top: break
    add(sel,reasons,min(rows,key=lambda r:float(r["total_size_bytes"])),"minimum-total-storage")
    add(sel,reasons,min(rows,key=lambda r:float(r["max_group_size_bytes"])),"minimum-max-group")
    add(sel,reasons,nearest(rows,1.1,1),"one-group-baseline")
    add(sel,reasons,nearest(rows,1.1,20),"kmhelpers-default-like")
    nat=[r for r in rows if abs(float(r["base"])-1.1)<1e-9 and "natural" in r.get("kind","")]
    if nat:add(sel,reasons,nat[0],"natural-no-merge")
    if args.old_ble:
        b,g=args.old_ble.split(":",1);add(sel,reasons,nearest(rows,float(b),int(g)),"legacy-BLE-best")
    fields=list(sel[0].keys())+["validation_reason","seen_in_training"]
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    with open(out,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in sel:w.writerow({**r,"validation_reason":reasons[r["config_id"]],"seen_in_training":"yes" if r["config_id"] in train_ids else "no"})
    print(f"validation_configs={len(sel)} unseen={sum(r['config_id'] not in train_ids for r in sel)}")
    print(out)
if __name__=="__main__":main()
