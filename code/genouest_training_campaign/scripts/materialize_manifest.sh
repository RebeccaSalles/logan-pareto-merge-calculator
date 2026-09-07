#!/usr/bin/env bash
# Decompress every .zst sample in $MANIFEST into $DECOMP_ROOT ONCE, producing
# $BUILD_MANIFEST. Every candidate (base, groups) configuration builds over
# the same sample set, so this runs once, not per-config -- see the comment
# block in config.env next to DECOMP_ROOT/BUILD_MANIFEST.
#
# Idempotent and resumable: safe to re-run (e.g. after a Slurm walltime
# limit) or to run repeatedly with --max-files to materialize the corpus in
# stages while watching disk usage.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/config.env"
source "${SCRIPT_DIR}/lib/common.sh"

if [[ ! -s "$MANIFEST" ]]; then
  echo "ERROR: manifest missing: $MANIFEST (run build_unitig_manifest.py first)" >&2
  exit 2
fi

mkdir -p "$DECOMP_ROOT" "$(dirname "$BUILD_MANIFEST")"

echo "Estimated decompressed corpus size: ~${DECOMP_ESTIMATE_BYTES} bytes" \
     "(measured ~1.52x zstd->gzip expansion ratio applied to the corrected" \
     "~2.48TB raw-corpus measurement, extrapolated -- see config.env)."
AVAIL=$(effective_headroom_bytes)
echo "Currently available (min of df free space and quota headroom): ${AVAIL} bytes."
if [[ "${REPLACE_SOURCE:-0}" != "1" ]] && (( AVAIL < DECOMP_ESTIMATE_BYTES + MIN_FREE_BYTES )); then
  echo "WARNING: available headroom (${AVAIL}) looks smaller than the estimate" \
       "(${DECOMP_ESTIMATE_BYTES}) plus the reserved margin (${MIN_FREE_BYTES})." \
       "In the default additive mode this will very likely run out of space" \
       "partway through the full corpus -- fine for a scoped-down subset." \
       "Set REPLACE_SOURCE=1 in config.env for in-place replacement instead" \
       "(deletes the raw .zst as each file is decompressed -- see" \
       "materialize_manifest.py's module docstring before using it)." >&2
fi

REPLACE_ARGS=()
if [[ "${REPLACE_SOURCE:-0}" == "1" ]]; then
  REPLACE_ARGS=(--replace-source --deleted-log "${MANIFEST_DIR}/deleted_sources.tsv")
fi
# Always on: a single missing/corrupt source must not abort a run spanning
# millions of files (real, known gap in this corpus -- ~1,634 accessions
# never downloaded, NoSuchKey). See materialize_manifest.py's --failed-log
# help and the 2026-08-25 postmortem in docs/implementation_log.md.
FAILED_LOG_ARGS=(--failed-log "${MANIFEST_DIR}/failed_sources.tsv")

MAX_FILES="${1:-0}"
set +e
python3 "$SCRIPT_DIR/materialize_manifest.py" "$MANIFEST" \
  --decomp-root "$DECOMP_ROOT" \
  --output "$BUILD_MANIFEST" \
  --mapping "$DECOMP_MAPPING" \
  --min-free-bytes "$MIN_FREE_BYTES" \
  --max-files "$MAX_FILES" \
  --workers "${MATERIALIZE_WORKERS:-1}" \
  "${FAILED_LOG_ARGS[@]}" \
  "${REPLACE_ARGS[@]}"
RC=$?
set -e
if [[ "$RC" -ne 0 && "$RC" -ne 3 ]]; then
  echo "ERROR: materialize_manifest.py failed (rc=$RC)" >&2
  exit "$RC"
fi

python3 "$SCRIPT_DIR/check_build_manifest.py" "$BUILD_MANIFEST" || {
  echo "ERROR: $BUILD_MANIFEST still references unsupported files after materialization." >&2
  exit 1
}

if [[ "$RC" -eq 3 ]]; then
  echo "Partial run (hit --max-files or a free-space guard). Re-run this script to continue."
  exit 3
fi
echo "BUILD_MANIFEST ready: $BUILD_MANIFEST"
