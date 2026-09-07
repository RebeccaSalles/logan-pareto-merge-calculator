#!/usr/bin/env bash
set -euo pipefail

safe_rm_tree() {
  local target="$1"
  local allowed_root="$2"
  local rt ra
  rt="$(realpath -m "$target")"
  ra="$(realpath -m "$allowed_root")"
  case "$rt" in
    "$ra"/*) rm -rf -- "$rt" ;;
    *) echo "ERROR: refusing rm outside $ra: $rt" >&2; return 99 ;;
  esac
}

csv_header_once() {
  local file="$1"
  local header="$2"
  if [[ ! -s "$file" ]]; then
    printf '%s\n' "$header" > "$file"
  fi
}

free_bytes() {
  df -B1 --output=avail "$1" | tail -n 1 | tr -d ' '
}

work_used_bytes() {
  # `du -sb "$WORK_ROOT"` gets slow once many small result/log files
  # accumulate (this project has already hit multi-minute `du`/`find` hangs
  # on directories with millions of entries -- see kmer_spans
  # docs/agent_context.md's node-heterogeneity/millions-of-files notes).
  # Cache the measurement for CACHE_TTL_SECONDS instead of re-du-ing on
  # every call; headroom does not need sub-cache-window precision, and a
  # stale-by-a-few-minutes number is far cheaper than a `du` on every check.
  local cache_file="${WORK_ROOT}/.work_used_bytes_cache"
  local cache_ttl_seconds="${WORK_USED_CACHE_TTL_SECONDS:-600}"
  local now cached_at cached_val
  now=$(date +%s)
  if [[ -f "$cache_file" ]]; then
    read -r cached_at cached_val < "$cache_file" 2>/dev/null || true
    if [[ -n "${cached_at:-}" && -n "${cached_val:-}" && $((now - cached_at)) -lt "$cache_ttl_seconds" ]]; then
      echo "$cached_val"
      return 0
    fi
  fi
  local work_used=0
  if [[ -d "${WORK_ROOT}" ]]; then
    work_used=$(du -sb "${WORK_ROOT}" 2>/dev/null | awk '{print $1}')
  fi
  printf '%s %s\n' "$now" "$work_used" > "$cache_file" 2>/dev/null || true
  echo "$work_used"
}

quota_headroom_bytes() {
  local work_used
  work_used=$(work_used_bytes)
  python3 - "${PROJECT_QUOTA_BYTES}" "${RAW_CORPUS_BYTES}" "${STATIC_OTHER_BYTES}" "$work_used" <<'PY'
import sys
print(max(0, int(float(sys.argv[1])-float(sys.argv[2])-float(sys.argv[3])-float(sys.argv[4]))))
PY
}

effective_headroom_bytes() {
  local fs q
  fs=$(free_bytes "${PROJECT_ROOT}")
  q=$(quota_headroom_bytes)
  if (( fs < q )); then echo "$fs"; else echo "$q"; fi
}

sanitize_base() {
  printf '%s' "$1" | sed 's/\./p/g; s/[^A-Za-z0-9_-]/_/g'
}
