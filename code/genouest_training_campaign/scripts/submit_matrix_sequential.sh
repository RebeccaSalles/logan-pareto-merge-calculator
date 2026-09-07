#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/config.env"
CSV="${1:-${MODEL_ROOT}/selected_configs.csv}"
PHASE="${2:-training}"
TEMPLATE="${ROOT_DIR}/templates/run_config.sbatch"
if [[ ! -s "$CSV" ]]; then echo "ERROR: missing $CSV" >&2; exit 2; fi

PREV=""
# Read columns by NAME (not position) -- see lib/csv_columns.py's docstring.
while IFS=$'\t' read -r config_id base groups total_size_bytes max_group_size_bytes; do
  [[ -n "$config_id" ]] || continue
  DEP=()
  if [[ -n "$PREV" ]]; then DEP=(--dependency="afterok:${PREV}"); fi
  CONSTRAINT=()
  if [[ -n "${SLURM_CONSTRAINT:-}" ]]; then CONSTRAINT=(--constraint="$SLURM_CONSTRAINT"); fi
  OUT=$(sbatch --parsable "${DEP[@]}" "${CONSTRAINT[@]}" \
    --job-name="kmh_${config_id}" \
    --cpus-per-task="$BUILD_THREADS" \
    --export="ALL,BUNDLE_ROOT=${ROOT_DIR}" \
    "$TEMPLATE" "$config_id" "$base" "$groups" "$total_size_bytes" "$max_group_size_bytes" "$PHASE")
  JOBID="${OUT%%;*}"
  echo "$config_id -> $JOBID${PREV:+ after $PREV}"
  PREV="$JOBID"
done < <(python3 "$SCRIPT_DIR/lib/csv_columns.py" "$CSV" config_id base groups total_size_bytes max_group_size_bytes)
