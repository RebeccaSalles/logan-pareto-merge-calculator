#!/usr/bin/env python3
"""Print selected CSV columns as TSV, in the requested order, looked up by name.

Used by the bash orchestration scripts instead of positional `IFS=,` parsing,
which silently breaks (reads the wrong value into the wrong variable, with no
error) if the source CSV's column order ever changes -- e.g. when
enumerate_designs.py's output is swapped for a different design-space source.

Usage: csv_columns.py FILE.csv col1 col2 col3 ...
Missing values print as an empty field, not an error, so callers can decide
whether an empty field matters. Unknown column names error out immediately.
"""
from __future__ import annotations
import csv
import sys


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: csv_columns.py FILE.csv col1 [col2 ...]", file=sys.stderr)
        sys.exit(2)
    path, cols = sys.argv[1], sys.argv[2:]
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        missing = [c for c in cols if c not in fieldnames]
        if missing:
            print(f"ERROR: column(s) not found in {path}: {missing}. "
                  f"Available: {fieldnames}", file=sys.stderr)
            sys.exit(3)
        for row in reader:
            print("\t".join(row.get(c, "") for c in cols))


if __name__ == "__main__":
    main()
