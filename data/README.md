# Data dictionary

## `design_space_*.csv` (raw `enumerate_designs.py` output)

One row per candidate `(base, groups)` design.

| column | meaning |
|---|---|
| `config_id` | e.g. `b1p2_g16` = base 1.2, 16 groups |
| `base` | the merge base (span-doubling ratio) requested |
| `requested_groups` | groups asked for |
| `groups` | groups actually produced (kmhelpers can only merge adjacent natural spans, so this sometimes clamps below `requested_groups`) |
| `natural_spans` | the finest possible grouping for this base: one group per natural span |
| `sample_count` | total accessions covered |
| `total_size_bytes` | real total Bloom-filter storage for this design |
| `max_group_size_bytes` | largest single group's storage |
| `mean_group_size_bytes`, `group_size_cv` | group-size mean and coefficient of variation |
| `min_span`, `max_span` | span range covered |
| `group_boundaries` | `;`-separated real span boundary per group |
| `group_samples` | `;`-separated real sample count per group |
| `group_sizes_bytes` | `;`-separated real storage size per group: the input to scoring |
| `kind` | `grid` (an explicit base×groups grid point) or `natural` (the finest grouping for that base) |

## `scored_designs_*.{json,csv}` (output of `code/score_designs.py`)

| column | meaning |
|---|---|
| `id` | same as `config_id` above |
| `b`, `g` | base, groups (actual) |
| `s` | total storage, **GB** |
| `m` | largest group's storage, **GB** |
| `np_min`, `np_max` | smallest / largest per-group partition count in this design |
| `score250`, `score500`, `score1000` | predicted query cost at that query length: lower is faster |
| `kind` | see above |
| `gb` | *(JSON only, not CSV)* the design's real per-group byte sizes, the raw input `nb_partitions` is computed from. This is what lets the report's live "formula sandbox" (and `code/compare_scoring.py`) recompute `np_min`/`np_max`/`score*` under a different formula without re-running kmhelpers. |

## `training_campaign/training16.csv`

The 16 real configs that were actually built and queried.

| column | meaning |
|---|---|
| `id`, `g`, `b`, `s` | same as above (`s` here is GB at training/subsample scale, not full-corpus scale) |
| `t250`, `t500`, `t1000` | **real measured** query time, seconds, cold cache |
| `score` | the predicted score at training scale (250bp) |

## `query_examples/`

5 real 5000bp windows from wheat genome assemblies (`query_sources.tsv`
records exactly which assembly/coordinates each came from). The
report's `M(L)` values are the number of distinct kmtricks minimizers
across the first `L` bp of each of these 5, at k=25/m=10, see
`code/compute_minimizer_M.py`.
