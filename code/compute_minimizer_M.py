#!/usr/bin/env python3
"""Compute M(L): the number of distinct kmtricks minimizers in a query
sequence, using an exact line-for-line Python port of kmtricks' real
minimizer selection (include/kmtricks/kmer.hpp, Kmer<32>::minimizer()) --
not a generic/approximate canonical-minimizer scheme.

Ported from the real kmtricks source (tlemane/kmtricks, master branch,
include/kmtricks/kmer.hpp). Encoding is kmtricks' own: A=0, C=1, T=2,
G=3 (NOT alphabetical) -- verified directly against the real NToB[256]
lookup table in that file.

Usage:
    python3 compute_minimizer_M.py data/query_examples/*.fa -k 25 -m 10
"""
import argparse
from pathlib import Path

NTOB = {65: 0, 67: 1, 71: 3, 84: 2, 97: 0, 99: 1, 103: 3, 116: 2}  # A C G T, upper/lower
REVB = {0: 2, 1: 3, 2: 0, 3: 1}
MASK32 = 0xFFFFFFFF


def is_valid_minimizer(value: int, size: int) -> bool:
    """Real GATB/DSK-derived poly-A exclusion filter (kmer.hpp:77-85)."""
    mask1 = MASK32 >> ((32 - (size * 2)) + 4)
    mask01 = 0x55555555
    mask00 = mask01 & mask1
    value = (~(value | (value >> 2))) & MASK32
    value = ((value >> 1) & value) & mask00
    return value == 0


def kmer_minimizer(kmer_2bit, m: int) -> int:
    """Port of Kmer<32>::minimizer(), kmer.hpp:591-629.
    kmer_2bit: list of 2-bit codes for one k-mer, forward orientation."""
    k = len(kmer_2bit)
    default_val = (1 << (2 * m)) - 1
    nb_mmers = k - m + 1
    minim = MASK32  # numeric_limits<uint32_t>::max()
    for i in range(nb_mmers):
        value = 0
        for j in range(i, i + m):
            value = (value << 2) | kmer_2bit[j]
        rev = 0
        tmp = value
        for _ in range(m):
            rev = (rev << 2) | REVB[tmp & 3]
            tmp >>= 2
        canon = rev if rev < value else value
        if is_valid_minimizer(canon, m):
            if canon < minim:
                minim = canon
        else:
            if default_val < minim:
                minim = default_val
    return minim


def distinct_minimizers(seq: str, k: int, m: int) -> int:
    seq = seq.strip().upper()
    codes = [NTOB[ord(c)] for c in seq if ord(c) in NTOB]
    n = len(codes)
    seen = set()
    for i in range(n - k + 1):
        seen.add(kmer_minimizer(codes[i:i + k], m))
    return len(seen)


def read_fasta_seq(path: Path) -> str:
    lines = [l.strip() for l in path.read_text().splitlines() if l.strip() and not l.startswith(">")]
    return "".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fasta", nargs="+", help="query FASTA file(s)")
    ap.add_argument("-k", type=int, default=25)
    ap.add_argument("-m", type=int, default=10)
    ap.add_argument("--lengths", default="250,500,1000", help="query prefix lengths to test, comma-separated")
    args = ap.parse_args()
    lengths = [int(x) for x in args.lengths.split(",")]

    print(f"k={args.k} m={args.m}\n")
    for L in lengths:
        Ms = []
        print(f"L={L}bp:")
        for path in args.fasta:
            seq = read_fasta_seq(Path(path))
            if len(seq) < L:
                continue
            M = distinct_minimizers(seq[:L], args.k, args.m)
            Ms.append(M)
            print(f"  {Path(path).name}: M={M}")
        if Ms:
            print(f"  -> mean={sum(Ms)/len(Ms):.1f}  range {min(Ms)}-{max(Ms)}\n")


if __name__ == "__main__":
    main()
