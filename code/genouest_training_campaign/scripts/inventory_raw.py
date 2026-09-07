#!/usr/bin/env python3
"""Inventory a Logan raw/unitig directory without reading sequence contents."""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

EXTENSIONS = (
    ".unitigs.fa.zst", ".fa.zst", ".fasta.zst", ".fna.zst",
    ".unitigs.fa.gz", ".fa.gz", ".fasta.gz", ".fna.gz",
    ".unitigs.fa", ".fa", ".fasta", ".fna",
)


def compression(path: str) -> str:
    if path.endswith(".zst"):
        return "zst"
    if path.endswith(".gz"):
        return "gz"
    return "plain"


def source_span(path: str) -> str:
    parts = Path(path).parts
    for part in reversed(parts):
        m = re.search(r"(?:span|sp)[_-]?(\d+)", part, re.I)
        if m:
            return m.group(1)
    return ""


def iter_paths(root: str, file_list: str | None):
    if file_list:
        with open(file_list) as f:
            for line in f:
                p = line.strip()
                if p and not p.startswith("#"):
                    yield os.path.abspath(p)
        return
    # os.walk + os.path.getsize is one stat() syscall per file. Over a
    # network filesystem with millions of files (e.g. unitigs_spans_20/,
    # ~7M files) this can take a very long time -- prefer --file-list
    # pointing at an already-existing accession/file list where one exists
    # (e.g. the s5cmd commands file from the original Logan download, or a
    # list derived from kmer_spans grouped_spans_tigs_sumlen_distribution.csv)
    # instead of walking the directory tree from scratch.
    print(
        "WARNING: walking the filesystem tree (no --file-list given). This "
        "can be very slow over millions of files on network storage -- "
        "consider --file-list with an existing accession/file list instead.",
        file=sys.stderr,
    )
    for dirpath, _, files in os.walk(root):
        for name in files:
            p = os.path.join(dirpath, name)
            if p.endswith(EXTENSIONS):
                yield p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="")
    ap.add_argument("--file-list", default="")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    if not args.root and not args.file_list:
        ap.error("provide --root or --file-list")

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    list_path = out / "logan_files.txt"
    csv_path = out / "inventory.csv"
    summary_path = out / "inventory_summary.txt"

    rows = []
    by_comp = Counter()
    by_span = defaultdict(lambda: [0, 0])
    total = 0
    missing = 0
    for p in sorted(set(iter_paths(args.root, args.file_list))):
        if not os.path.isfile(p):
            missing += 1
            continue
        size = os.path.getsize(p)
        comp = compression(p)
        span = source_span(p)
        total += size
        by_comp[comp] += 1
        by_span[span][0] += 1
        by_span[span][1] += size
        rows.append((p, size, comp, span))

    with open(list_path, "w") as f:
        for p, *_ in rows:
            f.write(p + "\n")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path", "bytes", "compression", "source_span"])
        w.writerows(rows)
    with open(summary_path, "w") as f:
        f.write(f"files={len(rows)}\n")
        f.write(f"missing={missing}\n")
        f.write(f"bytes={total}\n")
        f.write(f"terabytes_decimal={total/1e12:.6f}\n")
        for c, n in sorted(by_comp.items()):
            f.write(f"compression_{c}={n}\n")
        for span, (n, b) in sorted(by_span.items(), key=lambda x: (x[0] == '', int(x[0]) if x[0].isdigit() else 999999)):
            label = span or "unknown"
            f.write(f"span_{label}_files={n}\n")
            f.write(f"span_{label}_bytes={b}\n")

    print(summary_path.read_text(), end="")
    print(f"file_list={list_path}")
    print(f"inventory_csv={csv_path}")


if __name__ == "__main__":
    main()
