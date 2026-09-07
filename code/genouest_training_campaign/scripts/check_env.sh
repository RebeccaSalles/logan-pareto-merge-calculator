#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/config.env"

mkdir -p "${RESULTS_ROOT}"
OUT="${RESULTS_ROOT}/provenance_$(date +%Y%m%d_%H%M%S).txt"

{
  echo "date=$(date --iso-8601=seconds 2>/dev/null || date)"
  echo "hostname=$(hostname)"
  echo "pwd=$(pwd)"
  echo "project_root=${PROJECT_ROOT}"
  echo "ecoli_root=${ECOLI_ROOT}"
  echo "raw_root=${RAW_ROOT}"
  echo "work_root=${WORK_ROOT}"
  echo "project_quota_bytes=${PROJECT_QUOTA_BYTES}"
  echo "raw_corpus_bytes=${RAW_CORPUS_BYTES}"
  echo "static_other_bytes=${STATIC_OTHER_BYTES}"
  echo "kmer_size=${KMER_SIZE}"
  echo "false_positive_rate=${FALSE_POSITIVE_RATE}"
  echo
  echo "== OS =="
  uname -a || true
  echo
  echo "== CPU =="
  lscpu 2>/dev/null || true
  echo
  echo "== MEMORY =="
  free -h 2>/dev/null || true
  echo
  echo "== FILESYSTEM =="
  df -h "${PROJECT_ROOT}" 2>/dev/null || true
  df -T "${PROJECT_ROOT}" 2>/dev/null || true
  echo
  echo "== TOOL VERSIONS =="
  kmhelpers --version 2>&1 || true
  kmhelpers about 2>&1 || true
  kmindex --version 2>&1 || true
  kmtricks --version 2>&1 || true
  ntcard --version 2>&1 || true
  zstd --version 2>&1 | head -1 || true
  python3 --version 2>&1 || true
  echo
  echo "== KMHELPERS GIT =="
  if [[ -d "${KMHELPERS_REPO}/.git" ]]; then
    git -C "${KMHELPERS_REPO}" status --short --branch || true
    git -C "${KMHELPERS_REPO}" rev-parse HEAD || true
  fi
} | tee "${OUT}"

echo "Wrote ${OUT}"
