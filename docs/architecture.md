# Architecture

The current application has five layers: local chat or external MCP client; provider adapter and bounded investigation loop; shared ToolService; code/wiki retrieval and registered numerical functions; read-only sources plus local evidence artifacts. See [how it works](how-it-works.md) for a plain-language walkthrough and [efficient investigations](efficient-investigations.md) for the implemented notebook, structural and semantic retrieval, and writer.

The sections below preserve the original architectural direction. Operations labeled proposed are not a claim that arbitrary Python execution or every planned tool is available. Current interfaces live in `src/ifs_agent/tools.py`, with core packages under `src/ifs_research`, `src/ifs_analysis`, and `src/ifs_investigation`.

## Boundaries

```text
Local chat UI / external MCP client
           |
Model adapter + bounded investigation loop
           |
Transport-neutral IFs tools / local MCP interface
           |
Source catalog | Results reader | Analysis worker | Evidence store
           |
Read-only IFs sources and saved outputs
```

The in-house application may call tool functions directly. MCP exposes the same operations for external clients; it is neither the Python execution environment nor the model provider protocol.

## Initial technology direction

- Python core for extraction and analysis, with a possible .NET compatibility bridge if required by saved results.
- SQLite for local catalog, provenance, and session metadata.
- Filesystem artifacts for extracted tables, scripts, figures, and logs.
- A small local web UI after numerical and combined evidence workflows are demonstrated.
- Dedicated Python worker processes initially; persistent kernels optional later.

Exact libraries and versions should be selected and verified during implementation, not locked by this planning scaffold.

## Tool families

| Family | Proposed operations |
|---|---|
| Sources | `list_sources`, `get_source_status`, `search_code`, `read_routine`, `find_references`, `search_documentation` |
| Metadata | `lookup_variable`, `get_dimensions`, `get_aggregation_rule`, `get_scenario_setup` |
| Results | `list_result_sets`, `extract_results`, `inspect_selection` |
| Standard analysis | `compare_series`, `aggregate_results`, `rank_growth`, `check_identity` |
| Python | `execute_analysis`, `get_execution_status`, `cancel_execution`, `read_artifact` |
| Evidence | `create_investigation`, `record_finding`, `export_investigation` |

Tools accept registered resource IDs and validated selections. Avoid exposing arbitrary database SQL as the primary results interface. Python accesses prepared tables or the verified reader API. Execution permissions are controlled by the application, not instructions alone.

## Data and evidence contracts

Results retain dataset/scenario ID, variable, year, named dimensions, value, units and currency basis when known, aggregation rule, and provenance. Tables may vary in dimensions; do not assume every variable has only country and year.

Every extraction reports selection, total/returned counts, completeness, missingness, and the input fingerprint. Every finding links the executed script and outputs to its source snapshot and result selection.

World-level checks define country membership, treatment of aggregates, missing values, and weights. Never sum both countries and their precomputed groups.

An identity check defines absolute and relative tolerances, applicable years, units, and required dimensions. Precision thresholds must reflect the stored values and accumulation behavior; converting values to float64 cannot recover precision lost in storage.

## Resource policy

Use one selected latest code snapshot for default investigation. Track the generating code version of each results dataset separately. If unknown or incompatible, quantitative descriptions remain possible but implementation-based diagnosis is qualified.

Git synchronization is a managed maintenance operation. It cannot replace the snapshot beneath a running analysis. Documentation versions and scenario files are evidence with their own identities, not assumed matches to a result filename.
