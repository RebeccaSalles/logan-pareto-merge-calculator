#!/usr/bin/env python3
"""Build a full-Logan manifest (all spans) from the real DynamoDB unitig
stats CSV, using the EXACT same kmer_count approximation already
documented in this project's real span<=20 manifest header:
    kmer_count = seqstats_unitigs_sumlen - (k-1) * seqstats_unitigs_nbseq
(clamped at 0). No FASTA scan, no download needed -- this is only for
kmhelpers profile/design (no-build) scoring.
"""
import csv, json, sys

K = 25
IN_CSV = "/projects/logan_compression/rsalles/span_tuning_paper/manifest/dynamodb_tigs_stats_sorted.csv"
OUT_JSONL = "/projects/logan_compression/rsalles/span_tuning_paper/manifest/logan_full_k25.jsonl"
PLACEHOLDER_DIR = "/projects/logan_compression/unitigs_full"

header = {
    "description": "Full Logan unitig manifest (all spans), for kmhelpers profile/design (no-build) scoring only -- file paths are placeholders, real unitig data is not staged beyond span<=20",
    "root_path": "/",
    "k": K,
    "assembled": True,
    "abundance_min": 1,
    "count_method": f"cumulative_size - (k-1)*nb_unitigs, joined from dynamodb_tigs_stats_sorted.csv (seqstats_unitigs_nbseq/seqstats_unitigs_sumlen), same formula as logan_k25.jsonl's primary path; k={K}",
}

n = 0
n_clamped = 0
with open(IN_CSV, newline="") as fin, open(OUT_JSONL, "w") as fout:
    fout.write(json.dumps(header) + "\n")
    r = csv.DictReader(fin)
    for row in r:
        acc = row["accession"]
        try:
            nbseq = int(row["seqstats_unitigs_nbseq"])
            sumlen = int(row["seqstats_unitigs_sumlen"])
        except (ValueError, KeyError):
            continue
        kc = sumlen - (K - 1) * nbseq
        if kc < 1:
            kc = 1
            n_clamped += 1
        entry = {"name": acc, "files": [f"{PLACEHOLDER_DIR}/{acc}.unitigs.fa.zst"], "kmer_count": kc}
        fout.write(json.dumps(entry) + "\n")
        n += 1

print(f"wrote {n} entries to {OUT_JSONL}")
print(f"clamped-to-1 (sumlen too small for nbseq*{K-1}): {n_clamped}")
