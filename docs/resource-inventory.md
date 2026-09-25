# Pilot resource inventory

The authoritative pilot inputs are registered in `resources/pilot.json`. This inventory describes the inspected local files; it does not infer a generating commit from a folder name.

| Resource | Registered location relative to project | Role and limitations |
|---|---|---|
| IFsBase saved output | `../ifs-872/RUNFILES/IFsBase.run.db` | SQLite result store; 1,869 variables; generating version unknown |
| Working saved output | `../ifs-872/RUNFILES/Working.run.db` | Same schema and declared time/geography coverage; generating version unknown |
| Variable dictionary | `../ifs-872/DATA/IFsVar.db` | Definitions, units, currency codes and aggregation; match to generating run not established |
| Country membership | `resources/countries-872.json` | Explicit 188 country/territory entries, verified against the pilot catalogs; no aggregate group entries |
| Code reference | `../ifs-872/Code.Ifs-Translation/src/IFs.Core` | Selected 8.72 source tree for later investigation; no causal tracing implemented in this milestone |
| Model help | `../ifs-872/HELP/ifshelp.chm` | Located but not extracted/indexed in this milestone |
| Nearby scenario file | `../ifs-872/RUNFILES/Working.Sce` | Parameter-change definitions exist, but connection to saved Working results is unverified |

**Pilot limitation:** IFsBase and Working have identical full-file SHA-256 hashes in this workspace. They are two registered filenames containing the same result snapshot, not independent scenario outcomes. Their nearby scenario definitions must not be used to infer different generating conditions.

## Result format and coverage

Both runs contain `ifs_var`, `ifs_var_blob`, `ifs_var_dim`, `ifs_dim`, and `ifs_dim_bucket`, plus regression and migration tables. Variable dimensions are ordered by `ifs_var_dim.Seq`; payload columns `0`, `1`, etc. map to that order, and `v` holds the value.

- Dimension 0: Time, 2022–2100 inclusive (79 years).
- Dimension 1: Region, 188 explicitly enumerated countries/territories.
- Dimension 2: six economic sectors, Agriculture through ICTech, with no total bucket.
- GDP, I, IGCF: 14,852 expected rows each across the full pilot selection.
- INVS, IDS, PFD, MS, CS, GS, XS: 89,112 expected rows each, including the sector dimension.
- Pilot variables have SUM aggregation and currency code `1` in saved metadata.

The registry records reviewed summation rules and exact sector labels. Unknown aggregation rules, unknown variable semantics, mismatched memberships, and unreviewed extra dimensions prevent standard aggregation. Extraction remains available without guessing aggregation.

World totals represent the registered model geography, not an independently established geographic census. Missing/NaN/infinite observations are checked; no general finite numeric missing-value sentinel has been established.

## Legacy Parquet compatibility

Ordinary fastparquet decoding failed with `buffer is smaller than requested size` for pilot GDP. The payload declares INT32 fields annotated INT_16, but observed plain dimension pages use two-byte integers. The stored value field is FLOAT.

The adapter first tries standard decoding. Only explicitly registered legacy datasets can use the fallback. That fallback runs in a separate Python process, admits only the observed numeric schema, repairs two-byte integer pages, and returns numeric arrays without pickle. It does not change fastparquet globals in the caller. Standard-compliant synthetic files use the normal decoder.

The independent existing .NET ParquetTools reader supplies value-and-dimension checks for GDP, I, and INVS. Full-horizon reconciliation is also checked against the previous exports. These checks support the selected pilot format, not every possible historical IFs encoding.

## Provenance and interpretation

Each job fingerprints its registry, dataset, country membership, variable dictionary, and registered scenario file before and after execution. Changes invalidate results. Python/dependency versions and package source hashes are recorded; the executed implementation is archived in the job for inspection.

The current dictionary calls GDP units `Billion 2021$`. The saved results themselves do not establish a dollar base year. Outputs therefore preserve dictionary information with an unverified match flag; absolute changes are described as stored model currency units. Within-run growth rates and comparisons do not establish compatibility with another run's currency basis.

A complete machine-readable schema/metadata inventory is generated at `workspace/inventory/inventory.json`. It includes full SHA-256 fingerprints without copying the result databases.
