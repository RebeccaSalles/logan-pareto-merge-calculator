#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/config.env"

CSV="${1:-${MODEL_ROOT}/selected_configs.csv}"
PHASE="${2:-training}"
if [[ ! -s "$CSV" ]]; then
  echo "ERROR: selected config CSV not found: $CSV" >&2
  exit 2
fi
mkdir -p "$RESULTS_ROOT"

# Sequential on purpose: never keep multiple large builds alive.
# Read columns by NAME (not position) -- see lib/csv_columns.py's docstring
# for why: positional `IFS=,` parsing silently breaks if the CSV's column
# order ever changes.
python3 "$SCRIPT_DIR/lib/csv_columns.py" "$CSV" config_id base groups total_size_bytes max_group_size_bytes |
while IFS=$'\t' read -r config_id base groups total_size_bytes max_group_size_bytes; do
  [[ -n "$config_id" ]] || continue
  "$SCRIPT_DIR/run_one_config.sh" "$config_id" "$base" "$groups" "$total_size_bytes" "$max_group_size_bytes" "$PHASE"
done
