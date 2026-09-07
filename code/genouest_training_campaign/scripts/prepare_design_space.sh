#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/config.env"
source "${SCRIPT_DIR}/lib/common.sh"
mkdir -p "$MODEL_ROOT"

if [[ ! -s "$MANIFEST" ]]; then
  echo "ERROR: manifest missing: $MANIFEST" >&2
  exit 2
fi
# enumerate_designs.py now calls real `kmhelpers profile` per candidate
# (no reimplemented sizing math) -- it needs kmhelpers on PATH.
if ! command -v kmhelpers >/dev/null 2>&1; then
  echo "ERROR: kmhelpers not on PATH. Run: source ${SCRIPT_DIR}/activate_env.sh" >&2
  exit 2
fi
python3 "$SCRIPT_DIR/enumerate_designs.py" "$MANIFEST" \
  --bases "$BASES" --groups "$GROUP_SPEC" --fp "$FALSE_POSITIVE_RATE" \
  --partitions "$PARTITIONS_FOR_ESTIMATE" --output "$MODEL_ROOT/design_space.csv"

AVAIL=$(effective_headroom_bytes)
MAX_EST=$(python3 - "$AVAIL" "$MIN_FREE_BYTES" "$BUILD_SPACE_FACTOR" <<'PY'
import sys
avail=float(sys.argv[1]); reserve=float(sys.argv[2]); factor=float(sys.argv[3])
print(max(0,int((avail-reserve)/factor)))
PY
)
ARGS=("$SCRIPT_DIR/select_training_configs.py" "$MODEL_ROOT/design_space.csv" --n "$TRAINING_CONFIGS" --max-estimated-bytes "$MAX_EST" --output "$MODEL_ROOT/selected_configs.csv")
if [[ -n "$OLD_BLE_BASE" && -n "$OLD_BLE_GROUPS" ]]; then
  ARGS+=(--manual "${OLD_BLE_BASE}:${OLD_BLE_GROUPS}")
fi
python3 "${ARGS[@]}"
echo "available_bytes=$AVAIL"
echo "max_estimated_final_bytes=$MAX_EST"
