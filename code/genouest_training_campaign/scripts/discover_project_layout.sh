#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/config.env"

# unitigs_spans_20/ holds ~7 million files; `du`/`find` over it have already
# caused multi-minute-to-hung commands elsewhere in this project (see
# kmer_spans docs/agent_context.md). Exclude it explicitly rather than
# discovering that the hard way again -- its size/contents are already
# known and documented in kmer_spans results/latest_profile_summary.md.
EXCLUDE_DIRS=("unitigs_spans_20")

echo "== Top-level usage under ${PROJECT_ROOT} (excluding: ${EXCLUDE_DIRS[*]}) =="
for entry in "${PROJECT_ROOT}"/*; do
  name="$(basename "$entry")"
  skip=0
  for ex in "${EXCLUDE_DIRS[@]}"; do
    [[ "$name" == "$ex" ]] && skip=1
  done
  if [[ "$skip" -eq 1 ]]; then
    echo "(skipped, known large: $entry)"
    continue
  fi
  timeout 30 du -sh "$entry" 2>/dev/null || echo "(du timed out or failed: $entry)"
done | sort -h || true

PRUNE_ARGS=()
for ex in "${EXCLUDE_DIRS[@]}"; do
  PRUNE_ARGS+=(-path "${PROJECT_ROOT}/${ex}" -prune -o)
done

echo
echo "== Likely experiment/data directories (depth <= 3) =="
timeout 60 find "${PROJECT_ROOT}" "${PRUNE_ARGS[@]}" -maxdepth 3 -type d -print 2>/dev/null | grep -Ei '/(ble|ecoli|span|unitig|raw|download|index|bench)' | sort || echo "(find timed out; try a narrower --root)"

echo
echo "== Representative sequence files =="
timeout 60 find "${PROJECT_ROOT}" "${PRUNE_ARGS[@]}" -maxdepth 4 -type f \( -name '*.zst' -o -name '*.fa.gz' -o -name '*.fasta.gz' -o -name '*.fna.gz' -o -name '*.fa' -o -name '*.fasta' -o -name '*.fna' \) -print 2>/dev/null | head -n 40 || echo "(find timed out; try a narrower --root)"

echo
echo "== Existing benchmark-like files =="
find "${PROJECT_ROOT}" -maxdepth 4 -type f \( -name '*.csv' -o -name '*.tsv' -o -name '*.out' -o -name '*.jsonl' -o -name '*.yaml' \) 2>/dev/null | grep -Ei '(ble|bench|merge|span|query|download|unitig)' | head -n 80 || true
