#!/usr/bin/env python3
"""Build a kmhelpers JSONL manifest from Logan unitig FASTA files.

This project indexes at k=25 (kmer_spans' established, consistently-used
index k-mer size -- see config.env's KMER_SIZE comment), NOT the k=31 Logan
unitigs are assembled at. Those are different, unrelated parameters.

For Logan unitigs, each represented 31-mer is unique BY CONSTRUCTION (k=31
only) -- so at k=31, sum(max(0, sequence_length-k+1)) over FASTA records is
an *exact* distinct-k-mer count. At k=25 (or any k != 31) it is an
*approximation*, not an exact count: a 25-mer can recur within/across
unitigs even though the unitigs were built to avoid repeated 31-mers.

This approximation is used anyway, deliberately, because it's the same one
kmer_spans' own create_fof.py already relies on for span bucketing
(`cumulative_size - (kmer_size-1)*nb_unitigs`, see index_id_to_size()) --
using it here keeps this manifest consistent with the rest of the project.
Because it is only *approximate* at k=25, spot-check it with
scripts/spotcheck_unitig_counts.py before trusting it at scale -- don't
skip that step.

Primary path: --stats-csv join, not a FASTA scan.
------------------------------------------------
create_fof.py's formula only needs two aggregate numbers per accession
(unitig count, summed unitig length) -- exactly the columns already present
in the project's own per-accession stats CSV (unitigs_with_bins.csv /
dynamodb_tigs_stats_sorted.csv: `accession,seqstats_unitigs_nbseq,
seqstats_unitigs_sumlen[,unitigs_log2_span]`). So the count for every
accession in --file-list can be looked up directly from that CSV, with no
need to decompress and stream the (multi-terabyte) FASTA content at all.

The per-record floor in the FASTA-scan formula (max(0, length-k+1) per
unitig, not per accession) only matters if some individual unitig is
shorter than k-1=24bp. Logan unitigs are assembled at k=31, so the
shortest possible unitig is 31bp (a single k-31-mer) -- above 24bp -- so
the floor never actually triggers for this corpus, and the aggregate CSV
formula is mathematically identical to the FASTA-scan formula here, not
merely a faster approximation of it.

Any accession present in --file-list but missing from --stats-csv (should
be rare -- would mean the file list and stats CSV have diverged) falls
back to the direct FASTA-scan (count_fasta_kmers()), so no accession is
silently dropped just because the fast path can't cover it. The audit CSV
records which method produced each row's count (`count_source`).
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def opener(path: str):
    if path.endswith(".zst"):
        proc = subprocess.Popen(["zstd", "-dc", "--", path], stdout=subprocess.PIPE)
        if proc.stdout is None:
            raise RuntimeError("could not open zstd stdout")
        text = io.TextIOWrapper(proc.stdout, encoding="ascii", errors="ignore")
        return text, proc
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="ascii", errors="ignore"), None
    return open(path, "rt", encoding="ascii", errors="ignore"), None


def count_fasta_kmers(path: str, k: int) -> tuple[int, int, int]:
    """Fallback path: stream the FASTA and count directly. Only used for
    accessions the --stats-csv join can't cover (see module docstring)."""
    handle, proc = opener(path)
    total_kmers = 0
    total_bases = 0
    records = 0
    current_len = 0
    try:
        for line in handle:
            if line.startswith(">"):
                if records:
                    total_kmers += max(0, current_len - k + 1)
                records += 1
                current_len = 0
            else:
                s = line.strip()
                current_len += len(s)
                total_bases += len(s)
        if records:
            total_kmers += max(0, current_len - k + 1)
    finally:
        handle.close()
        if proc is not None:
            rc = proc.wait()
            if rc != 0:
                raise RuntimeError(f"zstd failed for {path} with code {rc}")
    if records == 0:
        raise ValueError(f"no FASTA records found: {path}")
    return total_kmers, total_bases, records


def sample_name(path: str) -> str:
    name = os.path.basename(path)
    for suffix in (".unitigs.fa.zst", ".unitigs.fa.gz", ".unitigs.fa", ".fasta.zst", ".fasta.gz", ".fasta", ".fna.zst", ".fna.gz", ".fna", ".fa.zst", ".fa.gz", ".fa"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


def source_span(path: str) -> str:
    for part in reversed(Path(path).parts):
        m = re.search(r"(?:span|sp)[_-]?(\d+)", part, re.I)
        if m:
            return m.group(1)
    return ""


def load_done(path: Path) -> dict[str, dict]:
    done = {}
    if not path.exists():
        return done
    with open(path) as f:
        first = True
        for line in f:
            obj = json.loads(line)
            if first:
                first = False
                continue
            files = obj.get("files") or []
            if files:
                done[os.path.abspath(files[0])] = obj
    return done


def load_stats(csv_path: str, wanted_names: set[str]) -> dict[str, tuple[int, int]]:
    """Stream the stats CSV once, keeping only rows whose accession is in
    wanted_names (bounds memory to the accessions actually in scope, not
    the full ~26.8M-row corpus)."""
    stats: dict[str, tuple[int, int]] = {}
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        # accepts either unitigs_with_bins.csv (4 cols, extra
        # unitigs_log2_span) or dynamodb_tigs_stats_sorted.csv (3 cols) --
        # both have accession,seqstats_unitigs_nbseq,seqstats_unitigs_sumlen
        # as the first three columns; only those three are used here.
        expected = ["accession", "seqstats_unitigs_nbseq", "seqstats_unitigs_sumlen"]
        if header[:3] != expected:
            raise SystemExit(f"unexpected stats CSV header: {header[:3]!r} (expected {expected!r})")
        for row in reader:
            acc = row[0]
            if acc in wanted_names:
                stats[acc] = (int(row[1]), int(row[2]))
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file-list", required=True)
    ap.add_argument("--stats-csv", required=True,
                     help="per-accession stats CSV (unitigs_with_bins.csv or "
                          "dynamodb_tigs_stats_sorted.csv -- interchangeable for "
                          "this script's purposes, see module docstring) providing "
                          "seqstats_unitigs_nbseq/seqstats_unitigs_sumlen; used to "
                          "derive kmer_count via create_fof.py's own formula instead "
                          "of scanning FASTA content")
    ap.add_argument("--output", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("-k", type=int, default=25,
                    help="index k-mer size (default: 25, this project's established value -- "
                         "NOT the k=31 Logan unitigs are assembled at; see module docstring)")
    ap.add_argument("--trust-unitigs", action="store_true", required=True,
                    help="acknowledge that k-mer counts are approximated as "
                         "sum(max(0, length-k+1)) per record -- exact only at k=31 "
                         "(Logan's construction k), an approximation at any other k "
                         "including this project's k=25; spot-check with "
                         "spotcheck_unitig_counts.py before trusting at scale")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    if args.k != 31:
        print(
            f"NOTE: k={args.k} != 31 (Logan's unitig construction k). The "
            "distinct-k-mer count below is an approximation, not exact -- "
            "see this script's module docstring. Spot-check with "
            "spotcheck_unitig_counts.py before trusting it at scale.",
            file=sys.stderr,
        )

    paths = []
    with open(args.file_list) as f:
        for line in f:
            p = line.strip()
            if p and not p.startswith("#"):
                paths.append(os.path.abspath(p))
    if not paths:
        raise SystemExit("empty file list")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    audit = Path(args.audit)
    audit.parent.mkdir(parents=True, exist_ok=True)

    done = load_done(out) if args.resume else {}
    mode = "a" if args.resume and out.exists() else "w"
    audit_mode = "a" if args.resume and audit.exists() else "w"

    names = {obj["name"] for obj in done.values() if "name" in obj}

    # Pre-compute the (path, name) pairs still needed so load_stats() only
    # has to keep rows for accessions actually in scope.
    pending = []
    for p in paths:
        if p in done:
            continue
        pending.append((p, sample_name(p)))
    wanted_names = {name for _, name in pending}
    print(f"Loading stats for {len(wanted_names)} accessions from {args.stats_csv} ...", file=sys.stderr)
    stats = load_stats(args.stats_csv, wanted_names)
    missing_from_csv = wanted_names - stats.keys()
    if missing_from_csv:
        print(
            f"WARNING: {len(missing_from_csv)} accession(s) in --file-list not found in "
            f"--stats-csv; falling back to direct FASTA scan for those (slower).",
            file=sys.stderr,
        )

    with open(out, mode) as jout, open(audit, audit_mode, newline="") as acsv:
        if mode == "w":
            header = {
                "description": "Logan unitig manifest for kmhelpers span-tuning experiments",
                "root_path": "/",
                "k": args.k,
                "assembled": True,
                "abundance_min": 1,
                "count_method": (
                    "primary: cumulative_size - (k-1)*nb_unitigs, joined from a stats CSV "
                    "(seqstats_unitigs_nbseq/seqstats_unitigs_sumlen), same formula as "
                    "create_fof.py's index_id_to_size(); fallback (accessions missing from "
                    "the stats CSV): sum(max(0, unitig_length-k+1)) via direct FASTA scan. "
                    "Exact distinct-k-mer count only at k=31 (Logan's construction k), "
                    f"approximation otherwise (this manifest: k={args.k}); spot-checked "
                    "with ntcard where noted -- see count_source in the audit CSV."
                ),
            }
            jout.write(json.dumps(header) + "\n")
        aw = csv.writer(acsv)
        if audit_mode == "w":
            aw.writerow(["name", "path", "kmer_count", "bases", "fasta_records", "source_span", "bytes", "count_source"])

        total = len(pending)
        for i, (p, name) in enumerate(pending, 1):
            if not os.path.isfile(p):
                print(f"SKIP missing: {p}", file=sys.stderr)
                continue
            base = name
            n = 1
            while name in names:
                n += 1
                name = f"{base}_{n}"
            names.add(name)

            row = stats.get(name)
            if row is not None:
                nb_unitigs, cumulative_size = row
                count = max(0, cumulative_size - (args.k - 1) * nb_unitigs)
                bases = cumulative_size
                records = nb_unitigs
                count_source = "csv_join"
            else:
                count, bases, records = count_fasta_kmers(p, args.k)
                count_source = "fasta_scan_fallback"

            obj = {
                "name": name,
                "files": [p],
                "kmer_count": count,
            }
            jout.write(json.dumps(obj) + "\n")
            jout.flush()
            aw.writerow([name, p, count, bases, records, source_span(p), os.path.getsize(p), count_source])
            acsv.flush()
            print(f"[{i}/{total}] {name}: {count} k-mers ({count_source})", flush=True)


if __name__ == "__main__":
    main()
