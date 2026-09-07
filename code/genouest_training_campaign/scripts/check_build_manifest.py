#!/usr/bin/env python3
"""Fast preflight for file existence and compression compatibility."""
import argparse, json, os, sys

ap = argparse.ArgumentParser()
ap.add_argument("manifest")
ap.add_argument("--allow-zst", action="store_true",
                 help="Don't flag .zst inputs as an error -- only valid when "
                      "USE_NATIVE_ZSTD_KMTRICKS=1 (a patched kmtricks fork that "
                      "reads .zst directly is on PATH). See config.env.")
args = ap.parse_args()
missing=[]; zst=[]; unsupported=[]; n=0
allowed=(".fa", ".fasta", ".fna", ".fq", ".fastq", ".fa.gz", ".fasta.gz", ".fna.gz", ".fq.gz", ".fastq.gz")
if args.allow_zst:
    allowed = allowed + (".zst",)
with open(args.manifest) as f:
    first=True
    for line in f:
        obj=json.loads(line)
        if first:
            first=False; continue
        for p in obj.get("files", []):
            n += 1
            if not os.path.isfile(p): missing.append(p)
            if p.endswith(".zst") and not args.allow_zst: zst.append(p)
            elif not p.endswith(allowed): unsupported.append(p)
print(f"files={n} missing={len(missing)} zst={len(zst)} unsupported={len(unsupported)}")
if missing:
    print("First missing:", *missing[:5], sep="\n  ", file=sys.stderr)
if zst:
    print("ERROR: build manifest contains .zst inputs. kmhelpers/kmtricks 0.6.3 workflow documents gz/plain FASTA/FASTQ for building. Create gz/plain build copies and use rewrite_manifest_paths.py, or point BUILD_MANIFEST to an existing compatible copy, or set USE_NATIVE_ZSTD_KMTRICKS=1 in config.env and pass --allow-zst.", file=sys.stderr)
    print("First .zst:", *zst[:5], sep="\n  ", file=sys.stderr)
if unsupported:
    print("First unsupported:", *unsupported[:5], sep="\n  ", file=sys.stderr)
sys.exit(1 if missing or zst or unsupported else 0)
