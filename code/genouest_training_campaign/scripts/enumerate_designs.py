#!/usr/bin/env python3
"""Enumerate kmhelpers-compatible base/group designs by calling REAL kmhelpers.

This deliberately does NOT reimplement kmhelpers' Bloom-filter sizing or
grouping algorithm. An earlier version of this script did, and that's a real
risk for a paper claiming "cheap enumeration predicts what real builds would
produce" -- any drift between a hand-derived formula and what kmhelpers
actually does undermines that claim. Instead, for every (base, groups)
candidate this calls `kmhelpers profile` on the already-counted manifest
(cheap: profile reads pre-computed kmer_count values, it does not rescan
FASTA) and parses its real profile.yaml output.

Verified profile.yaml schema (2026-08-24, kmhelpers v0.6.3, against a real
run -- see kmer_spans docs/implementation_log.md):

    default_profile: <N>_groups
    sample_count: <int>
    profiles:
      baseline:
        span_list: [...]        # one entry per natural span
        sample_dist: [...]      # samples per span
        disk_usage: [1.23e+07B, ...]   # bytes per span, "B"-suffixed (not plain YAML numerics)
        total_size: 4.56e+07B
      <N>_groups:
        span_list: [...]        # one representative span per GROUP (post-merge)
        sample_dist: [...]      # samples per group
        disk_usage: [...]       # bytes per group
        total_size: ...B        # sum of the group bytes above

Requires `kmhelpers` to be on PATH (source scripts/activate_env.sh first).
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def parse_float_list(s: str) -> list[float]:
    return [float(x.strip()) for x in s.split(",") if x.strip()]


def parse_int_spec(s: str) -> list[int]:
    vals = set()
    for token in s.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            a, b = token.split("-", 1)
            vals.update(range(int(a), int(b) + 1))
        else:
            vals.add(int(token))
    return sorted(vals)


_NUM_B = re.compile(r"[-+0-9.eE]+(?=B?\s*$)")


def _strip_b(token: str) -> float:
    """Parse a possibly 'B'-suffixed scalar like '1.23e+07B' or '1.23e+07'."""
    token = token.strip().rstrip(",")
    m = _NUM_B.search(token)
    if not m:
        raise ValueError(f"cannot parse numeric token: {token!r}")
    return float(m.group(0))


def _parse_list_field(raw: str) -> list[str]:
    """Parse a flow-style YAML list '[a, b, c]' into its raw string items."""
    raw = raw.strip()
    if not (raw.startswith("[") and raw.endswith("]")):
        raise ValueError(f"expected a flow-style list, got: {raw!r}")
    inner = raw[1:-1].strip()
    if not inner:
        return []
    # Simple split is safe here: profile.yaml's list items never contain commas
    # themselves (numbers, bare span ints, or quoted decimal strings).
    return [x.strip() for x in inner.split(",")]


def parse_profile_yaml(path: Path) -> dict:
    """Minimal targeted parser for kmhelpers' profile.yaml.

    Not a general YAML parser -- profile.yaml's numeric fields ("1.23e+07B")
    are not valid plain-YAML scalars, so a general parser (PyYAML et al.)
    would need custom handling anyway. This walks the known, simple,
    two-level structure directly.
    """
    text = path.read_text()
    lines = text.splitlines()
    n = len(lines)

    top: dict = {}
    profiles: dict[str, dict] = {}
    current_profile: str | None = None
    in_profiles = False

    i = 0
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if indent == 0:
            in_profiles = stripped == "profiles:"
            if not in_profiles and ":" in stripped:
                key, _, val = stripped.partition(":")
                top[key.strip()] = val.strip()
            i += 1
            continue

        if in_profiles and indent == 2 and stripped.endswith(":"):
            current_profile = stripped[:-1].strip()
            profiles[current_profile] = {}
            i += 1
            continue

        if in_profiles and current_profile is not None and indent >= 4 and ":" in stripped:
            key, _, val = stripped.partition(":")
            key, val = key.strip(), val.strip()
            # A flow-style list ("[a, b, ...]") that the YAML writer wrapped
            # across multiple physical lines (real, not hypothetical: base=1.05
            # alone can produce 100+ baseline span_list entries, well past a
            # typical ~80-col wrap width) starts with "[" but has no matching
            # "]" yet on this line. Keep consuming continuation lines (plain
            # comma-separated value text, no "key:" of their own) until the
            # list actually closes. Previously this silently truncated to the
            # first line, producing a malformed, unclosed value that either
            # raised downstream or (worse, actually observed) got misread as
            # a wildly-inflated bogus count -- fail loudly on a genuinely
            # malformed file instead, not silently truncate.
            if val.startswith("[") and "]" not in val:
                j = i + 1
                while j < n and "]" not in val:
                    val += " " + lines[j].strip()
                    j += 1
                i = j
                profiles[current_profile][key] = val
                continue
            profiles[current_profile][key] = val
            i += 1
            continue

        i += 1

    return {"top": top, "profiles": profiles}


def profile_summary(profile: dict) -> dict:
    """Extract the numbers enumerate_designs.py needs from one profile entry."""
    span_list = [int(x) for x in _parse_list_field(profile["span_list"])]
    sample_dist = [int(x) for x in _parse_list_field(profile["sample_dist"])]
    disk_usage = [_strip_b(x) for x in _parse_list_field(profile["disk_usage"])]
    total_size = _strip_b(profile["total_size"])
    return {
        "span_list": span_list,
        "sample_dist": sample_dist,
        "disk_usage_bytes": disk_usage,
        "total_size_bytes": total_size,
    }


def run_profile(kmhelpers_bin: str, manifest: str, base: float, groups: int, fp: float, tmp_root: Path) -> dict:
    out_dir = Path(tempfile.mkdtemp(prefix=f"profile_b{base}_g{groups}_", dir=tmp_root))
    try:
        cmd = [kmhelpers_bin, "profile", manifest, "-o", str(out_dir), "-g", str(groups), "-b", str(base), "-fp", str(fp)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"kmhelpers profile failed (base={base}, groups={groups}): {proc.stderr[-2000:]}")
        parsed = parse_profile_yaml(out_dir / "profile.yaml")
        default_profile = parsed["top"]["default_profile"]
        baseline = parsed["profiles"]["baseline"]
        requested = parsed["profiles"][default_profile]
        return {
            "sample_count": int(parsed["top"]["sample_count"]),
            "natural_spans": len(_parse_list_field(baseline["span_list"])),
            "requested": profile_summary(requested),
        }
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def row_for(kmhelpers_bin: str, manifest: str, base: float, requested_groups: int, fp: float, tmp_root: Path, label: str = "grid") -> dict:
    result = run_profile(kmhelpers_bin, manifest, base, requested_groups, fp, tmp_root)
    r = result["requested"]
    groups = len(r["sample_dist"])
    costs = r["disk_usage_bytes"]
    total = r["total_size_bytes"]
    max_cost = max(costs)
    mean = total / groups if groups else 0.0
    cv = (math.sqrt(sum((x - mean) ** 2 for x in costs) / len(costs)) / mean) if mean and costs else 0.0
    return {
        "config_id": f"b{str(base).replace('.', 'p')}_g{groups:02d}",
        "base": base,
        "requested_groups": requested_groups,
        "groups": groups,
        "natural_spans": result["natural_spans"],
        "sample_count": result["sample_count"],
        "total_size_bytes": total,
        "max_group_size_bytes": max_cost,
        "mean_group_size_bytes": mean,
        "group_size_cv": cv,
        "min_span": min(r["span_list"]) if r["span_list"] else "",
        "max_span": max(r["span_list"]) if r["span_list"] else "",
        "group_boundaries": ";".join(str(s) for s in r["span_list"]),
        "group_samples": ";".join(str(s) for s in r["sample_dist"]),
        "group_sizes_bytes": ";".join(str(int(c)) for c in costs),
        "kind": label,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--bases", required=True)
    ap.add_argument("--groups", required=True)
    ap.add_argument("--fp", type=float, default=0.25)
    ap.add_argument("--partitions", type=int, default=256, help="kept for CLI compatibility; kmhelpers profile does not take a partition count")
    ap.add_argument("--kmhelpers", default="kmhelpers", help="kmhelpers executable (default: whatever's on PATH -- run via activate_env.sh)")
    ap.add_argument("--tmp-root", default="", help="scratch dir for per-call profile output (default: system tmp)")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    kmhelpers_bin = shutil.which(args.kmhelpers) or args.kmhelpers
    if not shutil.which(kmhelpers_bin):
        raise SystemExit(f"kmhelpers not found ({args.kmhelpers}); source scripts/activate_env.sh first")

    tmp_root = Path(args.tmp_root) if args.tmp_root else Path(tempfile.gettempdir())
    tmp_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for base in parse_float_list(args.bases):
        seen_g: set[int] = set()
        natural_spans_for_base = None
        for requested in parse_int_spec(args.groups):
            r = row_for(kmhelpers_bin, args.manifest, base, requested, args.fp, tmp_root)
            natural_spans_for_base = r["natural_spans"]
            if r["groups"] not in seen_g:
                rows.append(r)
                seen_g.add(r["groups"])
        if natural_spans_for_base is not None and natural_spans_for_base not in seen_g:
            natural = row_for(kmhelpers_bin, args.manifest, base, natural_spans_for_base, args.fp, tmp_root, label="natural")
            rows.append(natural)
        elif natural_spans_for_base is not None:
            for r in rows:
                if r["base"] == base and r["groups"] == natural_spans_for_base:
                    r["kind"] = "grid+natural"

    if not rows:
        raise SystemExit("no designs produced")

    rows.sort(key=lambda r: (r["base"], r["groups"]))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"designs={len(rows)}")
    print(f"output={out}")
    best_total = min(rows, key=lambda r: r["total_size_bytes"])
    best_max = min(rows, key=lambda r: r["max_group_size_bytes"])
    print(f"min_total={best_total['config_id']} {best_total['total_size_bytes']} bytes")
    print(f"min_max_group={best_max['config_id']} {best_max['max_group_size_bytes']} bytes")


if __name__ == "__main__":
    main()
