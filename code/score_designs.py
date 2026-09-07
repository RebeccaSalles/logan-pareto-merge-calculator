#!/usr/bin/env python3
"""Score real enumerate_designs.py output (a CSV of candidate (base,
groups) designs, one row per design, with a `group_sizes_bytes` column
listing every group's real on-disk byte size) by estimated query cost.

    score(design, L) = sum_g min( nb_partitions(S_g), M(L) )

  S_g            = group g's real storage size, from kmhelpers profile
                   (the `group_sizes_bytes` column, semicolon-separated)
  nb_partitions  = kmhelpers' own real per-group partition-count formula
                   as shipped:
                     raw = 1 + group_bytes / 4_294_967_296   # 4GB/partition
                     nb_partitions = clamp(round_up_to_pow2(raw), 4, 256)
  M(L)           = distinct kmtricks minimizers in a query of length L --
                   see compute_minimizer_M.py. Shipped defaults (26/54/112
                   at 250/500/1000bp) are k=25,m=10 values computed against
                   this repo's data/query_examples/*.fa.

--- Testing alternate nb_partitions assumptions --------------------------

Every constant in the nb_partitions formula is a CLI flag, not a hardcoded
value, specifically so the formula can be re-checked:

    --partition-bytes N   bytes per partition (shipped: 4294967296 = 4GiB)
    --min-partitions N    floor on partitions/group (shipped: 4)
    --max-partitions N    cap on partitions/group  (shipped: 256)
    --rounding {pow2,ceil,nearest}
                           how `raw` is rounded to an integer partition
                           count before clamping (shipped: pow2 -- kmhelpers'
                           own compose formula rounds UP to the next power
                           of two; `ceil`/`nearest` are here specifically so
                           that assumption itself can be tested, not just
                           the byte/cap constants)

Example -- test doubling the per-partition byte size:

    python3 score_designs.py data/full_logan/design_space_full_logan.csv \\
        out/alt_8gb --partition-bytes 8589934592

Then diff out/alt_8gb.csv against data/full_logan/scored_designs_full_logan.csv,
or use compare_scoring.py to summarize what changed.

Nothing here is a re-implementation of kmhelpers' own math beyond this
one documented, source-verified formula -- group sizes come from real
`kmhelpers profile` calls (enumerate_designs.py), not a hand-rolled model.
The formula's *constants* are exactly what's being tested here, though --
that's the point.

Usage:
    python3 score_designs.py INPUT.csv OUT_PREFIX [--m250 26] [--m500 54] [--m1000 112]
                              [--partition-bytes N] [--min-partitions N]
                              [--max-partitions N] [--rounding {pow2,ceil,nearest}]

Writes OUT_PREFIX.json (embeddable in the report -- includes each
design's raw per-group byte list, `gb`, so the report's own "formula
sandbox" can recompute this same thing live in the browser) and
OUT_PREFIX.csv (flat, spreadsheet-friendly, summary fields only).
"""
import argparse
import csv
import json
import math


def round_up_pow2(x: float) -> int:
    if x <= 1:
        return 1
    return 1 << (int(x - 1)).bit_length()


def round_value(raw: float, rounding: str) -> int:
    if rounding == "pow2":
        return round_up_pow2(raw)
    if rounding == "ceil":
        return max(1, math.ceil(raw))
    if rounding == "nearest":
        return max(1, round(raw))
    raise ValueError(f"unknown --rounding {rounding!r}")


def nb_partitions(group_bytes: float, partition_bytes: float, min_p: int, max_p: int, rounding: str) -> int:
    raw = 1 + group_bytes / partition_bytes
    return max(min_p, min(max_p, round_value(raw, rounding)))


def score_csv(path_in: str, m_by_length: dict, partition_bytes: float, min_p: int, max_p: int, rounding: str) -> list:
    rows = []
    with open(path_in, newline="") as fh:
        for row in csv.DictReader(fh):
            sizes = [float(x) for x in row["group_sizes_bytes"].split(";") if x]
            if not sizes:
                continue
            parts = [nb_partitions(s, partition_bytes, min_p, max_p, rounding) for s in sizes]
            total_gb = float(row["total_size_bytes"]) / 1e9
            max_gb = float(row["max_group_size_bytes"]) / 1e9
            out = {
                "id": row["config_id"],
                "b": float(row["base"]),
                "g": int(row["groups"]),
                "s": round(total_gb, 1),
                "m": round(max_gb, 1),
                "np_min": min(parts),
                "np_max": max(parts),
                "kind": row["kind"],
                "gb": [round(x, 1) for x in sizes],  # raw per-group bytes, for the report's live formula sandbox
            }
            for length, cap in m_by_length.items():
                out[f"score{length}"] = sum(min(p, cap) for p in parts)
            rows.append(out)
    rows.sort(key=lambda d: (d["b"], d["g"]))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_csv", help="enumerate_designs.py output CSV")
    ap.add_argument("out_prefix", help="writes <out_prefix>.json and <out_prefix>.csv")
    ap.add_argument("--m250", type=int, default=26, help="M(250bp) minimizer cap")
    ap.add_argument("--m500", type=int, default=54, help="M(500bp) minimizer cap")
    ap.add_argument("--m1000", type=int, default=112, help="M(1000bp) minimizer cap")
    ap.add_argument("--partition-bytes", type=float, default=4_294_967_296, help="bytes per partition (shipped: 4GiB)")
    ap.add_argument("--min-partitions", type=int, default=4, help="floor on partitions/group (shipped: 4)")
    ap.add_argument("--max-partitions", type=int, default=256, help="cap on partitions/group (shipped: 256)")
    ap.add_argument("--rounding", choices=["pow2", "ceil", "nearest"], default="pow2",
                     help="how the raw partition count is rounded before clamping (shipped: pow2)")
    ap.add_argument("--no-groups", action="store_true", help="omit the raw per-group byte list ('gb') from the JSON, for a smaller file")
    args = ap.parse_args()

    m_by_length = {250: args.m250, 500: args.m500, 1000: args.m1000}
    rows = score_csv(args.input_csv, m_by_length, args.partition_bytes, args.min_partitions, args.max_partitions, args.rounding)
    if not rows:
        raise SystemExit("no designs scored -- empty or malformed input CSV")
    if args.no_groups:
        for r in rows:
            del r["gb"]

    json_path = f"{args.out_prefix}.json"
    with open(json_path, "w") as fh:
        json.dump(rows, fh, separators=(",", ":"))

    csv_path = f"{args.out_prefix}.csv"
    fields = ["id", "b", "g", "s", "m", "np_min", "np_max", "kind"] + [f"score{L}" for L in m_by_length]
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows({k: v for k, v in row.items() if k != "gb"} for row in rows)

    non_default = (args.partition_bytes != 4_294_967_296 or args.min_partitions != 4
                   or args.max_partitions != 256 or args.rounding != "pow2")
    if non_default:
        print(f"NOTE: non-default nb_partitions formula -- partition_bytes={args.partition_bytes:.0f}, "
              f"min={args.min_partitions}, max={args.max_partitions}, rounding={args.rounding}")
    print(f"scored {len(rows)} designs")
    print(f"  -> {json_path}")
    print(f"  -> {csv_path}")
    smin = min(d["s"] for d in rows)
    smax = max(d["s"] for d in rows)
    gmin = min(d["g"] for d in rows)
    gmax = max(d["g"] for d in rows)
    print(f"  storage range: {smin:.0f} - {smax:.0f} GB")
    print(f"  groups range:  {gmin} - {gmax}")


if __name__ == "__main__":
    main()
