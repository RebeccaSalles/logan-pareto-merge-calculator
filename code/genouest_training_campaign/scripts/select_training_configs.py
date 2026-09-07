#!/usr/bin/env python3
"""Select a storage-feasible, diverse set of configurations for expensive builds."""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


def load(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("base", "groups", "natural_spans", "total_size_bytes", "max_group_size_bytes", "group_size_cv"):
            r[k] = float(r[k])
    return rows


def dist(a, b, mins, maxs):
    keys = ("base", "groups", "total_size_bytes", "max_group_size_bytes")
    s = 0.0
    for k in keys:
        den = maxs[k] - mins[k]
        x = 0.0 if den == 0 else (a[k] - b[k]) / den
        s += x * x
    return math.sqrt(s)


def key_bg(r):
    return (round(r["base"], 9), int(r["groups"]))


def nearest(rows, base, groups):
    return min(rows, key=lambda r: abs(r["base"] - base) * 20.0 + abs(r["groups"] - groups))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("design_csv")
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--max-estimated-bytes", type=float, default=float("inf"))
    ap.add_argument("--manual", action="append", default=[], help="manual baseline as BASE:GROUPS; repeatable")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    all_rows = load(args.design_csv)
    rows = [r for r in all_rows if r["total_size_bytes"] <= args.max_estimated_bytes]
    if not rows:
        raise SystemExit("no design fits --max-estimated-bytes")

    selected = []
    reasons = {}
    def add(r, reason):
        k = key_bg(r)
        if k not in {key_bg(x) for x in selected}:
            selected.append(r)
            reasons[k] = reason

    add(min(rows, key=lambda r: r["total_size_bytes"]), "minimum-total-storage")
    add(min(rows, key=lambda r: r["max_group_size_bytes"]), "minimum-max-group")
    add(nearest(rows, 1.1, 1), "one-group-baseline")
    add(nearest(rows, 1.1, 20), "kmhelpers-default-like")
    add(max(rows, key=lambda r: r["groups"]), "many-groups-anchor")
    for spec in args.manual:
        b, g = spec.split(":", 1)
        add(nearest(rows, float(b), int(g)), f"manual-{spec}")

    mins = {k: min(r[k] for r in rows) for k in ("base", "groups", "total_size_bytes", "max_group_size_bytes")}
    maxs = {k: max(r[k] for r in rows) for k in mins}
    while len(selected) < min(args.n, len(rows)):
        candidates = [r for r in rows if key_bg(r) not in {key_bg(x) for x in selected}]
        best = max(candidates, key=lambda r: min(dist(r, s, mins, maxs) for s in selected))
        add(best, "farthest-point-design")

    fields = list(csv.DictReader(open(args.design_csv)).fieldnames or []) + ["selection_reason"]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in selected:
            rr = {k: r.get(k, "") for k in fields}
            # Restore integer-looking fields for readability.
            for k in ("groups", "natural_spans"):
                if k in rr and rr[k] != "":
                    rr[k] = int(float(rr[k]))
            rr["selection_reason"] = reasons[key_bg(r)]
            w.writerow(rr)
    print(f"selected={len(selected)}")
    print(f"output={out}")


if __name__ == "__main__":
    main()
