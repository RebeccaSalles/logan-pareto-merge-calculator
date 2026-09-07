#!/usr/bin/env python3
"""Select a few manifest entries and print commands for an ntcard spot check.

The script intentionally does not materialize files automatically. For .zst inputs,
use the emitted zstd|gzip command into a temporary location with enough space, then
run kmhelpers list on that gz file. ntcard is an estimator, so compare within a
small relative tolerance rather than requiring exact equality.
"""
import argparse,json,random
ap=argparse.ArgumentParser();ap.add_argument("manifest");ap.add_argument("--n",type=int,default=3);ap.add_argument("--seed",type=int,default=20260818);ap.add_argument("-k",type=int,default=25,help="must match the manifest's own k (default: 25, this project's index k-mer size)");args=ap.parse_args()
rows=[]
with open(args.manifest) as f:
    first=True
    for line in f:
        obj=json.loads(line)
        if first:first=False;continue
        if obj.get("files") and obj.get("kmer_count"):rows.append(obj)
rng=random.Random(args.seed);rng.shuffle(rows)
for i,r in enumerate(rows[:args.n],1):
    p=r["files"][0];n=r["kmer_count"]
    print(f"# sample {i}: {r['name']} manifest_count={n}")
    if p.endswith('.zst'):
        print(f"zstd -dc -- {p!r} | gzip -1 > /tmp/kmh_spot_{i}.fa.gz")
        q=f"/tmp/kmh_spot_{i}.fa.gz"
    else:q=p
    print(f"printf '%s\\n' {q!r} > /tmp/kmh_spot_{i}.txt")
    print(f"kmhelpers list /tmp/kmh_spot_{i}.txt -o /tmp/kmh_spot_{i}.jsonl -k {args.k} -dt assembled")
    print(f"tail -n 1 /tmp/kmh_spot_{i}.jsonl")
    print()
