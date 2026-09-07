#!/usr/bin/env bash
#SBATCH --job-name=kmh_cfg
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=3-00:00:00
#SBATCH --output=slurm-%x-%j.out
#SBATCH --error=slurm-%x-%j.err
# Default AVX2 pin for direct `sbatch templates/run_config.sbatch ...` runs.
# submit_matrix_sequential.sh instead passes --constraint from config.env's
# SLURM_CONSTRAINT at submission time (which takes precedence over this
# default when both are present). See kmer_spans docs/agent_context.md's
# node-heterogeneity note for why this matters even with the official,
# portable kmhelpers build: it keeps benchmark timings comparable across
# runs, not just crash-free.
#SBATCH --constraint=avx2
set -euo pipefail

if [[ -z "${BUNDLE_ROOT:-}" ]]; then
  echo "ERROR: BUNDLE_ROOT is not exported" >&2
  exit 2
fi
source "$BUNDLE_ROOT/scripts/activate_env.sh"
"$BUNDLE_ROOT/scripts/check_env.sh"
"$BUNDLE_ROOT/scripts/run_one_config.sh" "$@"
