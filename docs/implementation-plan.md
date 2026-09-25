# Implementation plan

## Current implementation status

The separately approved **verified local analysis core** milestone is implemented: pilot resource registration, read-only extraction, equality checks, GDP ranking, reconciliation, reproducible Python jobs, CLI, and validation. See `validation.md` and `resource-inventory.md`. This completes the selected first slice, not all features listed in the broader roadmap below. Model execution, AI-generated Python execution, code-investigation tools, MCP, and UI remain deferred.

## Outcome

Deliver a local application with a replaceable model connection and a reusable MCP tool service. Users can inspect IFs mechanisms, calculate answers from saved outputs, and assemble evidence-backed investigations without running IFs.

Build vertical slices: trustworthy extraction first, a combined research/analysis case second, then broader coverage and packaging. A chat interface is not a substitute for verified data semantics.

## Phase 0 — Establish sources and evidence contracts

Deliverables:
- Resource manifest selecting one authoritative code tree, documentation sources, saved-results locations, and available scenario definitions.
- Inventory of result formats and metadata: code version, scenario identity, years, geography, dimensions, units, currency basis, aggregation rules, and missing-value conventions.
- Inventory of documentation formats and extraction needs; include compiled help only after selecting an extraction method.
- Ten to fifteen real questions, with at least three reviewed end-to-end examples.

Acceptance:
- Every selected resource has an identity and provenance; unknown fields are explicitly unknown.
- Backup and alternate code trees are excluded from default retrieval.
- Sources remain unchanged during inspection.

Open decisions to resolve from evidence: authoritative repository/branch or release; expected saved-result formats; availability of scenario setup and generating versions; country/group mappings; first deployment operating system.

## Phase 1 — Build a trustworthy saved-results reader

Deliverables:
- Read-only adapter for the first supported `.run.db` format and its variable payloads.
- Variable and dimension catalog, including country identifiers and aggregation metadata.
- Complete, bounded extraction into analysis tables; large selections become local artifacts rather than huge model messages.
- Dataset fingerprints and explicit selection manifests.
- Compatibility tests against independently reviewed exports or the existing IFs reader.

Existing references:
- `../analysis/investment-reconciliation/check.py` demonstrates SQLite/Parquet extraction and a legacy integer-encoding workaround.
- `../ifs-modernization/IFsWeb-Modern/server/Features/Variables/IfsVariableQueryService.cs` demonstrates variable metadata, dimensions, scenarios, and query semantics.

Do not copy the Parquet monkey patch blindly. Reproduce its necessity with representative fixtures and choose a supported decoder or isolated compatibility adapter. The existing .NET reader is a possible bridge if Python decoding cannot establish parity.

Acceptance:
- Representative variable values and dimensions agree with the reference within justified precision.
- Missing, duplicate, invalid, and truncated records are detected.
- Dataset reads produce no source writes or sidecars.
- An all-years query proves coverage and does not silently apply an output-row limit.

## Phase 2 — Standard analysis and flexible local Python

Deliverables:
- Standard operations: scenario comparison, annual changes, absolute growth, percentage growth, CAGR, rankings, aggregation, and identity checks.
- A small Python API over the verified reader so generated code does not invent storage or variable semantics.
- Worker execution with a dedicated environment, time and output limits, cancellation, and per-analysis artifact folders.
- Saved script, inputs manifest, logs, tables, and charts for every execution.
- An execution-isolation decision appropriate to the target OS. A virtual environment is dependency isolation, not a security sandbox.

Acceptance:
- Reviewed world-equality and GDP-ranking cases produce reproducible results.
- Equality checks use explicit absolute/relative tolerances, report missing coverage, and identify failing years.
- Aggregations use documented rules; unsupported or unknown rules cause a clear limitation instead of guessed arithmetic.
- Rerunning the stored script against the same inputs reproduces the finding.

Start with fresh Python workers for reproducibility. Add persistent Jupyter sessions only if iterative usage demonstrates a need.

## Phase 3 — Code and documentation investigation

Status: initial lexical implementation and wiki backend validated on 2026-09-24. See [Phase 3 verification](phase3-validation.md). Source/result compatibility and combined numerical diagnoses remain Phase 4; compiler-resolved dependencies are not claimed.

Pardee Wiki ingestion must follow [the approved-first, latest-fallback policy](wiki-policy.md). Prefer a verified approved revision; otherwise retrieve the latest revision and disclose its fallback status and reason. Implement and verify revision selection and citation labeling before indexing wiki content.

Deliverables:
- Exact code search, routine reads, declarations, assignments, and reference searches.
- Documentation extraction with page/section or equivalent source locators.
- Variable catalog linking code symbols, descriptions, saved-result variables, and metadata; uncertain mappings remain explicit.
- Initialization and forecast-stage navigation, including conditions, bounds, lags, and later overwrites.
- Source citations tied to a snapshot.

Acceptance:
- Reviewed mechanism explanations cite relevant executable statements and documentation.
- Search distinguishes active source from backup/generated/reference copies.
- Lexical references are not presented as compiler-resolved dependencies.
- Direct equation effects are distinguished from net model behavior.

Use the existing backend audit as a navigation aid, not proof of a causal graph. Add language-aware parsing incrementally where lexical search fails. The live yield/poverty trials revealed retrieval and synthesis gaps. The efficiency milestone adds optional local hybrid search and bounded structural navigation; see [Efficient investigations](efficient-investigations.md).

## Phase 4 — Combine mechanisms and numerical evidence

Status: code-first investigation backend implemented. The supplied executable code controls the explanation; a user expectation is not presumed correct. See [the investigation guide](investigation-guide.md). The real I/INVS case is numerically consistent but retains unknown generating provenance/setup. Supported and deliberately perturbed outcomes are verified on a separate synthetic balance fixture.

Deliverables:
- Investigation record: question, expected relationship, preconditions, source evidence, scenario setup, dataset selection, Python calculation, findings, and limitations.
- Checks for identities, bounds, reconciliation relationships, and conditional scenario responses.
- Explicit outcomes: supported, potential inconsistency, insufficient evidence, or incompatible inputs.

First combined case: explain I versus sector-summed INVS from the supplied implementation, distinguishing initialization, inventory accounting, and possible overwrites. Saved results illustrate and conditionally check that relationship; unknown version/setup attribution does not block the code explanation. The generic runner does not contain an investment-specific rule.

Acceptance:
- At least one supported case and one deliberately perturbed test fixture are correctly classified.
- An unexplained mismatch is not automatically labeled a model bug.
- Missing intermediate variables, unknown scenario settings, and code/results version mismatches are surfaced.
- Saved-output correlations are not presented as proof of causality.

## Phase 5 — MCP, model adapters, and a thin local UI

Status: local prototype implemented, with shared tools, Responses, Chat Completions and native Anthropic Messages adapters, official-SDK stdio MCP, source settings, scoped wiki refresh and a browser chatbox. Protocol fixtures, Windows worker cancellation and a separate official MCP client are tested. Real online/local model evaluation remains an open acceptance gate; the user elected to configure Settings after implementation. See [the agent guide](agent-guide.md).

Define transport-neutral tool contracts from Phase 1; expose the stable tools here.

Deliverables:
- Local MCP server exposing source, results, analysis, and evidence tools.
- Provider adapters tested with one online model and one local model with tool support.
- Bounded tool loop, context budgets, cancellation, recoverable errors, and concise artifact summaries.
- Local chat UI with model settings, source status, citations, analysis artifacts, and inspectable executed code.
- Credentials stored outside committed configuration, preferably through OS credential storage.

Acceptance:
- The same evidence tools work through the in-house interface and a second MCP client.
- Both selected models complete the supported pilot tasks; differences are recorded rather than masked.
- Online-provider requests make clear what selected context leaves the computer.
- No API key is required for a fully local configuration.

## Phase 5 follow-up — Efficient investigations

The implementation adds stage/token accounting, incremental VB structural navigation, local hybrid retrieval, a durable evidence notebook, repeated-request reuse, and a separate bounded writer. Ten evaluation checklists and an offline retrieval comparison are included. Parser limitations, partial answers, and missing token counters remain explicit. Full live-model quality and efficiency acceptance must be assessed from repeated reviewed cases, not unit tests alone. See [the efficiency guide](efficient-investigations.md).

## Phase 6 — Updates, distribution, and pilot

Deliverables:
- Managed Git checkout following a selected branch or release; updates separate from user development checkouts.
- Atomic snapshot/index switching; an active investigation stays on its original snapshot.
- Last-known-source offline operation and visible source age/version.
- Local installation/launch/update instructions, dependency packaging, and recovery guidance.
- Pilot with a small internal group and regression evaluation after changes.

Acceptance:
- A colleague can install, select sources/model, and reproduce a reviewed case from the guide.
- Updating code does not silently relabel older results as generated by the new version.
- Existing investigations retain source fingerprints and sufficient evidence to inspect their conclusions.

## Milestones and prioritization

1. **Numerical prototype:** Phases 0–2. Trustworthy saved-output questions, without a chat UI.
2. **Research prototype:** Phases 3–4. One mechanism-to-result investigation demonstrated end to end.
3. **Usable local agent:** Phases 5–6. MCP interoperability, model choice, UI, and colleague installation.

These are completion gates, not calendar estimates. Estimate effort after Phase 0 and the first reader compatibility test: result-format differences and metadata availability are the largest current uncertainties.

## Deferred scope

Model execution; automatic source fixes; all historical versions indexed at once; exhaustive whole-program causal graphs; multi-user hosting; autonomous bug declarations; support for every provider at launch.
