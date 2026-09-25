# Phase 5 validation — 2026-09-24

Status: **local prototype implemented; live-model acceptance pending user configuration**.

- Full suite: **100 tests passed**, Windows / Python 3.12.14. Log: `workspace/phase5-all-tests.log`.
- The final relocated-profile discovery change also passed its targeted test after the full suite. It verifies code-only fallback and registration by a reviewed fingerprint without an original pilot installation.
- Both provider protocols were exercised against local HTTP fixtures: a simulated model requested an actual code tool, received its cited output, and returned a fixture answer. Responses reasoning items were carried into the subsequent request. These are protocol tests, not model-quality evaluations.
- A separate official MCP Python client initialized the stdio server, listed tools, read source evidence and received a tool error for an invalid artifact path. SDK: 1.30.0.
- Windows process cancellation stops the worker and an independently spawned child, verified through the child process handle. API credentials are excluded from persisted settings and worker logs. Changing endpoints clears the prior key.
- HTTP tests reject foreign origins, incorrect Host values and requests without the per-process token. Other tests cover malformed/unknown tools, nonfinite tolerances, path traversal, bounded artifact paging, context exhaustion, recoverable tool errors and source-snapshot changes.
- Model-authored investigations bind actual source hashes, reject supplied provenance paths and retain unknown preconditions. The outward report labels the interpretation as a hypothesis requiring human review.
- Browser verification used the isolated fixture on ports 8766/8767. It executed actual `source_status`, `code_read` and `equality` tools against the 8.72 pilot, displayed progress and the simulated answer, and opened the saved numerical replay script through the artifact viewer. The fixture was then stopped. The normal app on port 8765 remains unconfigured for a model.
- Actual pilot Phase 4 validation and replay passed again. The numerical engine and registered inputs remained unchanged. Investigation: `workspace/research/investigations/20260924T202051-97cea0e6`; replay: `workspace/research/investigations/20260924T202114-88ea4ad6`. Full evidence: `workspace/research/phase4-validation.json`.
- The installed `ifs-agent` command responds correctly, optional dependencies are pinned separately from the numerical core, and `pip check` reports no broken requirements.

## Open acceptance gates

No live online or local LLM has been evaluated; the user explicitly chose to configure Settings after the build. Test both on the supported tasks and record tool-support failures, citation quality, interpretation errors and numerical consistency. Do not replace these checks with the simulated UI fixture.

Unknown IFs versions are currently available for supported code/documentation research only until their numerical profile is reviewed. The connector does not infer generating source provenance from matching saved-result bytes. Native APIs other than Responses, Anthropic Messages and OpenAI-compatible Chat Completions, arbitrary generated Python, broad operating-system support and distribution updates remain outside this prototype.

MCP request cancellation has SDK thread semantics; only the in-house Windows UI provides the tested process-tree cancellation guarantee. Source explanations remain model-generated and are not independently proven by the runner.


## Provider preset follow-up

Added OpenAI, Gemini, Claude and DeepSeek presets with authenticated live model discovery and a manual/custom fallback. Native Claude Messages/tool conversion is now implemented. Eight additional provider tests and the 18 existing agent tests pass (`workspace/provider-settings-tests.log`, `workspace/provider-agent-regression.log`). Browser verification against an isolated local API fixture confirmed automatic fetching after key entry, selection filling the identifier, and provider switching clearing stale model choices. No real provider key was used and no live model/account validation is claimed. Key persistence remains unchanged.
