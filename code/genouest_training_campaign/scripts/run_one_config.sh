#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 5 ]]; then
  echo "usage: $0 CONFIG_ID BASE GROUPS EST_TOTAL_BYTES EST_MAX_GROUP_BYTES" >&2
  exit 2
fi
CONFIG_ID="$1"; BASE="$2"; GROUPS_N="$3"; EST_TOTAL="$4"; EST_MAX="$5"; PHASE="${6:-training}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/config.env"
source "${SCRIPT_DIR}/lib/common.sh"

mkdir -p "$DESIGN_ROOT" "$BUILD_ROOT" "$RESULTS_ROOT" "$QUERY_ROOT"
CHECK_MANIFEST_ARGS=()
if [[ "${USE_NATIVE_ZSTD_KMTRICKS:-0}" == "1" ]]; then
  CHECK_MANIFEST_ARGS=(--allow-zst)
fi
# Captured (not just streamed) to recover the real input sample count
# (files=N) for the input-count-based storage guard below -- real pilot
# data (4 scales, 300-15,000 samples) showed peak build workspace tracks
# input sample count directly (~5.25-6.38 MB/sample, stable across a 50x
# range), not output design size, which the old output-size-only guard
# assumed. See config.env's BUILD_SPACE_PER_SAMPLE_BYTES comment.
CHECK_OUT=$(python3 "$SCRIPT_DIR/check_build_manifest.py" "$BUILD_MANIFEST" "${CHECK_MANIFEST_ARGS[@]}")
echo "$CHECK_OUT"
N_SAMPLES=$(grep -oP '(?<=files=)\d+' <<< "$CHECK_OUT")

BUILD_DIR="${BUILD_ROOT}/${CONFIG_ID}"
DESIGN_DIR="${DESIGN_ROOT}/${CONFIG_ID}"
LOG_DIR="${RESULTS_ROOT}/logs/${CONFIG_ID}"
mkdir -p "$LOG_DIR"

# Avoid silently accumulating old full-scale indexes.
if [[ -d "$BUILD_DIR" ]]; then
  safe_rm_tree "$BUILD_DIR" "$BUILD_ROOT"
fi

FS_AVAIL=$(free_bytes "$PROJECT_ROOT")
QUOTA_HEADROOM=$(quota_headroom_bytes)
AVAIL=$(effective_headroom_bytes)
# max() of the two guard terms, not just the output-size one: real pilot
# data showed peak_build_bytes/estimated_total_bytes drifts (37x->46x
# across scale), so a design with a small estimated output but many input
# samples (e.g. many tiny groups) could pass the old output-only guard
# while still needing real input-driven workspace. The output-size term
# is kept, not dropped -- it's still a real (if less reliable) upper-bound
# signal, and costs nothing to keep as a floor.
REQUIRED=$(python3 - "$EST_TOTAL" "$BUILD_SPACE_FACTOR" "$MIN_FREE_BYTES" "$N_SAMPLES" "$BUILD_SPACE_PER_SAMPLE_BYTES" <<'PY'
import sys
est_total, factor, reserve, n, per_sample = (float(x) for x in sys.argv[1:6])
output_based = est_total * factor
input_based = n * per_sample
print(int(max(output_based, input_based) + reserve))
PY
)
if (( AVAIL < REQUIRED )); then
  echo "ERROR: storage guard failed for $CONFIG_ID" >&2
  echo "effective_available=$AVAIL fs_available=$FS_AVAIL quota_headroom=$QUOTA_HEADROOM required=$REQUIRED estimated_final=$EST_TOTAL factor=$BUILD_SPACE_FACTOR input_samples=$N_SAMPLES per_sample_bytes=$BUILD_SPACE_PER_SAMPLE_BYTES reserve=$MIN_FREE_BYTES" >&2
  exit 10
fi

# Not `YAML=$(design_one_config.sh ...)`: kmhelpers prints its own
# "Done in X.XXs" progress line to stdout (not stderr), which a bare
# command-substitution capture picks up alongside the actual path,
# corrupting $YAML with two lines instead of one. design_one_config.sh
# already persists the real path to a file for exactly this reason --
# read that instead of trusting stdout capture.
"$SCRIPT_DIR/design_one_config.sh" "$CONFIG_ID" "$BASE" "$GROUPS_N"
YAML=$(cat "${DESIGN_DIR}/build_definition.path")
# `kmhelpers build` already runs plan -> apply internally (see `kmhelpers
# build --help`); a separate `kmhelpers plan` call here just repeats the
# planning step for no benefit.

BUILD_TIME="$LOG_DIR/build.time"
DISK_SAMPLES="$LOG_DIR/build_disk_samples.tsv"
DISK_DONE="$LOG_DIR/build_disk_monitor.done"
rm -f "$DISK_DONE"
(
  echo -e "epoch_seconds\tbuild_dir_bytes"
  while [[ ! -e "$DISK_DONE" ]]; do
    B=0
    if [[ -d "$BUILD_DIR" ]]; then B=$(du -sb "$BUILD_DIR" 2>/dev/null | awk '{print $1}' || echo 0); fi
    printf "%s\t%s\n" "$(date +%s)" "$B"
    sleep "$DISK_SAMPLE_SECONDS"
  done
) > "$DISK_SAMPLES" &
MON_PID=$!
set +e
/usr/bin/time -f '%e,%M' -o "$BUILD_TIME" \
  kmhelpers build "$YAML" -o "$BUILD_DIR" -t "$BUILD_THREADS" \
  > "$LOG_DIR/build.stdout" 2> "$LOG_DIR/build.stderr"
RC=$?
set -e
touch "$DISK_DONE"
kill "$MON_PID" 2>/dev/null || true
wait "$MON_PID" 2>/dev/null || true
if [[ -d "$BUILD_DIR" ]]; then printf "%s\t%s\n" "$(date +%s)" "$(du -sb "$BUILD_DIR" | awk '{print $1}')" >> "$DISK_SAMPLES"; fi
if [[ $RC -ne 0 ]]; then
  echo "ERROR: build failed for $CONFIG_ID (rc=$RC); retaining build directory and logs." >&2
  exit $RC
fi

ACTUAL_BYTES=$(du -sb "$BUILD_DIR" | awk '{print $1}')
PEAK_BUILD_BYTES=$(awk 'NR>1 && $2>m {m=$2} END {print m+0}' "$DISK_SAMPLES")
PEAK_FACTOR=$(python3 - "$PEAK_BUILD_BYTES" "$EST_TOTAL" <<'PY'
import sys
est=float(sys.argv[2]); print(float(sys.argv[1])/est if est else 0.0)
PY
)
BUILD_FILES=$(find "$BUILD_DIR" -type f | wc -l)
IFS=, read -r BUILD_SECONDS BUILD_MAXRSS_KB < "$BUILD_TIME"
BUILDS_CSV="$RESULTS_ROOT/builds.csv"
csv_header_once "$BUILDS_CSV" 'phase,config_id,base,groups,estimated_total_bytes,estimated_max_group_bytes,actual_build_bytes,peak_build_bytes,peak_to_estimated_factor,build_files,build_seconds,build_maxrss_kb,effective_available_before_bytes,fs_available_before_bytes,quota_headroom_before_bytes,hostname,storage_label'
printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
  "$PHASE" "$CONFIG_ID" "$BASE" "$GROUPS_N" "$EST_TOTAL" "$EST_MAX" "$ACTUAL_BYTES" "$PEAK_BUILD_BYTES" "$PEAK_FACTOR" "$BUILD_FILES" \
  "$BUILD_SECONDS" "$BUILD_MAXRSS_KB" "$AVAIL" "$FS_AVAIL" "$QUOTA_HEADROOM" "$(hostname)" "$STORAGE_LABEL" >> "$BUILDS_CSV"

TIMINGS="$RESULTS_ROOT/query_timings.csv"
csv_header_once "$TIMINGS" 'phase,config_id,base,groups,estimated_total_bytes,estimated_max_group_bytes,actual_build_bytes,query_length,query_kmers,query_file,repeat,elapsed_seconds,maxrss_kb,query_threads,parallel_mode,zvalue,threshold,cache_policy,hostname,storage_label'

CACHE_POLICY="uncontrolled"
if [[ -n "$CACHE_DROP_CMD" ]]; then
  CACHE_POLICY="configured-drop-command"
fi

case "$PHASE" in
  training) LENGTH_SPEC="$TRAIN_QUERY_LENGTHS" ;;
  validation) LENGTH_SPEC="$VALIDATION_QUERY_LENGTHS" ;;
  extension) LENGTH_SPEC="$EXTENSION_QUERY_LENGTHS" ;;
  *) LENGTH_SPEC="$TRAIN_QUERY_LENGTHS" ;;
esac
IFS=, read -ra LENGTHS <<< "$LENGTH_SPEC"
for L in "${LENGTHS[@]}"; do
  L="${L// /}"
  [[ -n "$L" ]] || continue
  QDIR="$QUERY_ROOT/$L"
  if [[ ! -d "$QDIR" ]]; then
    echo "ERROR: query directory missing: $QDIR; run prepare_queries.py first" >&2
    exit 11
  fi
  mapfile -t QFILES < <(find "$QDIR" -maxdepth 1 -type f -name '*.fa' | sort | head -n "$QUERIES_PER_LENGTH")
  if [[ ${#QFILES[@]} -eq 0 ]]; then
    echo "ERROR: no queries found in $QDIR" >&2
    exit 11
  fi
  QK=$(( L - KMER_SIZE + 1 ))
  if (( QK < 1 )); then QK=1; fi
  for Q in "${QFILES[@]}"; do
    QBASE=$(basename "$Q" .fa)
    for REP in $(seq 1 "$QUERY_REPEATS"); do
      if [[ -n "$CACHE_DROP_CMD" ]]; then
        bash -lc "$CACHE_DROP_CMD"
      fi
      O="${RESULTS_ROOT}/query_output/${CONFIG_ID}/L${L}/${QBASE}/r${REP}"
      mkdir -p "$(dirname "$O")"
      rm -rf "$O"
      TFILE="$LOG_DIR/query_L${L}_${QBASE}_r${REP}.time"
      # Timed via raw `kmindex query`, not `kmhelpers query`: the kmhelpers
      # Python wrapper's own startup/dispatch overhead was previously
      # included in "elapsed_seconds" -- the primary dependent variable for
      # the whole cost-model fit -- contaminating it with a roughly-fixed
      # per-invocation cost that isn't a property of the index/query system
      # itself. `kmindex query`'s registry path (-i) is the same directory
      # `kmhelpers build -o` produced; nothing downstream parses the query
      # output content (only this script's own elapsed-time measurement),
      # so the backend swap doesn't affect anything else. No direct
      # equivalent to kmhelpers query's -P/--parallel (seq/sub) exists at
      # this level -- each built config here resolves to one merged index,
      # so it isn't applicable; $QUERY_PARALLEL is still recorded in the
      # CSV as configured intent, just no longer passed to the query call.
      /usr/bin/time -f '%e,%M' -o "$TFILE" \
        kmindex query -i "$BUILD_DIR" -q "$Q" -o "$O" \
          -t "$QUERY_THREADS" -z "$QUERY_Z" -r "$QUERY_THRESHOLD" \
          > "$LOG_DIR/query_L${L}_${QBASE}_r${REP}.stdout" \
          2> "$LOG_DIR/query_L${L}_${QBASE}_r${REP}.stderr"
      IFS=, read -r ELAPSED MAXRSS < "$TFILE"
      printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
        "$PHASE" "$CONFIG_ID" "$BASE" "$GROUPS_N" "$EST_TOTAL" "$EST_MAX" "$ACTUAL_BYTES" \
        "$L" "$QK" "$Q" "$REP" "$ELAPSED" "$MAXRSS" "$QUERY_THREADS" "$QUERY_PARALLEL" \
        "$QUERY_Z" "$QUERY_THRESHOLD" "$CACHE_POLICY" "$(hostname)" "$STORAGE_LABEL" >> "$TIMINGS"
      # Query result matrices are not needed for the cost model; retain only the first repeat.
      if [[ "$REP" -gt 1 ]]; then rm -rf "$O"; fi
    done
  done
done

if [[ "$KEEP_BUILDS" -eq 0 ]]; then
  safe_rm_tree "$BUILD_DIR" "$BUILD_ROOT"
fi

echo "Completed $CONFIG_ID"
