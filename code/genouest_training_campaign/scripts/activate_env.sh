#!/usr/bin/env bash
# Source this file:  source scripts/activate_env.sh
#
# Activates the kmhelpers environment configured in config.env
# (KMHELPERS_ENV). Must run on a Genouest *compute* node (via srun/sbatch) --
# the login node refuses to run environment/conda setup at all
# ("Sorry, no execution allowed on this machine, please connect to a compute
# node"). Verified 2026-08-24 against the official v0.6.3 env under rsalles/.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/config.env"

# envconda.sh and conda's own hook scripts reference variables that may be
# unset and use internal non-zero-returning control flow (e.g. a `grep`
# that legitimately finds no match) as part of normal operation. Simply not
# writing `set -e`/`set -u` in THIS file is not enough: `source` runs in
# the current shell, not a subshell, so a caller's own `set -e`/`set -u`
# (e.g. templates/run_config.sbatch's `set -euo pipefail`) is still active
# while this file executes and still aborts on the first such non-zero
# return -- confirmed directly: a real `sbatch` submission of
# run_config.sbatch died right here, silently, with empty stdout/stderr log
# files (the failure happens before any of this project's own code prints
# anything). So the caller's strict-mode flags are explicitly saved and
# relaxed for this section, then restored afterward, regardless of what the
# caller had set.
_activate_env_prev_opts="$(set +o | grep -E 'errexit|nounset|pipefail')"
set +euo pipefail
#
# Genouest-specific bootstrap: puts conda/mamba on PATH. Required before
# `conda activate` will work at all on this cluster -- confirmed by direct
# testing; skipping this step fails with "conda: command not found".
source /local/env/envconda.sh
conda activate "${KMHELPERS_ENV}"
eval "$_activate_env_prev_opts"
unset _activate_env_prev_opts

# Native-.zst kmtricks (H9, see config.env) -- prepend so `which kmtricks`
# resolves to it instead of the env's own bioconda kmtricks. This is the
# only reliable way to select it: `kindex build --km-path` looks like the
# documented mechanism but its actual implementation only uses that path
# as a fallback when no kmtricks is already on $PATH, which is never true
# once the env above is activated -- confirmed directly, not assumed, see
# kmer_spans docs/implementation_log.md's sixteenth-pass entry.
if [[ "${USE_NATIVE_ZSTD_KMTRICKS:-0}" == "1" ]]; then
  export PATH="${NATIVE_ZSTD_KMTRICKS_BIN_DIR}:${PATH}"
fi
