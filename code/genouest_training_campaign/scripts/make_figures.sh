#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/config.env"
python3 "$SCRIPT_DIR/plot_results.py" "$MODEL_ROOT/design_space.csv" "$MODEL_ROOT/fit/aggregated_timings.csv" "$MODEL_ROOT/fit/training_predictions.csv" --output-dir "$RESULTS_ROOT/figures"
