# Changes from the original ChatGPT-drafted bundle

This directory started as a paper-planning bundle drafted by ChatGPT
(`kmhelpers_logan_paper_bundle.zip`, dated 2026-08-18) and reviewed +
modified by Claude against a live Genouest cluster session on 2026-08-24,
with the project owner's explicit decisions. See `kmer_spans/docs/implementation_log.md`'s
2026-08-24 entries for the full review/verification trail (what was tested
live, what the evidence was). This file is the authoritative summary of what
changed and why: read it before trusting anything in `TUTORIAL.md` or
`PAPER_MAP.md` that contradicts it; those files were not fully rewritten,
only spot-corrected, to avoid introducing new inconsistencies in a large
prose document.

## 1. k=25, not k=31

`config.env`'s `KMER_SIZE` is now **25**, not 31. k=25 is this project's
established, consistently-used index k-mer size: `create_fof.py`,
`build_indexes/`, and the wheat benchmark (whose manifest explicitly records
`k: 25`) all use it, and the real Logan span histogram
(`kmer_spans/grouped_spans_tigs_sumlen_distribution.csv`) was built at k=25
and matched the project supervisor's own reference histogram. k=31 is a
*different* parameter: it's the k-mer size Logan's own unitigs are
*assembled* at (per the Logan paper), which is unrelated to what k this
project's kmindex-based *search index* uses. Citation for k=25 as kmindex's
own documented convention: Lemane, Téo, et al. "Indexing and real-time
user-friendly queries in terabyte-sized complex genomic datasets with
kmindex and ORA." *Nature Computational Science* 4.2 (2024): 104-109; every
construction example in `kmindex-src/README.md` and
`kmindex-src/docs/kmindex/docs/construction.md` (already in the `kmer_spans`
repo) uses `--kmer-size 25`.

Consequence: `build_unitig_manifest.py`'s length-based k-mer-count shortcut
(`sum(max(0, length-k+1))`) is *exact* only at k=31 (Logan's construction k,
where unitig k-mers are unique by construction), at k=25 it's an
*approximation*, the same one `create_fof.py` already relies on for span
bucketing. This is used deliberately for consistency with the rest of the
project, but **must** be spot-checked with `scripts/spotcheck_unitig_counts.py`
before trusting it at scale; this was already true for the original k=31
framing but is easier to forget once the number stops looking like a
citable exact-uniqueness guarantee.

**Update 2026-08-28:** `build_unitig_manifest.py` now computes this same
approximation via a `--stats-csv` join (`dynamodb_tigs_stats_sorted.csv`'s
`seqstats_unitigs_nbseq`/`seqstats_unitigs_sumlen`, the same two inputs
`create_fof.py`'s `index_id_to_size()` uses -- `unitigs_with_bins.csv` has
the same two columns plus one unused derived one, so either works, but the
smaller file was preferred) instead of decompressing and streaming every
`.zst` FASTA file, same formula, same approximation caveat, much cheaper;
verified against the real full corpus (all 7,153,150 `LOGAN_FILE_LIST`
accessions matched the stats CSV). Falls back to the original FASTA-scan
code for any accession the stats CSV doesn't cover. See
`kmer_spans/docs/implementation_log.md`'s 2026-08-28 entry.

## 2. Reuse the existing official kmhelpers v0.6.3 environment: no rebuild, no from-source install

`config.env`'s `KMHELPERS_REPO`/`KMHELPERS_ENV` now point at
`/projects/logan_compression/rsalles/kmhelpers_v0.6.3_official/`, a conda
environment already built and verified end-to-end (E. coli tutorial passes,
correct query result) on 2026-08-24, via the *plain* official recipe
(`conda env create -f conda/environment.yml`, which pulls bioconda's
`kmindex` 0.6.1). Verified portable across both AVX2 and non-AVX2 compute
nodes by direct testing on both.

`scripts/install_kmhelpers_063.sh` no longer installs or builds anything:
it now only *verifies* the existing environment (see the script's own
header comment for why). The original script ran the upstream repo's
`scripts/setup.sh`, which builds `kmindex`/`kmtricks` **from source**. Don't
use that: it was necessary only while bioconda's `kmindex` lagged the
`static_repart` feature (true as of the colleague's 2026-07-03 email, before
bioconda caught up on 2026-07-09), and a from-source build risks
reintroducing the exact non-portable-binary problem (SIGILL on some compute
nodes) that made the colleague's own manually-built beta unreliable; that
crash was directly reproduced and diagnosed this session, see
`kmer_spans/docs/experiment_status.md` §10.

`scripts/activate_env.sh` was also missing the Genouest-specific
`source /local/env/envconda.sh` bootstrap needed before `conda activate`
works at all on this cluster (confirmed by direct testing). Added. It
deliberately does **not** wrap that sourcing in `set -e`/`set -u`; doing so
caused a real, silently-swallowed activation failure earlier in this
project (see `kmer_spans/docs/implementation_log.md`, 2026-08-24, third
pass). Don't reintroduce that pattern here.

`SLURM_CONSTRAINT="avx2"` was added to `config.env` and wired into
`templates/run_config.sbatch` (a default `#SBATCH --constraint=avx2`) and
`submit_matrix_sequential.sh` (passed explicitly at `sbatch` submission
time, which takes precedence over the template default). The official
environment doesn't need this to avoid crashing, but it keeps benchmark
timings comparable across runs by pinning to one CPU generation, and is
cheap defense-in-depth.

## 3. `enumerate_designs.py` calls real kmhelpers now, not a reimplementation

The original script hand-derived kmhelpers' Bloom-filter sizing and minimax
grouping math from reading the source (`bf_size()`, `storage()`,
`minimax_groups()`). That's a real risk for a paper claiming cheap
enumeration predicts what real builds produce: any drift between the
reimplementation and the actual tool undermines the claim, and there was no
way to be sure they matched without checking against a real install, which
didn't exist when the bundle was drafted.

The script now calls `kmhelpers profile <manifest> -o <tmp> -g GROUPS -b BASE
-fp FP` per (base, groups) candidate and parses its real `profile.yaml`
output. This is still cheap: `profile` reads pre-computed `kmer_count`
values from the manifest, it does not rescan FASTA, and it's now
impossible for the enumerated numbers to disagree with what a real build
would compute, because they come from the same code path. **Verified
end-to-end against a real manifest on 2026-08-24** (see
`kmer_spans/docs/implementation_log.md`), the CSV output schema/column
names are unchanged, so `select_training_configs.py`, `recommend_config.py`,
`make_validation_configs.py`, `make_extension_configs.py` did not need to
change.

Consequence: `enumerate_designs.py` and `prepare_design_space.sh` now need
`kmhelpers` on `PATH` (`source scripts/activate_env.sh` first); they didn't
before. Both fail with a clear error if it's missing rather than a confusing
downstream one.

## 4. `.zst` decompression: real, necessary, and now automated (once, not per-config)

Tested directly (not assumed): feeding a `.zst` file to `kmtricks pipeline`
fails immediately on **both** kmtricks builds available to this project
(official v1.6.0 and the colleague's beta v1.5.1). A named-pipe streaming
workaround was also tested and rejected: it got further but then hung on a
trivial input, producing the same `kmtricks_backtrace.log` signature this
project's repo root already had from an unexplained historical crash. So a
real, persisted decompressed copy is necessary; there's no clever shortcut
around it.

**Important correction from an earlier (wrong) plan discussed in chat**:
decompression must NOT happen per-config. Every candidate `(base, groups)`
configuration builds over the *same* sample set; only the Bloom-filter
grouping differs, so decompressing once and reusing across every config is
correct; decompressing-then-deleting per config would mean redoing the same
work 16-20+ times for no reason.

New script: `scripts/materialize_manifest.py` (+ `materialize_manifest.sh`
wrapper) decompresses each `.zst` sample **once** into a persistent
`DECOMP_ROOT` cache, writes a path mapping, and produces `BUILD_MANIFEST`.
It's idempotent/resumable (skips already-materialized samples, safe to
re-run or interrupt), streams via `zstd -dc | gzip -1` (no full file held in
memory), and stops cleanly with a clear message if free space drops below
`MIN_FREE_BYTES` partway through (rather than filling the filesystem).
`scripts/rewrite_manifest_paths.py` still exists as a lower-level utility
(useful if decompressed copies already exist some other way) but is no
longer the primary path; `materialize_manifest.sh` replaces the old manual
"build a mapping TSV by hand" instructions in `TUTORIAL.md` step 6.

**This changes the disk-budget picture materially and it's worth being
deliberate about, not just running it.** By default the decompressed cache
sits *alongside* the raw `.zst` corpus, not instead of it.
`config.env`'s `DECOMP_ESTIMATE_BYTES` was originally a planning guess
(`gzip -1` typically lands within ~1.0–1.5x of the original `.zst` size,
not measured), **now replaced with a real measurement, twice**: a 50-file
random sample decompressed on 2026-08-25 gave **1.5228x** expansion
(8,462,518 → 12,886,749 bytes); a second, larger (974-file), more precisely
timed sample gave **1.5208x**, consistent with the first (the ratio held;
absolute per-file KB did not, so trust the ratio, not the first sample's
per-file size).

**Correction to the raw-corpus-size figure itself (2026-08-25)**: the "4 TB"
figure this file originally used for the raw `.zst` corpus turned out to be
the CSV's *uncompressed*-FASTA-size estimate (5.20 TB, actually), not a
measurement of what the `.zst` files occupy on disk; `du` on the raw
corpus directory hangs at this file count (7.15M files), so it was never
directly `du`'d. Cross-validated two independent ways instead: direct
random sampling of real `.zst` file sizes gave ~2.15–2.48 TB; the
raw/compressed ratio (5.20 TB ÷ 2.097x) independently gives ~2.48 TB. Using
the conservative (upper) end, **the actual raw corpus is ~2.48 TB, not
4 TB**. `config.env`'s `RAW_CORPUS_BYTES` is now set to this.

Recomputing the additive-mode budget with the corrected numbers: raw
(2.48 TB) + decompressed (~2.48 TB × 1.52 ≈ 3.78 TB) = **~6.26 TB, well
under the 10 TB quota**, with ~3.7 TB of headroom left over for a build and
margin. **This reverses the previous conclusion.** The original text here
said the full corpus does not fit additively and proposed a ~79%-by-size
subset as a planning ceiling; that was an artifact of the wrong 4 TB
figure. The full ~7M-accession corpus fits in the default additive mode
without needing `--replace-source` or a subset, left here, struck through
in spirit rather than deleted, as a record of the correction (see
`kmer_spans/docs/implementation_log.md` for the dated entry). The scope
decision (how much of the corpus to actually use for real experiments) is
still the project owner's call. The budget picture just changed
favorably.

**Second option, added 2026-08-25, off by default**: `materialize_manifest.py
--replace-source` (wired through `materialize_manifest.sh` via
`REPLACE_SOURCE=1` in `config.env`) deletes each `.zst` source, verified
good first, right after it's decompressed. Total footprint then converges
to just the decompressed size (~3.78 TB for the full corpus, with the
corrected figures, fits with even more room to spare), at the cost of
losing the local raw copy (mitigated by `s3://logan-pub` being
public/no-sign-request, re-fetchable, not lost, just not free). Every
deletion is logged (`${MANIFEST_DIR}/deleted_sources.tsv`) so a targeted
re-download list could be reconstructed. `materialize_manifest.sh` warns
loudly if the numbers don't look like they'll fit under the active mode
and supports `--max-files` for staged, partial materialization so you can
get real per-sample numbers before committing to a full run. Whether to
use the full ~7M-accession span-≤20 corpus, a smaller subset, or
`REPLACE_SOURCE=1`, is still a scope decision for the project owner. This
tooling supports all three, it doesn't make the decision.

**Parallel decompression, added 2026-08-25**: `materialize_manifest.py
--workers N` (default 1) parallelizes decompression with a thread pool
(subprocess-based `zstd -dc | gzip -1`, I/O-bound, so threads are enough,
no need for a heavier process pool). Measured on a real 1472-file slice of
the corpus rather than assumed: **1 worker ≈ 12.1 files/sec, 8 workers ≈
67.3 files/sec, 16 workers ≈ 79.7 files/sec**, clearly sub-linear (16
workers is only +18% over 8, for 2x the concurrent filesystem load),
consistent with this being bound by the network filesystem, not CPU.
`materialize_manifest.sh` now reads `MATERIALIZE_WORKERS` from
`config.env` (default **8**, chosen as most of the achievable speedup for
half the concurrent load) and passes `--workers`. At 8 workers, the full
corpus materializes in **~29.5 hours**, not the ~6.85 days a naive
single-threaded run would take.

**Native `.zst` support in kmtricks/GATB, reassessed, more favorably,
2026-08-25**: earlier in this project's history this was dismissed based on
a weak signal (no GitHub issues mentioning zstd). Reading the actual
vendored GATB source
(`kmindex-src/thirdparty/kmtricks/thirdparty/gatb-core-stripped/src/gatb/bank/impl/BankFasta.cpp`)
changes that assessment: all FASTA/FASTQ reads go through zlib's
`gzopen`/`gzread`/`gzclose` at roughly ten call sites in one file, and none
of it needs true random-seek: a contained, moderate-scope patch (e.g.
`libzstd`'s streaming API behind the same call sites, or a `zstd`-aware
wrapper), not the "disproportionate engineering effort" this file
previously implied. Still a real undertaking (a from-source GATB/kmtricks
patch, tested for correctness and performance, ideally upstreamed rather
than forked) and **not started**. The decompress-and-cache approach above
remains what's actually implemented and tested. Flagged here as a option
worth real consideration if `.zst`-native support becomes a recurring need
beyond this one project.

**`RAW_ROOT`/`LOGAN_FILE_LIST` are no longer blank.** `unitigs_with_bins.csv`
(needed to derive either) turned out to exist only in the local repo, not
on the cluster, so this was generated locally with the project's own
existing `kmer_spans/download_unitigs_span.py --generate-only` (a
single streaming pass, no directory walk, this script already existed
and was the right tool; an earlier ad hoc `awk`/`head` attempt at a small
test sample was a mistake worth recording: `unitigs_with_bins.csv` is
sorted by size, so `head -N` silently grabs the *N most degenerate* rows
in the entire dataset, not a representative sample; always shuffle first
when sampling from it, as `download_unitigs_span.py`'s own full-corpus
pass and this fix both do). The resulting full 7,153,150-line file list
was uploaded (gzip-compressed, 39MB) to
`${PROJECT_ROOT}/rsalles/span_tuning_paper/manifest/logan_span20_filelist.txt`
and `LOGAN_FILE_LIST` now points at it, confirmed matching the known
corpus numbers exactly (7,153,150 accessions, 4.73 TiB).

**Real bug found and fixed running the actual full-corpus job (2026-08-25)**:
the first real attempt (not a small sample) hit a source file missing on
disk, a known, real gap (~1,634 of 7,153,150 accessions were never
successfully downloaded in the original 07-06 job, `NoSuchKey`),
and `materialize_manifest.py` had no handling for it: the exception from a
failed `future.result()` was uncaught, killing the entire run. Worse,
because `ThreadPoolExecutor`'s context manager waits for in-flight work
before propagating that exception, files whose decompression (and, under
`--replace-source`, source deletion) had already completed in other
threads were never recorded, since the main thread's bookkeeping loop died
before reaching them. Fixed: `future.result()` is now wrapped in
`try/except`, failures are logged to a new `--failed-log` TSV
(source/error/timestamp) instead of aborting the run, and already-logged
failures are skipped (not retried) on resume. `materialize_manifest.sh`
now always passes `--failed-log` (`${MANIFEST_DIR}/failed_sources.tsv`).
The untracked files from the crash that produced this fix were reconciled
by cross-referencing what was actually on disk against `mapping.tsv`, see
`docs/implementation_log.md`'s fourteenth-pass entry for the full
postmortem, including a separate real mistake (accidental data loss during
this session's own smoke testing, corrected via re-fetch from
`s3://logan-pub`) that is unrelated to this bug but surfaced during the
same pass.

## 5. Efficiency / robustness fixes (no behavior change to the experimental design)

- `run_one_config.sh` and `smoke_ecoli.sh` no longer call `kmhelpers plan`
  immediately before `kmhelpers build`: `build` already runs plan→apply
  internally (`kmhelpers build --help`); the separate `plan` call just
  repeated work.
- `lib/common.sh`'s `quota_headroom_bytes()` no longer runs a fresh
  `du -sb "$WORK_ROOT"` on every single call. It's cached for 10 minutes
  (`WORK_USED_CACHE_TTL_SECONDS`, overridable). This project has already hit
  real multi-minute `du`/`find` hangs on directories with millions of files
  (see `kmer_spans/docs/agent_context.md`); the live `df`-based free-space
  check (`effective_headroom_bytes` takes the min of both) still catches any
  staleness in the dangerous direction: a stale `du` can only make the
  cached estimate too *conservative*, never too optimistic, so this is safe.
- `discover_project_layout.sh` and `inventory_raw.py` explicitly avoid
  walking/`du`-ing `unitigs_spans_20/` (7M files, already known to hang
  plain `du`/`find`/`ls` in this project), the layout script excludes it by
  name and adds `timeout` guards; the inventory script warns loudly and
  recommends `--file-list` when no file list is given, instead of silently
  doing a slow full-tree walk.
- `submit_matrix_sequential.sh` and `run_training_matrix.sh` parsed the
  design/selected-configs CSV **positionally** (`IFS=, read -r config_id
  base requested_groups groups ...`), fragile, since any future column
  reorder in the CSV silently reads the wrong value into the wrong variable
  instead of erroring. Both now read columns by **name** via a small shared
  helper, `scripts/lib/csv_columns.py`.

## What did NOT change

Everything not listed above: `fit_cost_model.py` (constrained NNLS,
leave-one-out CV, bootstrap CIs), `recommend_config.py` (Pareto front +
storage-constrained ranking), `select_training_configs.py` (farthest-point
training-set selection), `make_validation_configs.py`/
`make_extension_configs.py` (train/validation isolation,
`seen_in_training` tracking), `evaluate_validation.py`, `design_one_config.sh`
(correctly locates the top-level `{name}.yaml`, not a per-partition file,
verified against a real run), `build_unitig_manifest.py`/`prepare_queries.py`'s
streaming `.zst` reads (fine for a single sequential read, only feeding
`.zst` to *kmtricks* is the problem, not reading it in Python), all read as
correct on review and were left as-is.
