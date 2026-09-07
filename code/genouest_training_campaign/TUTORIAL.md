# Experimental tutorial

**Read `CHANGES_FROM_ORIGINAL_BUNDLE.md` first** -- several steps below were
corrected against a real Genouest session after this tutorial was first
drafted (k=25 not k=31, reused kmhelpers env, real `kmhelpers profile`
calls, a working `.zst` materialization step). Where this file and that one
disagree, the changes file is authoritative.

This tutorial is written for the GenOuest project layout used in the OmicFinder work. The known root is `/projects/logan_compression`; the official E. coli tutorial data are at `/projects/logan_compression/Ecoli`. The exact subdirectory produced by the earlier `s5cmd` Logan download is not guessed: set it once in `config.env` after running the discovery command below.

## 0. Where this lives

This bundle is tracked inside the `kmer_spans` repo at
`kmer_spans/kmhelpers_logan_paper/`. Deploy it to the cluster under your own
`rsalles/` subfolder (per this project's working rule: never write directly
into the shared `/projects/logan_compression` root or other users'
directories), for example:

```bash
rsync -a kmhelpers_logan_paper/ genouest:/projects/logan_compression/rsalles/kmhelpers_logan_paper/
ssh genouest
cd /projects/logan_compression/rsalles/kmhelpers_logan_paper
```

All generated large data are written to `${WORK_ROOT}` under `/projects/logan_compression`, not into this code directory.

## 1. Inspect the existing project layout

```bash
bash scripts/discover_project_layout.sh | tee project_layout.txt
```

Use the output to edit `config.env`:

- set `RAW_ROOT` to the directory containing the downloaded Logan unitig files, **or** set `LOGAN_FILE_LIST` to the exact file list created by the earlier download workflow;
- set `BLE_ROOT` only if you want to reuse the previous BLE experiment;
- keep `PROJECT_QUOTA_BYTES=10000000000000` and `RAW_CORPUS_BYTES=4000000000000` unless measured values differ;
- set `STATIC_OTHER_BYTES` if other large files in the 10 TB allocation are not included in the 4 TB corpus estimate.

The scripts use both the explicit 10 TB project budget and filesystem free space. This avoids trusting `df` alone on a shared filesystem where it may show cluster-level capacity instead of your project quota.

## 2. Verify the pinned kmhelpers toolchain

This reuses the official v0.6.3 environment already built and verified
under `rsalles/kmhelpers_v0.6.3_official/` (`config.env`'s `KMHELPERS_ENV`)
-- **do not rebuild it from source**; see
`scripts/install_kmhelpers_063.sh`'s header comment and
`CHANGES_FROM_ORIGINAL_BUNDLE.md` §2 for why. `install_kmhelpers_063.sh` now
only verifies the environment exists and reports versions:

```bash
bash scripts/install_kmhelpers_063.sh
source scripts/activate_env.sh
bash scripts/check_env.sh
```

`check_env.sh` records hostname, CPU, memory, filesystem, tool versions, and the exact kmhelpers git commit in `${RESULTS_ROOT}`.

If your colleague provides a newer fixed release specifically for the paper, build a *separate* environment for it (same pattern as the existing one, under your own `rsalles/` subfolder), point `KMHELPERS_ENV` at it deliberately, and record the change -- do not silently update mid-experiment, and do not modify the shared `/projects/logan_compression/kmhelpers` install either way.

## 3. Reproduce the official E. coli workflow first

The raw tutorial data already exist in `/projects/logan_compression/Ecoli`, so no download is required:

```bash
source scripts/activate_env.sh
bash scripts/smoke_ecoli.sh
```

This runs the same conceptual workflow as the upstream tutorial:

```text
design -> plan/build -> query
```

Do not start the 4 TB experiment until this succeeds.

## 4. Inventory the Logan corpus

If `RAW_ROOT` is set:

```bash
mkdir -p "${MANIFEST_DIR}"
python scripts/inventory_raw.py \
  --root "${RAW_ROOT}" \
  --output-dir "${MANIFEST_DIR}/inventory"
```

If the earlier download workflow already produced a file list:

```bash
python scripts/inventory_raw.py \
  --file-list "${LOGAN_FILE_LIST}" \
  --output-dir "${MANIFEST_DIR}/inventory"
```

Inspect:

```bash
cat "${MANIFEST_DIR}/inventory/inventory_summary.txt"
head "${MANIFEST_DIR}/inventory/inventory.csv"
```

Confirm that the total is close to the expected ~4 TB and that the file count/span distribution is plausible.

## 5. Build the one-time k-mer cardinality manifest

This project indexes at **k=25** (see `CHANGES_FROM_ORIGINAL_BUNDLE.md` §1
for why, and the citation for it), not the k=31 Logan unitigs are
*assembled* at. Those are different parameters. The Logan paper's "31-mers
are distinct by construction" guarantee is specific to k=31 -- at k=25 the
same length-based shortcut,

```text
sum(max(0, length(unitig) - 25 + 1))
```

is an *approximation*, the same one `create_fof.py` already uses for span
bucketing elsewhere in this project. Used deliberately for consistency, but
**spot-check it** (next section) before trusting it at scale -- don't skip
that step just because the k=31 framing made it sound exact.

`build_unitig_manifest.py` computes this without touching FASTA content at
all: `create_fof.py`'s formula only needs two aggregate numbers per
accession (unitig count, summed unitig length), and those are already
columns in the project's per-accession stats CSV
(`unitigs_with_bins.csv`/`dynamodb_tigs_stats_sorted.csv`:
`seqstats_unitigs_nbseq`/`seqstats_unitigs_sumlen`). The script joins
`--file-list` against `--stats-csv` on accession name instead of
decompressing and streaming every `.zst` file. Any accession present in
`--file-list` but missing from `--stats-csv` (should be rare) falls back
to a direct FASTA scan for just that accession -- no accession is silently
dropped just because the fast path can't cover it; the audit CSV's
`count_source` column records which method produced each row.

```bash
python scripts/build_unitig_manifest.py \
  --file-list "${MANIFEST_DIR}/inventory/logan_files.txt" \
  --stats-csv "${STATS_CSV}" \
  --output "${MANIFEST}" \
  --audit "${MANIFEST_DIR}/logan_k25_audit.csv" \
  -k 25 --trust-unitigs --resume
```

`STATS_CSV` is the per-accession stats CSV described above -- it must be
staged on the same filesystem this command runs on. The command is
resumable. It never changes the raw files.

### Recommended spot check

Generate commands for three ntcard comparisons:

```bash
python scripts/spotcheck_unitig_counts.py "${MANIFEST}" --n 3
```

For `.zst` inputs the generated commands create one temporary gzip copy at a time. ntcard is a cardinality estimator, so expect close agreement rather than bit-for-bit identity.

## 6. `.zst` build compatibility -- materialize once, reuse for every config

Confirmed by direct testing (not assumed): `kmtricks pipeline` cannot open
`.zst` files at all -- tried against both kmtricks builds available to this
project, both failed immediately. A named-pipe streaming workaround was also
tried and rejected (it hung rather than failing cleanly). So real
decompressed copies are necessary. See `CHANGES_FROM_ORIGINAL_BUNDLE.md` §4
for the full story, including why this must run **once**, not per config
(every candidate `(base, groups)` configuration builds over the same sample
set).

Run this once, before any training/validation/extension build:

```bash
bash scripts/materialize_manifest.sh          # full corpus
# or, to see real per-sample sizes before committing to the whole corpus:
bash scripts/materialize_manifest.sh 200      # stop after 200 new files
```

It's idempotent and resumable -- interrupting it (Slurm walltime, etc.) and
re-running just continues from where it left off. It writes `BUILD_MANIFEST`
(already set correctly in `config.env`) and warns loudly up front if the
configured budget looks too tight for the estimated decompressed size
(`DECOMP_ESTIMATE_BYTES` in `config.env` -- a planning guess, not measured;
update it once `materialize_manifest.sh` reports real numbers).

Verify before building anything large:

```bash
python scripts/check_build_manifest.py "${BUILD_MANIFEST}"
```

If the downloaded data are already `.fa`, `.fasta`, `.fna`, or gzip
variants (not the case for raw Logan `.zst` unitigs, but true for e.g. the
wheat/E. coli data this project also uses), `materialize_manifest.sh` passes
them through unchanged -- there's nothing to decompress.

## 7. Bridge with the old BLE experiment before the full Logan build

The previous BLE merge/no-merge experiment should be used as a calibration stage, not discarded. Locate its data/results with `discover_project_layout.sh`, then recover the best old `(base, groups)` setting and put it in:

```bash
OLD_BLE_BASE="..."
OLD_BLE_GROUPS="..."
```

For any representative pilot configuration built with `run_one_config.sh`, the runner records:

- estimated final size;
- actual final build size;
- peak observed build-directory size during construction;
- `peak_to_estimated_factor`.

After a few pilot builds, compute a safer quota factor:

```bash
python scripts/suggest_space_factor.py "${RESULTS_ROOT}/builds.csv" --margin 1.25
```

Update `BUILD_SPACE_FACTOR` in `config.env` before submitting the Logan matrix. Keep at least the configured 1 TB reserve.

## 8. Enumerate the full design space cheaply

This stage does **not** build indexes. It calls real `kmhelpers profile`
once per (base, groups) candidate -- not a reimplementation of kmhelpers'
sizing math, see `CHANGES_FROM_ORIGINAL_BUNDLE.md` §3 for why that matters.
`profile` only reads the JSONL's pre-computed `kmer_count` values, so this
stays cheap even though it's calling the real tool. Needs `kmhelpers` on
`PATH` (`source scripts/activate_env.sh` first, if not already done in this
shell):

```bash
bash scripts/prepare_design_space.sh
```

Outputs:

```text
${MODEL_ROOT}/design_space.csv
${MODEL_ROOT}/selected_configs.csv
```

The default grid spans bases 1.05 through 2.0 and 1-20 groups. The training selector always includes important anchors and then uses farthest-point sampling over `(base, G, S, M)` to cover the feasible region with approximately 16 expensive builds.

Inspect before proceeding:

```bash
column -s, -t < "${MODEL_ROOT}/selected_configs.csv" | less -S
```

## 9. Create deterministic query workloads

The default protocol uses five positive-control regions (increase after the pilot if variance requires it). A 1000 bp anchor is extracted from a unitig, then centered 500 bp and 250 bp versions are derived from the same region:

```bash
python scripts/prepare_queries.py "${MANIFEST}" \
  --output-dir "${QUERY_ROOT}" \
  --lengths "${ALL_QUERY_LENGTHS}" \
  --n "${QUERIES_PER_LENGTH}" \
  --seed "${RANDOM_SEED}"
```

This makes query-length comparisons paired rather than using unrelated sequences.

The primary workload is 1000 bp because that matches the public Logan-Search query scale; 250 and 500 bp are the query-aware extension.

## 10. Run the training configurations

### Interactive/sequential mode

```bash
source scripts/activate_env.sh
bash scripts/run_training_matrix.sh "${MODEL_ROOT}/selected_configs.csv" training
```

### Recommended SLURM mode

Submit a dependency chain so no two large builds coexist:

```bash
bash scripts/submit_matrix_sequential.sh "${MODEL_ROOT}/selected_configs.csv" training
```

The submitter prints job IDs. Use the same commands as in your previous GenOuest workflow to follow them, for example:

```bash
squeue -u "$USER"
sacct -j JOBID --format=JobID,JobName%30,State,ExitCode,Elapsed,Start,End
```

The template requests 16 CPUs, 64 GB RAM, and three days by default. Adjust the `#SBATCH` memory/time directives in `templates/run_config.sbatch` to GenOuest policy and the pilot measurements.

### What each configuration does

For each selected `(base, groups)`:

1. checks that the build manifest is compatible and files exist;
2. checks the explicit 10 TB storage budget;
3. runs `kmhelpers design` from the existing JSONL manifest;
4. runs `kmhelpers plan` before construction;
5. builds one index;
6. samples build-directory size every 60 s;
7. measures build time/RSS/final size;
8. queries all configured query files/repetitions;
9. saves timings and logs;
10. deletes the built index when `KEEP_BUILDS=0`.

Raw inputs are never deleted or modified.

## 11. Fit the model and obtain the recommendation

After all training jobs succeed:

```bash
source scripts/activate_env.sh
bash scripts/fit_and_recommend.sh
```

The fitted model is:

```text
T = intercept + a * groups + b * total_size_TB + c * max_group_size_TB
```

The three physical coefficients are constrained non-negative. The script reports training error, leave-one-configuration-out error, condition number, and bootstrap intervals.

Key outputs:

```text
${MODEL_ROOT}/fit/cost_models.json
${MODEL_ROOT}/fit/coefficients.csv
${MODEL_ROOT}/fit/model_metrics.csv
${MODEL_ROOT}/recommendation/ranked_configs.csv
${MODEL_ROOT}/recommendation/recommendation.json
${MODEL_ROOT}/validation_configs.csv
```

The ranker evaluates all **unbuilt** designs from the cheap enumeration and applies the storage limit before choosing the predicted fastest design.

## 12. Run post-fit validation without leakage

The validation list includes the recommendation, top-ranked configurations not used in training, and the required baselines. Rows explicitly say whether a configuration was already seen during fitting.

Interactive:

```bash
bash scripts/run_training_matrix.sh "${MODEL_ROOT}/validation_configs.csv" validation
python scripts/evaluate_validation.py \
  "${RESULTS_ROOT}/query_timings.csv" \
  "${MODEL_ROOT}/fit/cost_models.json" \
  --output "${MODEL_ROOT}/validation_predictions.csv"
```

SLURM:

```bash
bash scripts/submit_matrix_sequential.sh "${MODEL_ROOT}/validation_configs.csv" validation
```

After the dependency chain finishes, run only the `evaluate_validation.py` command above. Do **not** refit the model before reporting held-out prediction error.

## 13. Generate diagnostic figures

```bash
bash scripts/make_figures.sh
```

Outputs include:

```text
fig_storage_landscape.pdf
fig_observed_vs_predicted.pdf
fig_storage_vs_query_time.pdf
fig_query_length_scaling.pdf
```

For the final paper, add the validation points and highlight the recommended/baseline configurations after the numerical analysis is stable.

## 14. Query-length extension (third-level element)

After the 1 kb recommendation/validation is frozen, run only four anchor configurations at 250/500/1000 bp:

```bash
bash scripts/run_query_length_extension.sh
```

For SLURM, first create the list and submit it as an extension phase:

```bash
python scripts/make_extension_configs.py \
  "${MODEL_ROOT}/design_space.csv" \
  "${MODEL_ROOT}/recommendation/recommendation.json" \
  --output "${MODEL_ROOT}/extension_configs.csv"

bash scripts/submit_matrix_sequential.sh "${MODEL_ROOT}/extension_configs.csv" extension
```

After the jobs finish:

```bash
python scripts/fit_cost_model.py \
  "${RESULTS_ROOT}/query_timings.csv" \
  --phase extension \
  --output-dir "${MODEL_ROOT}/fit_extension" \
  --seed "${RANDOM_SEED}"
```

This estimates how the coefficients change with the number of query k-mers without tripling every training build.

## 15. Optional SSD extension

Do not duplicate the entire 4 TB corpus on SSD. Stage only the input/index subset needed for a small anchor set, for example:

- one-group baseline;
- kmhelpers default-like setting;
- model recommendation;
- one high-group configuration.

Set:

```bash
STORAGE_LABEL="ssd"
```

and repeat query measurements. The interesting result is whether `a`, `b`, and `c` change, especially the group-opening term `a`.

## 16. Files to archive for reproducibility

Keep permanently:

```text
config.env used for the run
provenance_*.txt
manifest JSONL + audit CSV
inventory summary/file list
all design/profile/compose metadata
selected_configs.csv
builds.csv
query_timings.csv
all plan/build/query logs
cost_models.json
coefficients/model metrics
ranked/recommendation/validation CSV+JSON
paper figures
SLURM stdout/stderr and sacct summary
```

You do not need to keep every built index. The serialized build/delete workflow is specifically designed for the 10 TB constraint.
