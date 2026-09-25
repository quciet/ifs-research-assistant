# Tests

Run the synthetic suite from the project root:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Fixtures are generated in `workspace/tests`, then removed after their SQLite connections close. They include precomputed World rows to verify these are excluded from country sums, explicit sector membership, missing years/rows, duplicate keys, bad dimensions, null/infinite values, unsupported aggregation, incompatible currencies, zero-start growth, and replay/source checks.

Real-data validation is separate:

```powershell
.\.venv\Scripts\python.exe -B scripts/validate_pilot.py
```

This requires the registered local sources, prior reconciliation exports, .NET runtime, and existing ParquetTools binaries. It copies the reader into the project workspace, compares representative decoded data independently, verifies full-horizon reconciliation, executes/replays ranking jobs, and checks source hashes/directory entries. It does not execute IFs.
