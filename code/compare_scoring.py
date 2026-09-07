#!/usr/bin/env python3
"""Compare two score_designs.py CSV outputs (e.g. the shipped nb_partitions
formula vs. an alternate one) and summarize what actually changed --
built for reviewing whether a different partition-bytes/cap/rounding
choice would have changed any real conclusion, not just the raw numbers.

Usage:
    python3 compare_scoring.py BASELINE.csv ALTERNATE.csv [--budget-gb 2000]

Reports, per query length (250/500/1000bp):
  - how many designs' score changed at all, and by how much (median/max % change)
  - whether the single best (lowest-score) design changed
  - whether the Pareto frontier (storage vs. score) membership changed,
    and by how many designs
  - if --budget-gb is given: whether the recommended design at that
    storage budget changed
"""
import argparse
import csv


def load(path):
    with open(path, newline="") as fh:
        return {row["id"]: row for row in csv.DictReader(fh)}


def frontier(rows, score_key):
    ordered = sorted(rows.values(), key=lambda r: float(r["s"]))
    best = float("inf")
    ids = set()
    for r in ordered:
        sc = float(r[score_key])
        if sc < best:
            ids.add(r["id"])
            best = sc
    return ids


def recommend(rows, score_key, budget_gb):
    candidates = [r for r in rows.values() if float(r["s"]) <= budget_gb]
    if not candidates:
        return None
    return min(candidates, key=lambda r: float(r[score_key]))["id"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("baseline_csv")
    ap.add_argument("alternate_csv")
    ap.add_argument("--budget-gb", type=float, default=None, help="also compare the budget-constrained recommendation at this storage budget (GB)")
    args = ap.parse_args()

    base = load(args.baseline_csv)
    alt = load(args.alternate_csv)
    common = sorted(set(base) & set(alt))
    if set(base) != set(alt):
        print(f"WARNING: design sets differ ({len(base)} vs {len(alt)} rows); comparing the {len(common)} shared ids only")

    for L in (250, 500, 1000):
        key = f"score{L}"
        deltas = []
        changed = 0
        for i in common:
            b, a = float(base[i][key]), float(alt[i][key])
            if b != a:
                changed += 1
            deltas.append(abs(a - b) / b * 100 if b else 0.0)
        deltas.sort()
        med = deltas[len(deltas) // 2] if deltas else 0.0
        mx = deltas[-1] if deltas else 0.0

        b_best = min(common, key=lambda i: float(base[i][key]))
        a_best = min(common, key=lambda i: float(alt[i][key]))

        b_front = frontier({i: base[i] for i in common}, key)
        a_front = frontier({i: alt[i] for i in common}, key)

        print(f"--- {L}bp ---")
        print(f"  scores changed: {changed} / {len(common)} designs (median |Δ|={med:.1f}%, max |Δ|={mx:.1f}%)")
        print(f"  single best design: {b_best} -> {a_best} {'(SAME)' if b_best == a_best else '(CHANGED)'}")
        print(f"  Pareto frontier size: {len(b_front)} -> {len(a_front)}; "
              f"{len(b_front - a_front)} dropped, {len(a_front - b_front)} added")
        if args.budget_gb is not None:
            b_rec = recommend({i: base[i] for i in common}, key, args.budget_gb)
            a_rec = recommend({i: alt[i] for i in common}, key, args.budget_gb)
            print(f"  recommended @ {args.budget_gb:.0f}GB budget: {b_rec} -> {a_rec} "
                  f"{'(SAME)' if b_rec == a_rec else '(CHANGED)'}")
        print()


if __name__ == "__main__":
    main()
