#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/config.env"
CSV="${MODEL_ROOT}/extension_configs.csv"
python3 "$SCRIPT_DIR/make_extension_configs.py" "$MODEL_ROOT/design_space.csv" "$MODEL_ROOT/recommendation/recommendation.json" --output "$CSV"
"$SCRIPT_DIR/run_training_matrix.sh" "$CSV" extension
python3 "$SCRIPT_DIR/fit_cost_model.py" "$RESULTS_ROOT/query_timings.csv" --phase extension --output-dir "$MODEL_ROOT/fit_extension" --seed "$RANDOM_SEED"
