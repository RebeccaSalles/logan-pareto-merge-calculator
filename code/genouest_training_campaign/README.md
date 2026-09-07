# OmicFinder Logan span-tuning experiment bundle

This bundle implements the experimental path from the earlier merge/no-merge span benchmark to a query-aware publication built on `kmhelpers` 0.6.3.

## Read first

1. `CHANGES_FROM_ORIGINAL_BUNDLE.md` - read this **first**. This bundle was
   drafted by ChatGPT without live cluster access, then reviewed and
   corrected against a real Genouest session (k=25 not k=31, reused/verified
   kmhelpers env instead of a from-source rebuild, real `kmhelpers profile`
   calls instead of reimplemented sizing math, a working `.zst`
   materialization step, several robustness fixes). `TUTORIAL.md` and
   `PAPER_MAP.md` below were spot-corrected, not fully rewritten -- where
   they disagree with `CHANGES_FROM_ORIGINAL_BUNDLE.md`, the changes file is
   authoritative.
2. `PAPER_MAP.md` - research questions, contributions, baselines, and publication stopping criterion.
3. `TUTORIAL.md` - complete GenOuest execution instructions.
4. `config.env` - the only file that should need path/quota/workload edits.

## Main workflow

```text
E. coli smoke test
        |
        v
inventory existing Logan files
        |
        v
one-time k=25 manifest
        |
        v
enumerate hundreds of (base,groups) designs cheaply
        |
        v
select ~16 storage-feasible training designs
        |
        v
build -> benchmark -> delete, one configuration at a time
        |
        v
fit T = d + aG + bS + cM
        |
        v
rank all unbuilt designs under storage constraint
        |
        v
build recommendation + unseen configs + baselines
        |
        v
held-out validation + figures
```

## Storage policy

The configuration defaults to the project facts supplied for this experiment:

```text
project quota: 10 TB
existing Logan raw corpus: ~4 TB
minimum reserve: 1 TB
```

The runner keeps only one full experimental build at a time and deletes it after query measurements by default. It also measures peak build-directory usage so `BUILD_SPACE_FACTOR` can be calibrated from pilot/BLE runs.

`df` is not treated as the project quota: the guard takes the minimum of filesystem free space and an explicit quota headroom calculation.

## `.zst` warning

The manifest builder can stream Logan `.unitigs.fa.zst` directly. Full `kmtricks/kmindex` construction is preflighted separately; the documented build input is gzip/uncompressed FASTA/FASTQ. If your downloaded files are `.zst`, point `BUILD_MANIFEST` to a path-rewritten manifest after controlled materialization, rather than decompressing the whole corpus without a storage plan.

## Script index

- `discover_project_layout.sh`: locate the prior download/BLE artifacts under `/projects/logan_compression`.
- `install_kmhelpers_063.sh`: pin and install the toolchain.
- `check_env.sh`: capture provenance.
- `smoke_ecoli.sh`: reproduce the E. coli design/build/query path.
- `inventory_raw.py`: file-size/compression/span inventory.
- `build_unitig_manifest.py`: k-mer count manifest for Logan unitigs, joined from a per-accession stats CSV rather than streaming FASTA (falls back to a direct scan for any accession the CSV doesn't cover); k=25 for this project, exact only at k=31, approximate otherwise -- see `CHANGES_FROM_ORIGINAL_BUNDLE.md` §1.
- `spotcheck_unitig_counts.py`: emit ntcard verification commands.
- `rewrite_manifest_paths.py`: preserve counts while switching to compatible build copies.
- `check_build_manifest.py`: block unsupported/missing build inputs before expensive work.
- `enumerate_designs.py`: reproduce kmhelpers span/Bloom/minimax storage calculations over a base/group grid.
- `select_training_configs.py`: choose a diverse feasible training set.
- `prepare_queries.py`: deterministic paired 250/500/1000 bp queries.
- `design_one_config.sh`: create one kmhelpers design.
- `run_one_config.sh`: build, benchmark, record, and optionally delete one index.
- `run_training_matrix.sh`: serialized local execution.
- `submit_matrix_sequential.sh`: serialized SLURM dependency chain.
- `suggest_space_factor.py`: calibrate peak workspace safety factor.
- `fit_cost_model.py`: constrained interpretable query-cost model.
- `recommend_config.py`: storage-constrained ranking of all candidate designs.
- `make_validation_configs.py`: post-fit recommendation/baseline/unseen validation set.
- `evaluate_validation.py`: frozen-model validation metrics.
- `plot_results.py`: initial paper figures.

## What this bundle intentionally does not do

It does not alter the original 4 TB corpus, automatically decompress every `.zst` file, or submit concurrent full-scale builds. It also does not yet replace `kmhelpers`' internal minimax group-boundary optimizer. Direct query-aware boundary optimization is a natural third-level follow-on once the `(base, group-count)` model is validated.
