#!/usr/bin/env python3
"""Materialize a build-ready manifest from a .zst-referencing source manifest.

kmtricks cannot open .zst files directly (confirmed empirically against both
kmtricks builds available to this project -- see kmer_spans
docs/experiment_status.md, "kmtricks input format" section). This script
decompresses each .zst sample to a .gz copy kmtricks CAN read, once, and
writes a new manifest pointing at the decompressed copies plus a
path-mapping TSV (same format rewrite_manifest_paths.py consumes/produces).

Designed to be run ONCE and reused across every (base, groups) candidate in
the design space: they all build over the same sample set, only the
Bloom-filter grouping differs, so there is no reason to decompress more than
once. Idempotent/resumable -- already-materialized samples are skipped, so
interrupting and re-running is safe.

Non-.zst inputs (already .gz or plain) pass through unchanged, with the
manifest simply recording the original path -- nothing to materialize.

Two disk strategies, chosen with --replace-source:

  default (additive): decompressed copies are written ALONGSIDE the raw
  .zst corpus. Preserves the raw data; the two copies' sizes add up, but
  for the full span<=20 corpus this DOES fit the project's 10TB quota
  (measured/corrected 2026-08-25: ~1.52x expansion ratio applied to the
  actual ~2.48TB raw corpus -- not the previously assumed 4TB -- gives
  ~3.78TB decompressed, so raw + decompressed = ~6.26TB, with ~3.7TB of
  quota headroom to spare). Also fine for a scoped-down subset.

  --replace-source (in-place): after a decompressed copy is verified good,
  the ORIGINAL .zst is deleted. Total footprint converges to just the
  decompressed size (~3.78TB for the full corpus -- fits with more room
  still). Cost: the raw .zst is gone locally. Mitigated by s3://logan-pub being public and
  no-sign-request -- re-fetching a deleted accession is possible, just not
  free (bandwidth/time). Every deletion is logged (source path, size,
  timestamp) to --deleted-log so a targeted re-download list can be
  reconstructed if ever needed. This modifies files under the SHARED raw
  corpus directory (not just this pipeline's own scratch space) -- use
  deliberately, not as a default.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def free_bytes(path: str) -> int:
    st = shutil.disk_usage(path)
    return st.free


def decompress_one(src: str, dst: Path) -> int:
    """Stream zstd -dc | gzip -1 into dst. Returns bytes written."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    with open(tmp, "wb") as out:
        zproc = subprocess.Popen(["zstd", "-dc", "--", src], stdout=subprocess.PIPE)
        gproc = subprocess.Popen(["gzip", "-1"], stdin=zproc.stdout, stdout=out)
        assert zproc.stdout is not None
        zproc.stdout.close()
        grc = gproc.wait()
        zrc = zproc.wait()
    if zrc != 0 or grc != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"decompression failed for {src} (zstd rc={zrc}, gzip rc={grc})")
    size = tmp.stat().st_size
    tmp.rename(dst)
    return size


def verify_gzip(dst: Path) -> bool:
    """Sanity check: the written .gz decompresses cleanly and has content.

    Not a full re-verification against the source (that would cost as much
    as the decompression itself) -- just enough to catch a truncated or
    corrupt write before deleting the only remaining copy of the data.
    """
    try:
        with gzip.open(dst, "rb") as f:
            first = f.read(1)
            return len(first) > 0 and first[:1] == b">"
    except Exception:
        return False


def load_manifest(path: str) -> tuple[dict, list[dict]]:
    header = None
    rows = []
    with open(path) as f:
        for i, line in enumerate(f):
            obj = json.loads(line)
            if i == 0:
                header = obj
                continue
            rows.append(obj)
    if header is None:
        raise SystemExit(f"empty manifest: {path}")
    return header, rows


class MaterializeError(Exception):
    def __init__(self, src: str, message: str):
        super().__init__(message)
        self.src = src


def materialize_one(src: str, dst: Path, replace_source: bool) -> tuple[str, Path, int, int | None]:
    """Worker function: decompress (and optionally delete the source).

    Runs in a thread pool -- must not touch shared mutable state (the
    caller does all bookkeeping/file writes after collecting the result).
    subprocess-based I/O releases the GIL while waiting, so threads (not a
    heavier process pool) are enough to parallelize this I/O-bound work.
    Returns (src, dst, decompressed_bytes, deleted_src_bytes_or_None).
    """
    size = decompress_one(src, dst)
    deleted_src_bytes = None
    if replace_source:
        if not verify_gzip(dst):
            dst.unlink(missing_ok=True)
            raise MaterializeError(
                src,
                f"verification failed for {dst} (decompressed from {src}); "
                f"refusing to delete source. Nothing was removed for this file.",
            )
        deleted_src_bytes = os.path.getsize(src)
        os.remove(src)
    return src, dst, size, deleted_src_bytes


def load_existing_mapping(mapping_path: Path) -> dict[str, str]:
    mapping = {}
    if mapping_path.exists():
        with open(mapping_path) as f:
            for line in f:
                if not line.strip() or line.startswith("#"):
                    continue
                a, b = line.rstrip("\n").split("\t")[:2]
                mapping[a] = b
    return mapping


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", help="source JSONL manifest (from build_unitig_manifest.py)")
    ap.add_argument("--decomp-root", required=True, help="persistent cache directory for decompressed copies")
    ap.add_argument("--output", required=True, help="output JSONL manifest with rewritten paths")
    ap.add_argument("--mapping", required=True, help="path-mapping TSV (original -> decompressed), appended to on resume")
    ap.add_argument("--min-free-bytes", type=int, default=200_000_000_000,
                     help="abort before starting a new file if free space on --decomp-root's filesystem would drop below this (default 200GB)")
    ap.add_argument("--max-files", type=int, default=0, help="stop after materializing this many new files (0 = no limit); useful for staged/partial runs")
    ap.add_argument("--replace-source", action="store_true",
                     help="DESTRUCTIVE: delete each .zst source after its decompressed copy is "
                          "verified good. Modifies the shared raw corpus directory, not just this "
                          "pipeline's scratch space. Off by default -- see module docstring.")
    ap.add_argument("--deleted-log", default="",
                     help="TSV log of (source_path, bytes, iso_timestamp) for every file deleted "
                          "by --replace-source. Required if --replace-source is set.")
    ap.add_argument("--failed-log", default="",
                     help="TSV log of (source_path, error, iso_timestamp) for sources that failed "
                          "to decompress (e.g. missing on disk -- known real gap: ~1,634 accessions "
                          "in this project's own corpus never downloaded, NoSuchKey). Without this, "
                          "a single bad source crashes the whole run -- see 2026-08-25 postmortem "
                          "in kmer_spans docs/implementation_log.md. Failures are skipped (not "
                          "written to --output) and the run continues.")
    ap.add_argument("--workers", type=int, default=1,
                     help="parallel decompression workers (default: 1, sequential; the shell "
                          "wrapper materialize_manifest.sh instead defaults to config.env's "
                          "MATERIALIZE_WORKERS=8). Measured 2026-08-25 on a real 1472-file slice "
                          "of the corpus: ~12.1 files/sec at 1 worker (~6.85 days full-corpus), "
                          "67.33 files/sec at 8 workers (~29.5 hours full-corpus), 79.73 files/sec "
                          "at 16 workers (only +18% over 8 workers, for 2x the concurrent load). "
                          "This is a many-small-files, network-filesystem-bound workload (the "
                          "same class of problem that makes `du`/`find` slow at scale in this "
                          "project), so scaling is clearly sub-linear -- re-measure before trying "
                          "a worker count above 16.")
    args = ap.parse_args()
    if args.workers < 1:
        ap.error("--workers must be >= 1")

    if args.replace_source and not args.deleted_log:
        raise SystemExit("--replace-source requires --deleted-log (a record of what was deleted)")

    decomp_root = Path(args.decomp_root)
    decomp_root.mkdir(parents=True, exist_ok=True)
    mapping_path = Path(args.mapping)
    mapping = load_existing_mapping(mapping_path)

    deleted_log_f = None
    if args.replace_source:
        print("WARNING: --replace-source is set. Verified-good .zst sources will be "
              "DELETED from the shared raw corpus directory after decompression. "
              f"Deletions are logged to {args.deleted_log}.", file=sys.stderr)
        deleted_log_path = Path(args.deleted_log)
        deleted_log_path.parent.mkdir(parents=True, exist_ok=True)
        is_new_log = not deleted_log_path.exists()
        deleted_log_f = open(deleted_log_path, "a")
        if is_new_log:
            deleted_log_f.write("source_path\tbytes\tiso_timestamp\n")

    failed_log_f = None
    already_failed: set[str] = set()
    if args.failed_log:
        failed_log_path = Path(args.failed_log)
        failed_log_path.parent.mkdir(parents=True, exist_ok=True)
        if failed_log_path.exists():
            with open(failed_log_path) as f:
                for line in f:
                    if not line.strip() or line.startswith("source_path\t"):
                        continue
                    already_failed.add(line.split("\t", 1)[0])
        is_new_failed_log = not failed_log_path.exists()
        failed_log_f = open(failed_log_path, "a")
        if is_new_failed_log:
            failed_log_f.write("source_path\terror\tiso_timestamp\n")

    header, rows = load_manifest(args.manifest)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    new_files = 0
    reused = 0
    passthrough = 0
    failed = 0
    total_new_bytes = 0

    mapping_f = open(mapping_path, "a")
    out_f = open(out_path, "w")
    out_f.write(json.dumps(header) + "\n")

    # Chunked so a free-space check happens regularly even on an unbounded
    # (--max-files 0) full-corpus run, and so we never hold millions of
    # in-flight futures in memory at once.
    chunk_size = max(args.workers * 20, 100)
    stop = False

    try:
        row_iter = iter(rows)
        while not stop:
            # Build one chunk of work: passthrough/reused rows are resolved
            # immediately (cheap, no thread needed); .zst rows needing real
            # work are queued for the thread pool.
            to_materialize: list[tuple[str, Path, dict, str]] = []  # (src, dst, new_row, name)
            for row in row_iter:
                files = row.get("files") or []
                if not files:
                    continue
                src = os.path.abspath(files[0])
                new_row = dict(row)

                if not src.endswith(".zst"):
                    new_row["files"] = [src]
                    out_f.write(json.dumps(new_row) + "\n")
                    passthrough += 1
                    continue

                if src in mapping and os.path.isfile(mapping[src]):
                    new_row["files"] = [mapping[src]]
                    out_f.write(json.dumps(new_row) + "\n")
                    reused += 1
                    continue

                if src in already_failed:
                    failed += 1
                    continue

                if args.max_files and new_files + len(to_materialize) >= args.max_files:
                    print(f"STOP: reached --max-files={args.max_files}; re-run to continue "
                          f"(resumable via --mapping/{mapping_path})", file=sys.stderr)
                    stop = True
                    break

                name = row.get("name") or Path(src).stem
                dst = decomp_root / f"{name}.fa.gz"
                to_materialize.append((src, dst, new_row, name))
                if len(to_materialize) >= chunk_size:
                    break

            if not to_materialize:
                break

            free = free_bytes(str(decomp_root))
            if free < args.min_free_bytes:
                print(f"ERROR: only {free} bytes free on {decomp_root}'s filesystem "
                      f"(< --min-free-bytes={args.min_free_bytes}); stopping before "
                      f"materializing this chunk. Already-materialized samples are recorded "
                      f"in {mapping_path} and will be reused on the next run.",
                      file=sys.stderr)
                break

            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = {
                    pool.submit(materialize_one, src, dst, args.replace_source): (src, dst, new_row, name)
                    for src, dst, new_row, name in to_materialize
                }
                for future in as_completed(futures):
                    src, dst, new_row, name = futures[future]
                    try:
                        src2, dst2, size, deleted_src_bytes = future.result()
                    except Exception as exc:
                        # Do not let one bad source (known real case: an
                        # accession missing from the raw corpus download,
                        # NoSuchKey) abort a run spanning millions of files.
                        # Nothing was deleted for a failed source -- either
                        # decompress_one raised before any deletion, or (for
                        # --replace-source) verify_gzip already refused the
                        # delete. Not written to --output; recorded here so
                        # the gap is explicit and searchable, and skipped on
                        # resume via --failed-log instead of retried forever.
                        failed += 1
                        if failed_log_f is not None:
                            failed_log_f.write(
                                f"{src}\t{exc}\t{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
                            )
                            failed_log_f.flush()
                        else:
                            print(f"FAILED (no --failed-log set, not persisted): {src}: {exc}",
                                  file=sys.stderr)
                        continue

                    if args.replace_source:
                        deleted_log_f.write(
                            f"{src}\t{deleted_src_bytes}\t{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
                        )
                        deleted_log_f.flush()

                    mapping[src] = str(dst)
                    mapping_f.write(f"{src}\t{dst}\n")
                    mapping_f.flush()
                    new_row["files"] = [str(dst)]
                    out_f.write(json.dumps(new_row) + "\n")
                    out_f.flush()
                    new_files += 1
                    total_new_bytes += size
                    if new_files % 500 == 0:
                        print(f"[{new_files} materialized this run] {name}: {size} bytes -> {dst}", flush=True)
    finally:
        mapping_f.close()
        out_f.close()
        if deleted_log_f is not None:
            deleted_log_f.close()
        if failed_log_f is not None:
            failed_log_f.close()

    print(f"materialized_this_run={new_files}")
    print(f"reused_from_cache={reused}")
    print(f"passthrough_non_zst={passthrough}")
    print(f"failed_this_run={failed}")
    print(f"new_bytes_this_run={total_new_bytes}")
    print(f"replace_source={args.replace_source}")
    print(f"output={out_path}")
    print(f"mapping={mapping_path}")
    if args.max_files and new_files >= args.max_files:
        sys.exit(3)  # partial: caller should re-run to continue


if __name__ == "__main__":
    main()
