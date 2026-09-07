#!/usr/bin/env python3
"""Rewrite only sample file paths in a kmhelpers JSONL manifest.

Use this after creating gz/plain materialized copies of .zst Logan unitigs.
The k-mer counts and sample IDs remain unchanged.
"""
from __future__ import annotations
import argparse, csv, json, os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("mapping_tsv", help="two columns: original_path TAB build_path")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    mapping = {}
    with open(args.mapping_tsv) as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            a, b = line.rstrip("\n").split("\t")[:2]
            mapping[os.path.abspath(a)] = os.path.abspath(b)
    with open(args.manifest) as src, open(args.output, "w") as dst:
        first = True
        for line in src:
            obj = json.loads(line)
            if first:
                first = False
                dst.write(json.dumps(obj) + "\n")
                continue
            files = obj.get("files") or []
            rewritten = []
            for p in files:
                key = os.path.abspath(p)
                if key not in mapping:
                    raise SystemExit(f"missing path mapping for {p}")
                new = mapping[key]
                if not os.path.isfile(new):
                    raise SystemExit(f"mapped build file does not exist: {new}")
                rewritten.append(new)
            obj["files"] = rewritten
            dst.write(json.dumps(obj) + "\n")
    print(args.output)

if __name__ == "__main__":
    main()
