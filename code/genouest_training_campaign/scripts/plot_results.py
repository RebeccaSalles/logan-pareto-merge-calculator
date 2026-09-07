#!/usr/bin/env python3
"""Generate paper-ready diagnostic figures and compact summary tables."""
from __future__ import annotations
import argparse,csv,json,statistics
from collections import defaultdict
from pathlib import Path
import matplotlib.pyplot as plt


def read_csv(path):
    with open(path,newline="") as f:return list(csv.DictReader(f))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("design_csv")
    ap.add_argument("aggregated_timings_csv")
    ap.add_argument("training_predictions_csv")
    ap.add_argument("--output-dir",required=True)
    args=ap.parse_args(); out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    designs=read_csv(args.design_csv); agg=read_csv(args.aggregated_timings_csv); pred=read_csv(args.training_predictions_csv)

    # Figure 1: storage landscape.
    bybase=defaultdict(list)
    for r in designs:
        if r.get("kind")=="natural": continue
        bybase[float(r["base"])].append((int(float(r["groups"])),float(r["total_size_bytes"])/1e12))
    plt.figure(figsize=(8,5))
    for b,vals in sorted(bybase.items()):
        vals=sorted(set(vals));plt.plot([x for x,_ in vals],[y for _,y in vals],marker="o",markersize=3,label=f"b={b:g}")
    plt.xlabel("Number of groups");plt.ylabel("Estimated grouped storage (TB)");plt.legend(ncol=3,fontsize=7);plt.tight_layout();plt.savefig(out/"fig_storage_landscape.pdf");plt.close()

    # Figure 2: observed vs model predicted.
    plt.figure(figsize=(6,6))
    xs=[float(r["elapsed_seconds"]) for r in pred];ys=[float(r["predicted_seconds"]) for r in pred]
    plt.scatter(xs,ys);lo=min(xs+ys);hi=max(xs+ys);plt.plot([lo,hi],[lo,hi],linestyle="--")
    plt.xlabel("Observed median query time (s)");plt.ylabel("Predicted query time (s)");plt.tight_layout();plt.savefig(out/"fig_observed_vs_predicted.pdf");plt.close()

    # Figure 3: empirical storage/time tradeoff for primary 1000 bp workload when present.
    lengths=sorted({int(r["query_length"]) for r in agg});primary=1000 if 1000 in lengths else lengths[-1]
    rr=[r for r in agg if int(r["query_length"])==primary]
    plt.figure(figsize=(7,5))
    plt.scatter([float(r["total_size_tb"]) for r in rr],[float(r["elapsed_seconds"]) for r in rr])
    for r in rr: plt.annotate(r["config_id"],(float(r["total_size_tb"]),float(r["elapsed_seconds"])),fontsize=6)
    plt.xlabel("Estimated grouped storage (TB)");plt.ylabel(f"Median query time, {primary} bp (s)");plt.tight_layout();plt.savefig(out/"fig_storage_vs_query_time.pdf");plt.close()

    # Figure 4: query-length scaling, one line per config.
    bycfg=defaultdict(list)
    for r in agg: bycfg[r["config_id"]].append((int(r["query_length"]),float(r["elapsed_seconds"])))
    plt.figure(figsize=(7,5))
    for cid,vals in sorted(bycfg.items()):
        vals=sorted(vals);plt.plot([x for x,_ in vals],[y for _,y in vals],marker="o",label=cid)
    plt.xlabel("Query length (bp)");plt.ylabel("Median query time (s)")
    if len(bycfg)<=12:plt.legend(fontsize=6,ncol=2)
    plt.tight_layout();plt.savefig(out/"fig_query_length_scaling.pdf");plt.close()
    print(out)
if __name__=="__main__":main()
