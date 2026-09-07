#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 3 ]]; then
  echo "usage: $0 CONFIG_ID BASE GROUPS" >&2
  exit 2
fi
CONFIG_ID="$1"; BASE="$2"; GROUPS_N="$3"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/config.env"
source "${SCRIPT_DIR}/lib/common.sh"

D="${DESIGN_ROOT}/${CONFIG_ID}"
safe_rm_tree "$D" "$DESIGN_ROOT" || true
mkdir -p "$D"

kmhelpers design "${BUILD_MANIFEST}" \
  -o "$D" -n "$CONFIG_ID" -S eval -k "$KMER_SIZE" \
  -dt "$DATA_TYPE" -b "$BASE" -g "$GROUPS_N" -fp "$FALSE_POSITIVE_RATE"

YAML=$(find "$D/compose" -type f -name "${CONFIG_ID}.yaml" -print -quit 2>/dev/null || true)
if [[ -z "$YAML" ]]; then
  YAML=$(find "$D/compose" -type f -name '*.yaml' ! -name '*layout*' -print -quit 2>/dev/null || true)
fi
if [[ -z "$YAML" ]]; then
  echo "ERROR: no build definition YAML found below $D/compose" >&2
  exit 3
fi
printf '%s\n' "$YAML" > "$D/build_definition.path"
printf '%s\n' "$YAML"
