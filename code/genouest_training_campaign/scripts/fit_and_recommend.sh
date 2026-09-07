#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/config.env"
source "${SCRIPT_DIR}/lib/common.sh"
mkdir -p "$MODEL_ROOT/fit" "$MODEL_ROOT/recommendation"
python3 "$SCRIPT_DIR/fit_cost_model.py" "$RESULTS_ROOT/query_timings.csv" --output-dir "$MODEL_ROOT/fit" --seed "$RANDOM_SEED"

AVAIL=$(effective_headroom_bytes)
MAX_EST=$(python3 - "$AVAIL" "$MIN_FREE_BYTES" "$BUILD_SPACE_FACTOR" <<'PY'
import sys
print(max(0,int((float(sys.argv[1])-float(sys.argv[2]))/float(sys.argv[3]))))
PY
)
python3 "$SCRIPT_DIR/recommend_config.py" "$MODEL_ROOT/design_space.csv" "$MODEL_ROOT/fit/cost_models.json" \
  --query-length 1000 --max-total-bytes "$MAX_EST" --output-dir "$MODEL_ROOT/recommendation"

OLD=""
if [[ -n "$OLD_BLE_BASE" && -n "$OLD_BLE_GROUPS" ]]; then OLD="${OLD_BLE_BASE}:${OLD_BLE_GROUPS}"; fi
ARGS=("$SCRIPT_DIR/make_validation_configs.py" "$MODEL_ROOT/design_space.csv" "$MODEL_ROOT/recommendation/recommendation.json" --training-csv "$MODEL_ROOT/selected_configs.csv" --ranked-csv "$MODEL_ROOT/recommendation/ranked_configs.csv" --output "$MODEL_ROOT/validation_configs.csv")
if [[ -n "$OLD" ]]; then ARGS+=(--old-ble "$OLD"); fi
python3 "${ARGS[@]}"
