# Reproducing this benchmark

Three real, separate stages produced the numbers in the report. They
have different reproducibility stories — this page is honest about
which is which rather than claiming one blanket "reproducible."

## Stage 1 — Score the designs (fully reproducible from this repo alone)

Given the raw `kmhelpers profile` CSVs already checked into
[`data/`](data/), `code/score_designs.py` recomputes every score with
no external dependency beyond the Python standard library:

```bash
python3 code/score_designs.py data/span_le20/design_space_span_le20.csv   out/span_le20
python3 code/score_designs.py data/full_logan/design_space_full_logan.csv out/full_logan
```

**Verified**: run against a fresh clone, this reproduces
`data/*/scored_designs_*.json` exactly — every one of the 250 + 252 =
502 designs, every field (`s`, `m`, `np_min`, `np_max`, `score250`,
`score500`, `score1000`), 0 mismatches. This is the actual scoring
logic behind the calculator in `docs/index.html` — not a summary of it.

`code/compute_minimizer_M.py` independently re-derives the `M(L)`
constants (the `--m250/--m500/--m1000` defaults `score_designs.py`
uses) from a real, line-for-line Python port of kmtricks' own minimizer
selection (`Kmer<32>::minimizer()`, including its exact 2-bit encoding
and its poly-A low-complexity filter — not a generic approximation),
run against the real query sequences in
[`data/query_examples/`](data/query_examples/):

```bash
python3 code/compute_minimizer_M.py data/query_examples/query_*.fa -k 25 -m 10
```

**Honest caveat**: this reproduces the same order of magnitude and a
similar spread as the report's values (M≈25-31 at 250bp vs. the
report's 24-29, for example) using a straightforward "first *L* bp of
each query" convention, but not bit-for-bit — the exact per-query
slicing offset used when the report's numbers were originally computed
wasn't preserved in a standalone script. `score_designs.py` takes `M(L)`
as a plain argument either way, so this doesn't block reproducing the
score computation itself (Stage 1, above) — it only affects reproducing
the specific constants 26/54/112 from scratch.

## Stage 2 — Generate the raw design-space CSVs (needs cluster + kmhelpers)

`data/*/design_space_*.csv` were produced by `code/enumerate_designs.py`
(unmodified from the real toolchain — it calls `kmhelpers profile` for
every (base, groups) candidate and parses the real `profile.yaml`
output; see its own docstring), driven by `code/enumerate_fullcorpus.sh`
/ `code/enumerate_alllogan.sh`.

This stage needs, and is **not** redistributed in this repo:

- A working [`kmhelpers`](https://github.com/sebllns/kmhelpers)/[`kmtricks`](https://github.com/tlemane/kmtricks) install (the report's numbers used
  kmhelpers v0.6.3; the environment activation script is
  project-cluster-specific and not included here).
- The Logan corpus manifests these CSVs were computed against — built
  from real per-accession k-mer statistics
  (`dynamodb_tigs_stats_sorted.csv`-style data), which is large
  (hundreds of MB to GB) and not republished here. `code/build_full_logan_manifest.py`
  shows exactly how the full-corpus manifest was built from that stats
  file, for anyone with their own access to it.

Given those two things, the exact commands are in
`code/enumerate_fullcorpus.sh` / `code/enumerate_alllogan.sh` — they
are the real job scripts that were actually run, not a paraphrase.

## Stage 3 — The 16-config training campaign (real cluster builds+queries)

`data/training_campaign/training16.csv` is measured data: 16 real
index builds and real timed queries on a SLURM cluster, not something a
script reproduces on demand — reproducing it means re-running that
campaign (real builds, real query timing, on the order of 1.5 days of
cluster time total for all 16 at 60,000-sample training scale). The
report's Validation section explains the campaign design and links the
measured numbers back to the predicted score.

## Summary

| Stage | Reproducible from this repo? |
|---|---|
| Score computation (the actual deliverable) | **Yes — verified, see Stage 1** |
| M(L) minimizer constants | Algorithm yes, exact constants approximately (see caveat) |
| Raw design-space enumeration | Code yes, but needs cluster + kmhelpers + corpus data not included here |
| Training-campaign measurements | No — real measured data, not a computation |
