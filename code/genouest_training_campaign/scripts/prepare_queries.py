#!/usr/bin/env python3
"""Extract reproducible positive-control query substrings from Logan unitigs."""
from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import random
import subprocess
from pathlib import Path


def open_text(path: str):
    if path.endswith(".zst"):
        proc = subprocess.Popen(["zstd", "-dc", "--", path], stdout=subprocess.PIPE)
        if proc.stdout is None:
            raise RuntimeError("could not open zstd stdout")
        return io.TextIOWrapper(proc.stdout, encoding="ascii", errors="ignore"), proc
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="ascii", errors="ignore"), None
    return open(path, "rt", encoding="ascii", errors="ignore"), None


def fasta_records(path: str):
    h, proc = open_text(path)
    header = None
    seq = []
    try:
        for line in h:
            if line.startswith(">"):
                if header is not None:
                    yield header, "".join(seq)
                header = line[1:].strip().split()[0]
                seq = []
            else:
                seq.append(line.strip().upper())
        if header is not None:
            yield header, "".join(seq)
    finally:
        h.close()
        if proc is not None:
            rc = proc.wait()
            if rc != 0:
                raise RuntimeError(f"zstd failed for {path} with code {rc}")


def manifest_files(path: str) -> list[str]:
    files = []
    with open(path) as f:
        first = True
        for line in f:
            obj = json.loads(line)
            if first:
                first = False
                continue
            xs = obj.get("files") or []
            if xs:
                files.append(xs[0])
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--lengths", default="250,500,1000")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=20260818)
    ap.add_argument("--max-source-files", type=int, default=100)
    args = ap.parse_args()

    lengths = sorted({int(x) for x in args.lengths.split(",") if x.strip()})
    max_len = max(lengths)
    rng = random.Random(args.seed)
    files = manifest_files(args.manifest)
    rng.shuffle(files)
    files = files[: min(args.max_source_files, len(files))]
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for L in lengths:
        (out / str(L)).mkdir(parents=True, exist_ok=True)

    found = 0
    metadata = []
    for path in files:
        if found >= args.n:
            break
        if not os.path.isfile(path):
            continue
        for header, seq in fasta_records(path):
            if found >= args.n:
                break
            if len(seq) < max_len or any(c not in "ACGT" for c in seq):
                continue
            start = rng.randint(0, len(seq) - max_len)
            anchor = seq[start:start + max_len]
            qid = f"q{found:03d}"
            for L in lengths:
                offset = (max_len - L) // 2
                q = anchor[offset:offset + L]
                qpath = out / str(L) / f"{qid}_{L}.fa"
                with open(qpath, "w") as f:
                    f.write(f">{qid}_L{L}\n{q}\n")
            metadata.append((qid, path, header, start, max_len))
            found += 1

    if found < args.n:
        raise SystemExit(f"only found {found} sequences of at least {max_len} bp in {len(files)} source files")
    with open(out / "queries.tsv", "w") as f:
        f.write("query_id\tsource_file\tsource_record\tstart\tanchor_length\n")
        for row in metadata:
            f.write("\t".join(map(str, row)) + "\n")
    print(f"queries={found}")
    print(f"output={out}")


if __name__ == "__main__":
    main()
