# Logan Search Index-Merge Calculator

A free, physically-grounded way to choose how [Logan Search](https://github.com/IndexThePlanet/logan-search)'s
Bloom-filter index (built with [kmindex](https://github.com/tlemane/kmindex)/[kmtricks](https://github.com/tlemane/kmtricks)
via [kmhelpers](https://github.com/sebllns/kmhelpers)) merges small per-span
sub-indexes — trading storage against query speed without building a
single candidate index.

**[Open the live report →](https://RebeccaSalles.github.io/logan-pareto-merge-calculator/)**
*(also live right now, independent of GitHub Pages, at
<https://claude.ai/code/artifact/894f960f-d880-4358-87c3-f33b12447f29>)*

## What's here

| Path | What it is |
|---|---|
| [`docs/index.html`](docs/index.html) | The report itself — the source for the GitHub Pages site above. Self-contained: all data is embedded, all charts are rendered client-side from it, no build step. |
| [`code/`](code/) | The real deliverable: the enumeration/scoring toolchain that produced every number in the report. See [Reproducing the benchmark](#reproducing-the-benchmark). |
| [`data/span_le20/`](data/span_le20/) | 250 candidate designs over the span≤20 slice of the Logan corpus (7.15M accessions). |
| [`data/full_logan/`](data/full_logan/) | 252 candidate designs over the full Logan corpus, all spans (26.86M accessions). |
| [`data/training_campaign/`](data/training_campaign/) | The 16 configurations that were actually built and query-benchmarked for real, used to validate the score against measured query time. |
| [`data/query_examples/`](data/query_examples/) | The 5 real wheat-genome query sequences the report's minimizer counts (`M(L)`) are computed from. |

## The model

```
score(design, L) = Σ_g  min( nb_partitions(S_g), M(L) )
```

- `S_g` — group *g*'s real on-disk storage size, from `kmhelpers profile`.
- `nb_partitions` — the group's real partition count, from kmhelpers'
  own compose formula (`clamp(round_up_to_pow2(1 + S_g / 4GB), 4, 256)`,
  read directly from its source).
- `M(L)` — distinct kmtricks minimizers in a query of length `L`
  (k=25, m=10). The index shards k-mers by minimizer, not by k-mer, so
  this — not the query's raw k-mer count — bounds how many partitions a
  query can touch.

Full derivation, the physical argument for why partition count drives
query time, and the validation against real measured query time are all
in the report itself.

## Results as CSV

Every number behind the report is also available as plain CSV, not just
embedded in the HTML:

- [`data/span_le20/design_space_span_le20.csv`](data/span_le20/design_space_span_le20.csv) — raw `kmhelpers profile` output, one row per design (storage, per-group byte sizes, natural span boundaries).
- [`data/span_le20/scored_designs_span_le20.csv`](data/span_le20/scored_designs_span_le20.csv) — the same 250 designs with `score250/500/1000` computed.
- [`data/full_logan/design_space_full_logan.csv`](data/full_logan/design_space_full_logan.csv) / [`scored_designs_full_logan.csv`](data/full_logan/scored_designs_full_logan.csv) — same, for the full-corpus grid.
- [`data/training_campaign/training16.csv`](data/training_campaign/training16.csv) — the 16 real built-and-queried configs, with measured query times (`t250/t500/t1000` seconds) alongside the predicted score.

Column meanings are documented in [`data/README.md`](data/README.md).

## Reproducing the benchmark

See [`REPRODUCE.md`](REPRODUCE.md) for exactly what's push-button
reproducible from this repo alone (the scoring step — verified, see
below) versus what needs cluster access to kmhelpers and the Logan
corpus statistics (the raw `kmhelpers profile` enumeration).

Quick version — regenerate every scored CSV/JSON in `data/` from the
checked-in raw CSVs, no cluster needed:

```bash
python3 code/score_designs.py data/span_le20/design_space_span_le20.csv  out/span_le20
python3 code/score_designs.py data/full_logan/design_space_full_logan.csv out/full_logan
```

This was verified byte-for-numeric-value-identical against the data
shipped in this repo before publishing (0 mismatches across all 502
designs, both corpora).

## Testing alternate `nb_partitions` assumptions

Three constants in the formula are worth a second look: 4GB per
partition, power-of-2 rounding, and the 4–256 floor/cap. Two ways to
test different values, no cluster needed:

- **In the report itself** — "Test the nb_partitions formula" at the
  end of How It Works. Change any constant and the calculator and
  trend charts recompute live, in the browser, from the real per-group
  storage data already embedded in the page.
- **From the command line**, for a reproducible before/after on disk:

  ```bash
  python3 code/score_designs.py data/full_logan/design_space_full_logan.csv out/baseline
  python3 code/score_designs.py data/full_logan/design_space_full_logan.csv out/alt \
      --partition-bytes 8589934592 --max-partitions 128   # e.g. 8GB/partition, cap 128
  python3 code/compare_scoring.py out/baseline.csv out/alt.csv --budget-gb 2000000
  ```

  `compare_scoring.py` reports how many designs' scores changed, whether
  the single best design or the Pareto frontier changed, and (with
  `--budget-gb`) whether the budget-constrained recommendation changed —
  the actual question "is this constant right?" needs answered, not
  just a diff of numbers.

## License

MIT — see [`LICENSE`](LICENSE). This covers the code and the derived
result data in this repo. It does not cover Logan/kmtricks/kmindex/
kmhelpers themselves, which are separate projects under their own
licenses (linked above).

## Status

This is one part of an ongoing project (OmicFinder / Logan Search index
optimization). The calculator's *ranking* is checked against the real
16-config training campaign (Validation section of the report); an
anchor phase of full-scale builds to confirm absolute query time, and a
full-Logan (all-spans) measurement campaign, are both still pending —
the report states plainly what's confirmed versus what's open.
