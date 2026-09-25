# Phase 4 verification

Validated on Windows with Python 3.12.14 on 2026-09-24. **Ready within reviewed scope:** code-first investigation records and bounded saved-result checks. This is a reusable Python/CLI backend; automatic model-led source interpretation, MCP, and chat remain later work.

- **82 tests passed:** the existing 27 numerical tests, 41 research tests, and 14 new investigation tests.
- The real pilot used IFsBase, 188 registered countries/territories, and all 79 stored years (2022–2100). Precomputed aggregate groups were excluded by reviewed membership.
- First stored year: all **188** country records satisfy the reviewed initialization sum with its 0.001 floor within absolute tolerance 0.001 plus relative tolerance 1e-6.
- Subsequent years: all **14,664** country/year records satisfy the conditional inventory-accounting expression within the same tolerances. **14,648** of those records have an observed I–sector-summed-INVS gap beyond tolerance; that gap is not classified as a failed requirement.
- The generic runner also passes an unrelated synthetic balance case with documented matching fixture provenance and established conditions. Deliberately changing two country values in opposite directions produces `potential_inconsistency` even though the aggregate cancels.
- Independent arithmetic spot checks recomputed sector sums and the reviewed equation directly from raw reader observations for Afghanistan, China, and the United States in 2022, 2050, and 2100. These are nine spot checks, not a second independent full-corpus decoder validation.
- Artifact replay produced byte-identical country-values and comparison tables with the same outcome. Changed source, changed datasets, and invalid citation bindings are rejected in tests.
- The earlier numerical engine and registered numerical input fingerprints remain unchanged. IFs was not built or executed.

The pilot result is `numeric_consistency: consistent_with_reviewed_relations`. Its saved-run attribution remains `insufficient_evidence`: the generating source version, exogenous-replacement settings, initialization-year correspondence, and final output timing have not been independently established. This qualification does not negate the reviewed implementation explanation or the measured numbers. The code explanation explicitly records the first-year floor, forecast inventory term, allocation, call order, and possible exogenous overwrite.

The saved outputs are `workspace/research/phase4-validation.json` and the investigation/replay folders named there. Each investigation preserves its reviewed specification, source excerpts, documentation approval labels, scenario provenance, metadata/coverage, country and aggregate results, execution log, archived implementation and replay script. See [the investigation guide](investigation-guide.md) for commands, schema, outcomes and limits.
