#!/usr/bin/env bash
#SBATCH --job-name=enum_fullcorpus
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --constraint=avx2
#SBATCH --output=/projects/logan_compression/rsalles/goal2_validation/enumfull-%j.out
#SBATCH --error=/projects/logan_compression/rsalles/goal2_validation/enumfull-%j.err
set -uo pipefail
BUNDLE_ROOT="/projects/logan_compression/rsalles/kmhelpers_logan_paper"
source "$BUNDLE_ROOT/scripts/activate_env.sh"

MANIFEST="/projects/logan_compression/rsalles/span_tuning_paper/manifest/logan_k25.jsonl"
OUTDIR="/projects/logan_compression/rsalles/goal2_validation/fullcorpus_design_space"
mkdir -p "$OUTDIR"
GROUP_SPEC="1-20"
FP=0.25

# Same 12-base grid used for the training-scale design space (config.env's BASES),
# split into 6 parallel workers of 2 bases each to fit a ~2h window instead of ~2h serial.
declare -a CHUNKS=(
  "1.05,1.075"
  "1.10,1.125"
  "1.15,1.20"
  "1.25,1.30"
  "1.40,1.50"
  "1.75,2.00"
)

pids=()
for i in "${!CHUNKS[@]}"; do
  chunk="${CHUNKS[$i]}"
  out="$OUTDIR/chunk_${i}.csv"
  python3 "$BUNDLE_ROOT/scripts/enumerate_designs.py" "$MANIFEST" \
    --bases "$chunk" --groups "$GROUP_SPEC" --fp "$FP" \
    --tmp-root "/tmp/enumfull_${SLURM_JOB_ID}_${i}" \
    --output "$out" > "$OUTDIR/chunk_${i}.log" 2>&1 &
  pids+=($!)
done

fail=0
for pid in "${pids[@]}"; do
  wait "$pid" || fail=1
done

echo "=== per-chunk logs (tail) ==="
for i in "${!CHUNKS[@]}"; do
  echo "--- chunk $i (${CHUNKS[$i]}) ---"
  tail -5 "$OUTDIR/chunk_${i}.log"
done

if [[ "$fail" -ne 0 ]]; then
  echo "ERROR: at least one chunk failed" >&2
  exit 1
fi

# Merge into one real CSV
python3 - "$OUTDIR" <<'PY'
import csv, sys, glob
outdir = sys.argv[1]
files = sorted(glob.glob(f"{outdir}/chunk_*.csv"))
rows = []
fields = None
for f in files:
    with open(f, newline="") as fh:
        r = csv.DictReader(fh)
        if fields is None:
            fields = r.fieldnames
        rows.extend(r)
rows.sort(key=lambda r: (float(r["base"]), int(r["groups"])))
with open(f"{outdir}/design_space_fullcorpus.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
print(f"merged_designs={len(rows)}")
PY
echo "DONE"
