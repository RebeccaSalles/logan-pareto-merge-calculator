#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/config.env"
CSV="${MODEL_ROOT}/validation_configs.csv"
"$SCRIPT_DIR/run_training_matrix.sh" "$CSV" validation
python3 "$SCRIPT_DIR/evaluate_validation.py" "$RESULTS_ROOT/query_timings.csv" "$MODEL_ROOT/fit/cost_models.json" --output "$MODEL_ROOT/validation_predictions.csv"
