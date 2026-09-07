#!/usr/bin/env bash
# Verify the pre-built kmhelpers v0.6.3 environment -- does NOT install or
# rebuild anything.
#
# This project reuses the official v0.6.3 conda environment already built
# and verified under rsalles/ on 2026-08-24 (conda env create -f
# conda/environment.yml from the official v0.6.3 tag; pulls bioconda kmindex
# 0.6.1, kmtricks 1.6.0). That environment is portable across AVX2 and
# non-AVX2 compute nodes -- confirmed by direct testing on both.
#
# The upstream v0.6.3 repo also ships scripts/setup.sh, which builds
# kmindex/kmtricks FROM SOURCE. Do not use it: it was needed only while
# bioconda's kmindex lagged the static_repart feature (true as of the
# colleague's 2026-07-03 email), which bioconda has since caught up on
# (kmindex 0.6.1, uploaded 2026-07-09). A from-source build also risks
# reintroducing the exact non-portability problem (SIGILL on some compute
# nodes) that made the colleague's own manual beta build unreliable here.
#
# If this environment ever needs to be rebuilt from scratch, use the plain
# conda path, not scripts/setup.sh:
#   git clone --branch v0.6.3 --depth 1 https://github.com/sebllns/kmhelpers <dir>
#   cd <dir> && conda env create -f conda/environment.yml -p ./.env
# (run via srun on a compute node; the login node refuses env setup).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/config.env"

if [[ ! -d "${KMHELPERS_ENV}" ]]; then
  echo "ERROR: KMHELPERS_ENV does not exist: ${KMHELPERS_ENV}" >&2
  echo "This script only verifies an existing environment; it does not build one." >&2
  echo "See the comment block at the top of this file for how to build one if needed." >&2
  exit 2
fi

source "${SCRIPT_DIR}/activate_env.sh"

echo "== kmhelpers =="
kmhelpers --version
echo "== kmindex (must be >= 0.6.1 for --static-repart support) =="
kmindex --version
echo "== kmtricks =="
kmtricks --version
echo "== ntcard =="
ntcard --version

KMINDEX_VER="$(kmindex --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
if [[ -n "${KMINDEX_VER}" ]]; then
  IFS=. read -r maj min _ <<< "${KMINDEX_VER}"
  if (( maj == 0 && min < 6 )); then
    echo "WARNING: kmindex ${KMINDEX_VER} is older than 0.6.1 -- --static-repart may not work." >&2
  fi
fi

echo "Environment OK: ${KMHELPERS_ENV}"
