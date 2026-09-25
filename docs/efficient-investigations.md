# Efficient IFs investigations

This milestone extends the existing application. It does not execute IFs or introduce arbitrary model-written Python execution. Original IFs sources and databases remain read-only.

## Install and prepare on Windows

From the project folder:

```powershell
.\scripts\setup.ps1 -Semantic
```

This installs the agent and optional FastEmbed dependency, downloads the small English embedding model into the research workspace, indexes the supplied code, and computes embeddings locally. The initial CPU build can take substantial time. Later builds reuse completed vectors and parsed files. Downloads fetch model weights; source text is not uploaded for embedding.

For an existing environment:

```powershell
.\.venv\Scripts\python.exe -m ifs_agent index --semantic --download-model
```

Subsequent offline updates:

```powershell
.\.venv\Scripts\python.exe -m ifs_agent index --semantic
```

Use `--config path/to/research.json` for another registered workspace. Without `--semantic`, the command prepares structural and textual indexes only. Chat queries do not download a model. Missing or stale embeddings cause an explicit textual-search fallback, not an online embedding request. Code/wiki refresh updates embeddings when a local model is already configured.

## What changed

### Accounting and outcomes

Every model request records its stage, elapsed time, input character count, and provider-reported token usage. Input, output, cache, and reasoning counters remain distinct; cached/reasoning counters can be subsets and must not be added again. Missing values are null. No prices or savings are guessed.

Tool accounting records execution, reuse, elapsed time, and returned character counts. The browser shows a usage summary and detailed stage totals. JSONL conversation logs retain the same events for evaluation.

An answer event carries `outcome=answered` or `partial`. The worker reports `status=complete,outcome=answered` only when a validated writer response declares an answer and the research stage ended normally. An incomplete investigation reports `partial`; execution/connection failures report `failed`. These labels describe workflow completion, not independent verification of scientific conclusions.

### Structural navigation

`structure.sqlite3` stores per-file parse caches keyed by content hash, path, and parser version, plus snapshot membership and searchable records. Updating one source file reparses that file; snapshot-specific relationships are rebuilt from the corresponding cached records. Older source snapshots remain readable.

The bounded VB parser handles explicit continuation, parenthesized expressions, common implicit continuations, scalar type suffixes, declaration initializers, compound assignments, array target indices, routine boundaries, and enclosing branches/loops. It distinguishes assignment targets from syntactic input references. Routine call candidates include name-matched destinations, but array access versus invocation and overload/scope binding remain unresolved.

This is **not a compiler-resolved dependency graph**. It does not resolve aliases, ByRef effects, dynamic invocation, conditional compilation, every inline statement, or C# semantics. Warnings retain source locations. Missing records are not proof that a relationship is absent. File-based initialization/forecast labels are navigation hints only.

Code reads also attach bounded routine and branch contexts so initialization conditions remain visible beside the excerpt. These annotations are syntactic and may be incomplete; full source remains authoritative.

Agent/MCP tools: `symbol_lookup`, `variable_assignments`, `variable_uses`, and `routine_context`. Symbol queries support optional file restriction and pagination. Exact code search remains available.

### Local hybrid retrieval

`retrieval.sqlite3` holds immutable code chunks, scoped wiki sections, available variable dictionary descriptions, exact-search indexes, and normalized vector blobs. Numpy performs cosine ranking; no database server is required. The default embedding model is `BAAI/bge-small-en-v1.5`, loaded through FastEmbed/ONNX on CPU.

Code chunks follow complete statements where possible. Large statements and sections preserve source spans and explicitly labeled excerpts. Embedding input is bounded and can be shorter than the original chunk. Wiki revision URLs, approval/fallback information, and freshness are retained. Dictionary descriptions retain their database fingerprint and an unverified compatibility notice.

`research_search` combines AND/OR textual rankings with semantic rankings using reciprocal-rank fusion. Exact textual matches receive extra weight. Relevance is not evidence of a dependency or causal effect. The agent must read appropriate source context.

Vectors are keyed by content hash and an identity covering the embedding model files and library version. Incomplete builds cannot activate semantic search for a corpus. Model changes require the appropriate new vectors. Previous corpus IDs remain available to an active investigation. No remote embedding fallback exists.

### Investigation notebook

Each executed evidence tool receives an `E0001`-style ID and a local artifact containing its full result. The notebook retains the original question, tool arguments, successful/failed execution, references to those artifacts, model-proposed findings, and unresolved questions. `record_notes` rejects findings referencing absent or failed evidence.

Each research request starts a fresh conversation turn with a compact notebook and selected original excerpts. It does not resend the entire provider reasoning/tool-call transcript. Excerpts are explicitly truncated when necessary; their full artifacts stay retrievable. Recent direct source reads and numerical results take precedence over search listings. Notes stay labeled as model interpretations, not verified facts.

Identical read-only requests in one investigation reuse prior results. They still count against the requested-call allowance to prevent repeated requests from creating an unbounded loop. Refresh and mutation tools are not in the research tool catalog.

### Separate writer

The default 16-model-request allowance reserves two requests for writing and at most one correction. Research has at most 14 requests and 32 requested tool calls, with at most eight executed from a batch. Research also reserves wall-clock time for writing. The parent worker still imposes a hard timeout and supports cancellation. Numerical schemas are loaded immediately for explicit numerical requests, or on demand with enable_results_tools, rather than sent with every code-only request. Stable research instructions are separated from changing allowance data to help provider prefix caching.

The writer uses the same selected model with no tools and receives the original question, evidence ledger, selected excerpts, hypotheses, and unresolved checks. It returns structured JSON containing status, answer, and unresolved questions. The application checks citation IDs against successful evidence and supplies clickable artifact references. This checks reference existence, **not whether the source entails the claim**.

Malformed tool markup, unknown citations, or incomplete generation receive at most one bounded writer correction. Continued failure yields an honest partial response. On the official DeepSeek endpoint, the writer explicitly disables thinking mode and requests JSON, so reasoning cannot consume its entire answer allowance. Other providers do not receive DeepSeek-specific options.

## Evaluation

See [the pilot validation report](efficiency-validation.md) for executed checks, live failures, and outstanding answer-quality acceptance.

The initial ten-case checklist is in `resources/efficiency-cases.json`. It includes the yield/poverty and investment questions, narrow code navigation, numerical checks, missing-input clarification, scenario guidance, and unavailable evidence. Generated answers are not ground truth.

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_efficiency.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The offline evaluator compares legacy lexical search, text search over the same chunks as semantic search, structural lookup using specified symbols, and hybrid search. It writes `workspace/efficiency-evaluation/report.json` and summarizes available conversation usage logs. Structural lookup has known symbol inputs, so its scores are not directly equivalent to natural-language retrieval. The fixed-query legacy baseline does not reproduce the older agent's adaptive query rewriting. Path/kind hits measure navigation, not causal answer accuracy. Historical logs may lack token counters.

Live evaluation uses a configured model and incurs provider usage. Repeat representative questions across configurations and review mechanisms, conditions, citations, numerical coverage, and version uncertainty before claiming savings or scientific correctness. The deterministic tests exercise malformed responses, bounded correction, repeated calls, source updates, offline fallback, vector reuse/model changes, and structural syntax. They do not substitute for live-model and human interpretation review.

## References for implementation decisions

- [FastEmbed local inference](https://github.com/qdrant/fastembed)
- [Local model cache and offline use](https://qdrant.tech/documentation/edge/edge-fastembed-embeddings/)
- [Visual Basic statements and continuation](https://learn.microsoft.com/en-us/dotnet/visual-basic/programming-guide/language-features/statements)
- [DeepSeek thinking mode](https://api-docs.deepseek.com/guides/thinking_mode/)

Later work can render the structural records as a diagram. A displayed edge would still need to distinguish a syntactic reference from a resolved dependency and from demonstrated model behavior.
