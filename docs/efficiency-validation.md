# Efficiency milestone validation — 24 September 2026

## Delivered

The local application now has incremental structural navigation, optional local semantic retrieval, per-investigation evidence notebooks, duplicate read reuse, a separate bounded writer, usage accounting, and explicit partial outcomes. Setup and operating instructions are in [efficient-investigations.md](efficient-investigations.md).

The pilot index contains 53 source files and 144,675 structural records. The conservative parser reported 6,885 warnings; these are limitations to inspect, not compiler errors. The prepared semantic corpus contains 12,391 chunks: 7,924 code, 2,598 wiki, and 1,869 variable metadata chunks. Embeddings run locally. The completed build reused 8,775 vectors and embedded the remaining 3,616. Source integrity checks found no changes to the 53 registered source files.

## Automated and offline checks

The full suite passed 127 tests before the final execution-context annotation change. After that change, the structural/retrieval/workflow suite passed 12 tests, including a new initialization-versus-forecast regression; all 18 agent tests also passed after the change. Python source and scripts compile successfully. Test logs and inventories are under workspace/.

The offline evaluator completed with semantic search active. It compares fixed-query legacy lexical search, textual search over the new chunks, structural lookup with supplied symbols, and hybrid retrieval. Structural lookup found the expected code files for five code cases. Hybrid top results chiefly favored documentation and variable metadata; this does not establish improved direct code-path retrieval or causal answer quality. Concept-to-symbol retrieval is useful: a metadata-restricted crop-yield query retrieves YL. The configurations are not equivalent adaptive agents, and their scores must not be represented as end-to-end answer accuracy.

Browser checks confirmed partial status, token accounting, clickable evidence IDs, and full artifact display. The key remains memory-only.

## Live DeepSeek checks

Four runs used the existing configured connection without retrieving or persisting its key:

| Run | Result |
| --- | --- |
| Initial notebook/writer run | Failed: writer reasoning consumed its output allowance. This motivated disabling thinking specifically for the official DeepSeek writer endpoint. |
| Writer recovery run | Bounded partial fallback after two invalid writer responses. The original validation reasons were not recorded, so their cause is unknown. Diagnostic logging was subsequently added. |
| Narrow YL assignment question | Cited partial prose matching the inspected assignment; 7 model requests and 8 tool executions. Browser evidence links worked. |
| Full yield/poverty question | Cited partial prose; 11 model requests, 32 tool executions, about 59 seconds, and 186,920 provider-reported input plus output tokens. Human review found substantive interpretation errors. |

These runs are debugging checks, not a controlled before/after cost experiment. Historical token accounting is incomplete. **No token-saving percentage or answer-quality pass is established.**

## Open quality finding

The broad answer described a first-year agricultural wage cap as though it applied generally. The inspected Economy.Forecast.vb cap was inside an `If IY = 1 Then` branch; forecast behavior begins in the later `Else` branch. The answer also generalized an initialization growth rule and inferred a distributional/poverty direction without demonstrating all connecting assignments.

The final changes attach routine and branch contexts to code reads and require the writer to preserve year/branch conditions and label missing links as hypotheses. A deterministic regression verifies preservation of first-year and later-year contexts. **The broad live question has not been rerun after this mitigation; the interpretation defect is not yet demonstrated fixed.** Citation validation checks that evidence exists, not that each conclusion follows from it.

## Remaining acceptance work

- Review the broad yield/poverty answer against complete connecting assignments and scenario-specific saved results before accepting a causal conclusion.
- Run the ten-case checklist across representative provider/model configurations, including numerical answers against the saved reference calculations. The checklist is not a set of verified reference answers.
- Compare repeated runs under matched settings to establish whether notebook compaction, structural navigation, and semantic retrieval reduce tokens while preserving quality.
- Test a configured local chat model; none was supplied for live validation.

The numerical reader and its existing regression suite remain available. IFs execution and unrestricted generated-code execution are outside this milestone. Code/results generating-version compatibility remains unknown.

The current browser can be refreshed for the new UI, and newly spawned investigations import the updated worker. The already-running server needs a later restart to adopt the parent-server change that retains partial answers in follow-up history. Restarting will require re-entering the memory-only API key.
