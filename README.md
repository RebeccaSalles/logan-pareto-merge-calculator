# Logan Pareto Merge Calculator

An interactive tool for choosing how [Logan Search](https://github.com/IndexThePlanet/logan-search)'s
Bloom-filter index (built with [kmindex](https://github.com/tlemane/kmindex)/[kmtricks](https://github.com/tlemane/kmtricks)
via [kmhelpers](https://github.com/sebllns/kmhelpers)) merges small per-span sub-indexes.

**[Open the calculator tool →](https://RebeccaSalles.github.io/logan-pareto-merge-calculator/)**

What you can do on the page:

- Get a recommended (base, groups) design for a query length and storage budget: the tool plots the real storage-vs-speed Pareto curve across 502 candidate designs and picks the fastest one on it that fits your budget — no index built to check it.
- Test the underlying cost formula's own assumptions (partition size, rounding, caps) live, right in the browser.
- See how storage and query cost move with groups and base, across both the span≤20 and full-Logan corpus.
- Read the model itself and how it holds up against a real 16-config measurement campaign.

## What's here

| Path | What it is |
|---|---|
| [`docs/index.html`](docs/index.html) | The calculator and the write-up together, in one page — the source for the GitHub Pages site above. Self-contained: all data is embedded, everything runs client-side, no build step. |
| [`code/`](code/) | The real toolchain behind it: the enumeration/scoring scripts that produced every number on the page, plus [`genouest_training_campaign/`](code/genouest_training_campaign/) — the full pipeline that ran the 16-config training campaign on Genouest, for anyone with their own account there. See [Reproducing the benchmark](#reproducing-the-benchmark). |
| [`data/span_le20/`](data/span_le20/) | 250 candidate designs over the span≤20 slice of the Logan corpus (7.15M accessions). |
| [`data/full_logan/`](data/full_logan/) | 252 candidate designs over the full Logan corpus, all spans (26.86M accessions). |
| [`data/training_campaign/`](data/training_campaign/) | The 16 configurations actually built and query-benchmarked for real, used to check the score against measured query time. |
| [`data/query_examples/`](data/query_examples/) | The 5 real wheat-genome query sequences the minimizer counts (`M(L)`) are computed from. |

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

The full derivation, the physical argument for why partition count
drives query time, and the check against real measured query time are
all in the write-up itself.

## Results as CSV

Every number behind the calculator is also there as plain CSV, not
just embedded in the page:

- [`data/span_le20/design_space_span_le20.csv`](data/span_le20/design_space_span_le20.csv) — raw `kmhelpers profile` output, one row per design (storage, per-group byte sizes, natural span boundaries).
- [`data/span_le20/scored_designs_span_le20.csv`](data/span_le20/scored_designs_span_le20.csv) — the same 250 designs with `score250/500/1000` computed.
- [`data/full_logan/design_space_full_logan.csv`](data/full_logan/design_space_full_logan.csv) / [`scored_designs_full_logan.csv`](data/full_logan/scored_designs_full_logan.csv) — same, for the full-corpus grid.
- [`data/training_campaign/training16.csv`](data/training_campaign/training16.csv) — the 16 real built-and-queried configs, with measured query times (`t250/t500/t1000` seconds) next to the predicted score.

Column meanings are in [`data/README.md`](data/README.md).

## Reproducing the benchmark

[`REPRODUCE.md`](REPRODUCE.md) lays out what's push-button reproducible
from this repo alone versus what needs cluster access to kmhelpers and
the Logan corpus statistics.

Quick version — regenerate every scored CSV/JSON in `data/` from the
checked-in raw CSVs, no cluster needed:

```bash
python3 code/score_designs.py data/span_le20/design_space_span_le20.csv  out/span_le20
python3 code/score_designs.py data/full_logan/design_space_full_logan.csv out/full_logan
```

It reproduces the shipped scored files exactly, field for field, across
all 502 designs.

## Testing alternate `nb_partitions` assumptions

Three constants in the formula are worth a second look: 4GB per
partition, power-of-2 rounding, and the 4–256 floor/cap. Two ways to
try different values, no cluster needed:

- **In the calculator itself** — "Test the nb_partitions formula" at
  the end of How It Works. Change any constant and the calculator and
  trend charts recompute live, in the browser, from the real per-group
  storage data already embedded in the page.
- **From the command line**, for a reproducible before/after on disk:

  ```bash
  python3 code/score_designs.py data/full_logan/design_space_full_logan.csv out/baseline
  python3 code/score_designs.py data/full_logan/design_space_full_logan.csv out/alt \
      --partition-bytes 8589934592 --max-partitions 128   # e.g. 8GB/partition, cap 128
  python3 code/compare_scoring.py out/baseline.csv out/alt.csv --budget-gb 2000000
  ```

  `compare_scoring.py` shows how many designs' scores changed, whether
  the single best design or the Pareto frontier changed, and — with
  `--budget-gb` — whether the actual recommendation at a given budget
  changed. That's the real question worth asking, not just whether the
  numbers moved.

## License

MIT — see [`LICENSE`](LICENSE). Covers the code and the result data in
this repo. It doesn't cover Logan/kmtricks/kmindex/kmhelpers themselves,
which are separate projects under their own licenses (linked above).

## Status

Part of an ongoing project (OmicFinder / Logan Search index
optimization). The calculator's ranking is checked against the real
16-config training campaign (see the write-up's Validation section); an
anchor phase of full-scale builds to confirm absolute query time, and a
full-Logan (all-spans) measurement campaign, are both still pending.
