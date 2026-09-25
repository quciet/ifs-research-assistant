# Validation of the first milestone

Validated locally on Windows with Python 3.12.14, using the isolated project virtual environment. Package dependency checks passed. The package has no dependency on the sibling `.analysis-deps` folder.

## Automated results

- **27 synthetic tests passed.** Coverage includes complete and filtered extraction, independent dimension labels, world totals excluding aggregate groups, reviewed sector membership, perturbed identities, missing rows and entire years, duplicates, invalid dimensions/selections, null/infinite values, unsupported aggregation, incompatible currencies, zero-start growth, read-only access, live-sidecar rejection, payload budget rejection, and replay/input-change behavior.
- **Independent decoder parity passed.** For each registered pilot dataset, GDP and I matched 1,316 records each and INVS matched 7,896 records against the existing .NET ParquetTools decoder. Dimension keys and reconstructed float32 values matched exactly: 21,056 comparisons across both registered paths.
- **Full-horizon reconciliation passed.** All 79 years and all columns match the prior IFsBase/Working reconciliation exports with `atol=1e-8`, `rtol=1e-12`. Maximum observed difference was approximately `5.82e-11`, attributable to CSV round-tripping/arithmetic representation.
- **Reproducibility passed.** GDP-ranking jobs replayed in new folders with identical output CSV SHA-256 hashes, after checking source and implementation fingerprints.
- **Source preservation passed.** Input SHA-256 hashes and result-directory entries were unchanged during validation. No SQLite sidecars were created.

The machine-readable evidence is in `workspace/validation/validation.json`; schema and metadata inventory is in `workspace/inventory/inventory.json`. Analysis job folders contain executable replay scripts and archived implementation source.

## Important limits

**IFsBase.run.db and Working.run.db are byte-identical in this workspace.** Their shared SHA-256 is `c5ca392dda1ec2f4316cf18a4eb0b79638ffe631e56f8232fa3906368d2c3b77`. Validation exercises both registrations but does not demonstrate different real scenario responses. The deliberately perturbed synthetic case tests discrepancy detection.

The existing .NET reference program exports only years before 2029, so its independent comparison covers 2022–2028. The 79-year comparison uses existing reconciliation exports, which were produced with a related Python decoding workaround. These are distinct checks with different independence and coverage limits.

The observed maximum country forecast reconciliation residual was about `0.00715` in stored model monetary units. This milestone reproduces that diagnostic; it does not establish whether the residual represents storage precision, another mechanism, or a model defect. No causal conclusion is made.

The equality example (`I` versus `IGCF`, `atol=0.001`, `rtol=1e-6`) passes for the first stored year and fails in the subsequent 78 years. This is an observed numerical distinction, not a claim that the variables should be identical.

Generating code versions, scenario provenance, and saved-run currency base year remain unverified. Only the selected pilot variables and format have been validated; arbitrary historical stores and weighted aggregation are not supported by this milestone.

## Re-run

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B scripts/validate_pilot.py
```

The integration script accepts `--registry`, `--reference-tool`, and `--reference-exports` to locate corresponding resources on another machine. It requires the .NET runtime only for the independent reference check, not for normal Python analysis.
