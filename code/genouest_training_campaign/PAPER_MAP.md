# Publication map: query-aware span grouping for Logan-scale k-mer indexes

## 1. Paper target

The main target is the **second-level publication** discussed in the OmicFinder project: move beyond a merge/no-merge benchmark and turn the observed storage/query tradeoff into a measured, predictive method. The paper should also include selected **third-level elements**: automatic recommendation, out-of-sample validation, query-workload awareness, and integration-ready logic for `kmhelpers`.

The central question is not "does merging spans help?" The new `kmhelpers` already supports span profiling and storage-balanced grouping. The stronger question is:

> Given a sample k-mer cardinality distribution, a storage budget, a span logarithm base, and a target query workload, which number of grouped sub-indexes should be built to minimize end-to-end query cost without exceeding the available storage?

The working empirical model is:

\[
T_q = d + aG + bS + cM,
\]

where:

- `G` is the number of grouped sub-indexes;
- `S` is the estimated total storage after grouping;
- `M` is the estimated size of the largest group;
- `d,a,b,c` are calibrated on the target system;
- the span base `B` changes `G,S,M` through the cardinality buckets and therefore enters the optimization indirectly.

The model uses **design-time** features, so it can score configurations before an expensive build.

## 2. Why the new kmhelpers version changes the contribution

`kmhelpers` 0.6.3 now exposes the complete workflow `list -> profile -> compose -> plan -> apply`, with `design` and `build` wrappers. Its current grouping algorithm partitions contiguous spans into a user-requested number of groups using dynamic programming and a **minimax largest-group storage objective**. This is a strong baseline, not the novelty of this paper.

The paper contribution should therefore be positioned above the existing profiler:

1. characterize how span base and group count jointly affect total storage, largest-group storage, and query latency;
2. learn an empirical query-cost model on the actual deployment/storage system;
3. use the model to recommend `(base, number_of_groups)` subject to a storage constraint;
4. validate the recommendation on configurations that were not used to fit the model;
5. test whether coefficients/recommendations change with query length and, if available, storage class (network disk versus SSD).

A later third-level extension can replace the current fixed minimax boundary objective with a directly query-aware boundary optimizer. That is deliberately not required for the first paper.

## 3. Proposed contributions

### Core second-level contributions

**C1. Logan-scale characterization.** A systematic evaluation on the same Logan unitig material used by Logan-Search, restricted to the locally available spans up to 20, quantifying the storage/query consequences of span granularity and grouping.

**C2. Query-cost model.** An interpretable model linking query latency to number of groups, total grouped storage, and largest-group storage. Coefficients are measured on the target filesystem/hardware instead of assumed.

**C3. Storage-constrained recommender.** A method that enumerates inexpensive design candidates from the sample cardinality manifest and recommends a configuration without building every candidate.

**C4. Reproducible experimental workflow.** Pinned `kmhelpers` version, exact provenance, SLURM-safe serialized builds, peak workspace measurement, deterministic queries, and retained experiment metadata.

### Third-level elements to include if results support them

**C5. Query-workload awareness.** Fit/compare models for 250, 500, and 1000 bp queries and test whether the same configuration remains optimal.

**C6. Hardware/storage transfer.** Repeat a small anchor set on SSD if the same subset can be staged there. Compare coefficients rather than rebuilding the entire design space.

**C7. Held-out configuration validation.** Evaluate top-ranked configurations that were not part of model fitting and report prediction error and regret relative to the best measured validation configuration.

**C8. kmhelpers integration path.** Express the final selection rule as a proposed `profile --recommend`/API extension after the paper model stabilizes.

## 4. Research questions

- **RQ1:** How do logarithm base and number of groups change estimated and realized index storage on Logan-scale data?
- **RQ2:** How much query latency is explained by `G`, `S`, and `M`, and which term dominates on network storage?
- **RQ3:** Can a model trained on a small number of expensive builds identify a near-optimal configuration from a much larger unbuilt design space?
- **RQ4:** How does the model recommendation compare with natural/no-merge spans, one-group merging, the current kmhelpers default-like setting, the storage-minimum setting, and the best legacy BLE configuration?
- **RQ5:** Does the recommended configuration remain stable as the number of query k-mers changes?
- **RQ6 (optional third-level):** How do coefficients/recommendations change when the index is queried from SSD rather than network storage?

## 5. Hypotheses

- **H1:** Natural/no-merge grouping is not generally optimal because pack-of-8 waste and per-sub-index I/O overhead penalize sparse span layouts.
- **H2:** A one-group index minimizes sub-index-open overhead but can increase storage and largest-group cost enough to lose on end-to-end query time.
- **H3:** The optimal point lies inside the design space and depends on the storage medium and query workload.
- **H4:** A model fitted from a small, space-filling subset of configurations predicts the useful part of the design space accurately enough to avoid exhaustive full builds.

## 6. Experimental levels

### Level A: correctness and instrumentation

Use `/projects/logan_compression/Ecoli` and reproduce the official E. coli design/build/query workflow. This checks the pinned toolchain before large jobs.

### Level B: legacy BLE bridge

Reuse the previous BLE raw-data benchmark as a continuity experiment. The important outcomes are:

- reproduce the merge/no-merge direction seen previously;
- measure actual/estimated final size;
- measure peak build workspace/estimated final size;
- set `BUILD_SPACE_FACTOR` conservatively before Logan-scale runs;
- add the previous best `(base, groups)` to `OLD_BLE_BASE` and `OLD_BLE_GROUPS` so it becomes an explicit baseline.

The bundle cannot recover the verbatim old script/path from a previous chat session, so `BLE_ROOT` is intentionally left blank. `discover_project_layout.sh` helps locate the existing benchmark artifacts without changing them.

### Level C: Logan main evaluation

1. Inventory the already downloaded ~4 TB corpus.
2. Create one k-mer-count manifest.
3. Enumerate all base/group candidates from the manifest only.
4. Select ~16 storage-feasible, space-filling training configurations.
5. Build/query them **one at a time**, deleting each final index after measurements unless `KEEP_BUILDS=1`.
6. Fit the cost model.
7. Rank the unbuilt design space.
8. Build the recommendation plus unseen top-ranked candidates and baselines as a validation phase.
9. Report prediction error and measured regret.

### Level D: third-level extensions

- Query-length transfer: already supported by the default 250/500/1000 bp workload.
- SSD/network transfer: change `STORAGE_LABEL`, stage only a small anchor set, and rerun the query phase.
- Direct group-boundary optimizer: future work after the first paper unless the core results finish early.

## 7. Baselines

The final comparison table should contain at least:

1. **Natural/no merge** at base 1.1.
2. **Single merged group** at base 1.1.
3. **kmhelpers default-like**: base 1.1, up to 20 groups.
4. **Minimum estimated total storage** from the enumerated design space.
5. **Minimum largest-group storage** from the design space.
6. **Legacy BLE best**, if recovered.
7. **Model recommendation**.
8. **Top-ranked unseen configurations** for honest post-fit validation.

## 8. Primary metrics

- estimated total grouped storage;
- estimated largest-group storage;
- actual final build size;
- peak observed build-directory size;
- build time and peak RSS;
- query elapsed time (median and dispersion);
- prediction MAE/RMSE and leave-one-configuration-out error;
- validation relative error;
- final recommendation's time and storage regret versus the best measured validation baseline.

Secondary metrics include number of partition/sub-index files, coefficient confidence intervals, and sensitivity to query length.

## 9. Recommended figures

1. Storage versus group count for each span base.
2. Observed versus predicted query time.
3. Empirical storage/query-time Pareto plot with baselines and recommendation annotated.
4. Query-length scaling by configuration.
5. Optional: coefficient comparison for network disk versus SSD.
6. Optional: estimated versus actual/peak build storage to justify the quota guard.

The supplied `plot_results.py` creates the first four diagnostics; final publication styling can be adjusted after results exist.

## 10. Claims to avoid until measured

Do not claim that fewer groups always make queries faster, that minimizing total storage minimizes query time, or that the current kmhelpers minimax grouping is suboptimal in general. The experiment is explicitly designed to establish when each effect dominates.

Do not call the model universal. Coefficients are system/workload dependent unless transfer experiments demonstrate stability.

## 11. Stopping criterion for a publishable second-level result

The second-level paper is ready when all of the following are available:

- a stable Logan manifest and reproducible design-space enumeration;
- at least 12-16 successful training configurations covering the feasible space;
- a fitted model with acceptable held-out prediction error;
- at least three unseen validation configurations plus the required baselines;
- a measured recommendation that provides a defensible query/storage advantage or, equally publishably, a clear characterization of the tradeoff showing why no single setting dominates;
- reproducible provenance and no unresolved storage/caching confounder.
