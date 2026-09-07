#!/usr/bin/env python3
"""Suggest a conservative BUILD_SPACE_FACTOR from observed build peaks."""
import argparse,csv,math
ap=argparse.ArgumentParser();ap.add_argument("builds_csv");ap.add_argument("--margin",type=float,default=1.25);args=ap.parse_args()
vals=[]
with open(args.builds_csv,newline="") as f:
    for r in csv.DictReader(f):
        try: vals.append(float(r["peak_to_estimated_factor"]))
        except (KeyError,ValueError): pass
if not vals: raise SystemExit("no peak_to_estimated_factor values")
mx=max(vals); suggested=max(1.0,mx*args.margin)
print(f"observed_max_peak_factor={mx:.4f}")
print(f"margin={args.margin:.3f}")
print(f"suggested_BUILD_SPACE_FACTOR={suggested:.4f}")
