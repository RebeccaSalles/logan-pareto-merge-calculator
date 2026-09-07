#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/config.env"

OUT="${WORK_ROOT}/smoke_ecoli"
DESIGN="${OUT}/design"
BUILD="${OUT}/build"
RESULTS="${OUT}/results"
LIST="${OUT}/ecoli_files.txt"
QUERY="${OUT}/query.fa"
rm -rf "${OUT}"
mkdir -p "${OUT}"

if [[ ! -d "${ECOLI_ROOT}" ]]; then
  echo "ERROR: E. coli directory does not exist: ${ECOLI_ROOT}" >&2
  exit 2
fi

find "${ECOLI_ROOT}" -type f \( \
  -name '*.fa' -o -name '*.fa.gz' -o -name '*.fna' -o -name '*.fna.gz' -o \
  -name '*.fasta' -o -name '*.fasta.gz' \
\) | sort > "${LIST}"

N=$(wc -l < "${LIST}")
if [[ "${N}" -eq 0 ]]; then
  echo "ERROR: no supported E. coli FASTA files found in ${ECOLI_ROOT}" >&2
  exit 2
fi

echo "E. coli files: ${N}"
kmhelpers design "${LIST}" -o "${DESIGN}" -n ecoli_smoke -S initial -k 25 -b 1.1 -g 2

YAML=$(find "${DESIGN}/compose" -type f -name 'ecoli_smoke.yaml' -print -quit)
if [[ -z "${YAML}" ]]; then
  YAML=$(find "${DESIGN}/compose" -type f -name '*.yaml' ! -name '*layout*' -print -quit)
fi
if [[ -z "${YAML}" ]]; then
  echo "ERROR: could not locate compose YAML under ${DESIGN}/compose" >&2
  exit 3
fi

# `kmhelpers build` already runs plan -> apply internally; no separate
# `kmhelpers plan` call needed.
kmhelpers build "${YAML}" -o "${BUILD}" -t 4

FIRST=$(head -n 1 "${LIST}")
case "${FIRST}" in
  *.gz) READER=(gzip -dc "${FIRST}") ;;
  *) READER=(cat "${FIRST}") ;;
esac
"${READER[@]}" | awk '/^>/{if (seen) exit; seen=1} {print}' > "${QUERY}"

kmhelpers query -r "${BUILD}" -o "${RESULTS}" -t 1 -z 6 -R 0.05 "${QUERY}"

echo "Smoke test completed: ${OUT}"
