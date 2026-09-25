# IFs Research Assistant

**[Documentation home](docs/README.md)** · [How it works](docs/how-it-works.md) · [Install and sync](docs/setup-and-sync.md) · [Validation and limitations](docs/efficiency-validation.md)

## Local chat and MCP prototype

Start the local chatbox with `scripts/start-agent.ps1` after installing the agent extra with `scripts/setup.ps1 -Agent`. Open **http://127.0.0.1:8765** and configure the model in **Settings**. On a new machine, supply your own IFs development folder and refresh the wiki; local resources are not included in Git.

See [the agent guide](docs/agent-guide.md) for model settings, source-folder registration, MCP configuration, execution limits and validation. Provider protocols and MCP are tested; DeepSeek pilot evaluations have started, with open answer-quality findings. Unfamiliar IFs result versions require a reviewed numerical profile.


Local, read-only analysis of saved IFs model results, IFs code navigation, and revision-aware Pardee Wiki search. The implemented backend provides Python interfaces and command-line tools. The optional agent layer adds provider connections, local chat and MCP. It does not run IFs.

## Implemented

- Registered IFsBase and Working datasets, with schema/resource inventory and SHA-256 provenance.
- Variable metadata, named dimensions, labels, filtered extraction, and explicit completeness reports.
- World equality checks for reviewed SUM variables, with user-specified tolerances.
- Country GDP rankings by absolute change, percent change, or CAGR over an explicit period.
- Investment reconciliation regression analysis.
- CSV results, evidence JSON, input fingerprints, execution logs, and replay scripts.
- Dedicated-process compatibility decoding for the observed legacy Parquet format.
- Wiki sync with verified approved revisions, explicitly labeled latest fallbacks, immutable snapshots, and offline section search. The selected core covers 20 articles and 873 section headings beneath the model-documentation and scenario-guide roots.
- Source-code snapshots, identifier references, likely assignments/declarations, routine reads, and variable catalog links.
- Five reviewed documentation retrieval examples and source-grounded mechanism notes.
- Code-first investigation records, source-bound explanations, conditional numerical checks, country-level diagnostics, and replayable evidence bundles.
- A reviewed I-versus-INVS example, with general-purpose expressions and an unrelated synthetic regression case.

Start with the [wiki and code guide](docs/research-guide.md) for Phase 3 commands and the [Phase 3 validation report](docs/phase3-validation.md) for results.

For Phase 4, see the [code-first investigation guide](docs/investigation-guide.md).

## Windows setup

Python 3.12 is the validated runtime. From this folder, run:

```powershell
.\scripts\setup.ps1
```

If Python is installed at a custom path:

```powershell
.\scripts\setup.ps1 -Python 'C:\path\to\python.exe'
```

The setup creates `.venv` and installs the package with pinned dependencies. Initial installation requires access to the Python package index; normal analysis runs offline. No activation is required. Each machine creates its own `.venv`.

The default resource manifest expects the existing `../ifs-872` sibling folder. Edit `resources/pilot.json` to register different locations; relative paths resolve from the manifest's directory. Do not change the reviewed country/sector membership to accommodate a different dataset without checking its semantics.

## Commands

Run from this project folder:

```powershell
.\.venv\Scripts\python.exe -m ifs_analysis --registry resources/pilot.json datasets
.\.venv\Scripts\python.exe -m ifs_analysis --registry resources/pilot.json --output workspace/inventory inventory
.\.venv\Scripts\python.exe -m ifs_analysis --registry resources/pilot.json describe --dataset IFsBase --variable GDP
.\.venv\Scripts\python.exe -m ifs_analysis --registry resources/pilot.json extract --dataset IFsBase --variable GDP --first-year 2022 --last-year 2050 --filter country_id=34,180
.\.venv\Scripts\python.exe -m ifs_analysis --registry resources/pilot.json equality --dataset IFsBase --x I --y IGCF --atol 0.001 --rtol 0.000001
.\.venv\Scripts\python.exe -m ifs_analysis --registry resources/pilot.json gdp-ranking --dataset IFsBase --first-year 2022 --last-year 2050 --metric cagr
.\.venv\Scripts\python.exe -m ifs_analysis --registry resources/pilot.json reconciliation --dataset Working
```

`--output` is a global option, placed before the command. Calculation commands print the job folder. `ifs-analysis` is also installed under `.venv/Scripts`.

Each completed job contains `results.csv`, `evidence.json`, `manifest.json`, `execution.log`, and `analysis.py`, plus an `implementation/` archive of the executed package source. Replay a job with:

```powershell
.\.venv\Scripts\python.exe workspace/jobs/JOB-ID/analysis.py
```

Replay creates a new job and verifies identical CSV bytes. It refuses changed sources, package code, Python, or recorded dependency versions. An equality calculation completing successfully does not mean the variables were equal: inspect `equal` in the CSV or `all_equal` and `failing_years` in the evidence.

## Python API

```python
from ifs_analysis import Registry, Reader, check_equality, rank_gdp

reader = Reader(Registry('resources/pilot.json'), 'IFsBase')
selection = reader.extract('GDP', 2022, 2050, {'country_id': [34, 180]})
selection.require_complete()
print(selection.table)
print(selection.metadata)

ranking, evidence = rank_gdp(reader, first_year=2022, last_year=2050, metric='percent')
equality, evidence = check_equality(reader, 'I', 'IGCF', atol=0.001, rtol=1e-6)
```

Use `ifs_analysis.jobs.run_job` when you need automatic provenance and saved replay artifacts. Direct Python functions return results without writing files.

## Interpretation and limits

- World means the registered 188 IFs country/territory entries. Precomputed aggregate regions are not added to that sum.
- Aggregation currently supports reviewed SUM variables only. Weighted means and ratios are rejected, not guessed. General extraction is available for other variables within the configured payload limit.
- Extra dimensions may be summed only with reviewed rules; extraction preserves their keys and labels.
- Equality uses `abs(x-y) <= atol + rtol * max(abs(x), abs(y))`. Both tolerances are mandatory; examples are analysis choices, not universal IFs correctness thresholds.
- Growth requires a start/end year and metric. Percent and CAGR exclude nonpositive starting values or negative ending values, retaining those rows with exclusion reasons. CAGR is an annual percent; absolute growth uses stored model units. Ties share ranks.
- The reader checks every intervening year, not only endpoints. Null/nonfinite observations and missing rows prevent complete-data analyses. Numeric sentinel conventions beyond those checks are not established.
- The first stored year is labeled separately, without assuming all initialization identities also hold in forecast years.
- The generating code version and dollar base year of these saved runs are unverified. The current variable dictionary says GDP is in billion 2021 dollars, but this is reported as dictionary metadata, not proof of the saved run's base year.
- The current IFsBase and Working result files are byte-identical. They do not demonstrate different scenario outcomes.
- `Working.Sce` is a nearby scenario definition; its relationship to `Working.run.db` is unverified.
- The five-million-row budget applies to a full variable payload. This prototype decodes selected variables into memory; it does not stream arbitrarily large bilateral datasets.
- A completed numerical check is not a causal explanation or a model-bug verdict.

## Verification

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B scripts/validate_pilot.py
```

Unit tests use synthetic databases under `workspace/tests`. Pilot validation requires the local IFs datasets, existing reconciliation exports, and .NET 8 runtime. It copies the existing ParquetTools reader into this project's workspace and never builds or runs IFs. See [validation notes](docs/validation.md) for results and limitations.

## Project documents

- [Resource inventory](docs/resource-inventory.md)
- [Implementation plan](docs/implementation-plan.md)
- [Code-first investigations (Phase 4)](docs/investigation-guide.md)
- [Phase 4 verification](docs/phase4-validation.md)
- [Wiki milestone specification](docs/next-milestone-wiki.md)
- [Wiki and code investigation guide](docs/research-guide.md)
- [Core wiki coverage and unavailable links](docs/core-wiki-coverage.md)
- [Phase 3 verification](docs/phase3-validation.md)
- [Architecture](docs/architecture.md)
- [Wiki policy: approved first, latest fallback](docs/wiki-policy.md) — implemented and tested
- [Evaluation plan](evals/README.md)

Generated indexes, datasets, jobs, and local environments are ignored by Git. The source package, tests, resource manifests, and guides belong in version control.

## Efficient local investigations

For structural code navigation, optional local semantic search, per-stage usage reporting, the evidence notebook, and the bounded answer writer, see [the efficiency guide](docs/efficient-investigations.md). On Windows, `scripts/setup.ps1 -Semantic` prepares the optional local embedding model and indexes. Source text is embedded locally; online chat still sends selected evidence to the chosen provider.
