# How the agent works

The agent is a model connected to a small collection of IFs research tools. The model decides what evidence to request and writes an explanation. Local Python tools retrieve the evidence and perform supported calculations. The model does not know your IFs installation just because you selected a folder: the tools give it access to the relevant parts.

## Three sources of evidence

1. **Your IFs code** explains what the implementation does. Source reads retain the file, snapshot, lines, and available routine/branch context. Initialization and forecast rules can differ even inside the same file.
2. **Pardee Wiki** explains concepts and scenario use. The local cache prefers a verifiably approved revision; otherwise it uses the latest retrievable revision with an explicit fallback label. Documentation may describe a different version from your code.
3. **Saved model results** show actual values. The reader preserves countries, years, other dimensions, metadata and completeness. Results require a reviewed compatibility profile; a new IFs version is not automatically supported for numerical analysis.

Code is the authority for implementation. Documentation provides context. Saved results establish what happened in a particular run. A code/results version relationship that has not been established remains unknown.

## What happens after you ask a question

1. The application pins the source snapshots for the investigation and checks available resources.
2. The model selects tools to search documentation, locate variables, read assignments, inspect routines, or request supported numerical calculations.
3. Every executed evidence tool saves its full output locally and receives a citation ID such as E0001. Repeated identical reads reuse that output.
4. A compact investigation notebook carries selected excerpts, findings, and unanswered questions into the next model request. Full artifacts remain available even when an excerpt is shortened.
5. A separate writing request uses the same selected model, with tools disabled, to turn the evidence into an answer. This is a stage in the workflow, not another autonomous agent.
6. The application checks the response format and citation IDs. It displays an answer, partial investigation, or failure, together with usage and evidence links.

A citation check proves that a referenced artifact exists. It does not prove that the explanation correctly interprets that artifact.

## Example: agricultural yield and poverty

For “When could higher agricultural yield increase poverty?”, the agent should first identify the relevant yield and poverty variables, then inspect the assignments connecting production, prices, incomes, distribution, and poverty in the supplied version. Search matches suggest where to look; they do not establish those links.

Each proposed link needs source support and applicable conditions. A first-year wage cap must not be described as a general forecast rule. A change in one income share does not alone establish the direction of inequality or poverty. Where connecting assignments are missing, the answer should label a hypothesis or say the evidence is insufficient.

If compatible scenario results are available, numerical tools can compare the relevant countries and years. This agent does not run a new IFs scenario. Without the required scenarios, it cannot demonstrate that raising yield caused poverty to rise. The live pilot answer made an initialization/forecast mistake; see the [open validation finding](efficiency-validation.md).

## Why the indexes help

**Exact search** finds identifiers and literal text. **Structural indexing** records likely assignments, inputs, routines and enclosing conditions. It is conservative syntax analysis, not a compiler-resolved causal graph. Changed files can be reparsed without rebuilding every unchanged file.

**Optional semantic search** finds related wording, such as connecting “crop productivity” with yield documentation. Embeddings are computed locally and stored with the local textual index. No separate database server is needed. Semantic similarity is a discovery aid, not proof that two variables interact.

Indexing reduces repeated source discovery. The notebook reduces repeated transcript transmission. Reusing tool outputs avoids duplicate execution. A bounded writer ensures the process reserves an opportunity to answer. Actual savings depend on the question and chosen model; the pilot has not established a cost-reduction percentage.

## Privacy, limits, and control

- The chat interface listens on your local machine. It is not a multi-user organizational server.
- An online model receives your question and selected evidence, potentially including source excerpts and result previews. Local embeddings do not make online chat private.
- API keys remain in server memory and must be entered again after restart. Non-secret settings, logs, indexes, and artifacts stay under workspace/.
- The research tools read IFs resources; they do not edit or execute IFs. Numerical tools call registered Python functions, not arbitrary AI-written programs.
- Context, time, model requests, and tool calls are bounded. A partial answer is expected when evidence or budget is insufficient.
- A listed provider model is not a guarantee that its tool use works correctly. External MCP clients use their own model loop and limits.

See the [agent guide](agent-guide.md) for settings and exact runtime boundaries.
