# Local IFs agent prototype

The Phase 5 implementation adds a browser chatbox, provider adapters and an MCP server on top of the existing verified tools. It does not execute IFs or arbitrary model-written Python. Model-authored causal explanations remain interpretations requiring review.

## Start on Windows

From the project folder, with Python 3.12 installed:

```powershell
.\scripts\setup.ps1 -Agent
.\scripts\start-agent.ps1
```

Open **http://127.0.0.1:8765**. The server listens only on loopback; there is no hosted website, cloud deployment or application hosting subscription. API usage or local-model hardware costs are separate.

In **Settings**:

1. Select the IFs development folder. On this machine, leaving it blank uses the existing 8.72 pilot registration. Other installations are indexed in an isolated project workspace.
2. Choose OpenAI (ChatGPT), Google (Gemini), Anthropic (Claude), or DeepSeek (DeepSeek). The base URL and protocol fill automatically. Custom / local server keeps manual endpoint and protocol configuration available.
3. Paste your API key. For a preset, the available-model dropdown loads automatically after entry. Select a returned model and save. **Fetch models** retries discovery and works with custom compatible servers too; a manual model identifier remains available if discovery is unsupported. Local servers may leave the key blank.

OpenAI uses **Responses** and `https://api.openai.com/v1`. A tool-capable Ollama server can use **Chat Completions** and `http://127.0.0.1:11434/v1`. Use the actual model installed on that server; the assistant does not install or start models. Other OpenAI-compatible APIs can be configured, but compatibility is not guaranteed for every provider or model. Claude uses its native Anthropic Messages/tool format. Gemini uses its documented OpenAI-compatible API. Native Gemini generateContent, Vertex AI, Azure and Bedrock authentication are not implemented.

The model list comes from the selected API and is not a hardcoded list of releases. A listed model is not automatically proven to support this assistant’s tools; the UI states that limitation. Switching providers or editing the endpoint/protocol clears the entered key and stale model choices. Discovery can reuse a saved in-memory key only for the exact same endpoint and protocol, and does not save a newly entered key or change the active connection. Failed discovery leaves manual entry available.

Keys stay in server memory until the process closes. A blank key field keeps the current key for the same endpoint; changing endpoints or protocols clears it unless a new key is entered. **Clear the current in-memory key** removes it. Keys are not persisted in settings or supplied as model context. Do not enter credentials into chat. Non-secret settings are saved in `workspace/agent/settings.json`.

Online endpoints receive questions and selected tool evidence, including source excerpts, metadata and result previews. The Settings panel states this before use. A loopback model endpoint avoids an online LLM request. Explicit wiki refresh still makes public requests to Pardee Wiki.

**Refresh wiki** retrieves the two configured roots and linked scoped articles, preferring verified approval with labeled latest-revision fallbacks. **Reindex code** creates a new source snapshot after local edits. These actions reset conversation context; do them between investigations. The existing CLI remains available for larger syncs and detailed diagnostics. A first installation without a wiki cache must refresh it before documentation research is available.

## What works, and what remains conditional

- Shared tools: source status, variable metadata, code search/read/routines, revision-aware wiki search/read, reproducible extraction, worldwide equality, GDP rankings, bounded conditional investigations and artifact paging.
- Results calculations use the existing completeness and aggregation checks. GDP period and metric, equality period and tolerances are explicit tool inputs.
- The folder connector recognizes translated `Code.Ifs-Translation/src/IFs.Core`, `src/IFs.Core`, `IFs.Core`, and supported direct VB/C# source roots. Unsupported layouts return an explanation instead of guessing.
- Automatic numerical registration currently accepts only result files whose SHA-256 matches the reviewed pilot profile in `resources/result-profiles.json`. This also works for a relocated byte-identical copy, without the original pilot folder. An unfamiliar version can use code and cached documentation; its saved-result format, membership and aggregation profile require review before numerical tools are enabled. Arbitrary-version numerical onboarding is not complete.
- The `investigate` tool assembles exact source hashes itself and allows only the existing weighted-sum/floor check language. Model-supplied provenance paths are forbidden and scenario/precondition claims remain unknown. `agent-evidence.json` and `agent-report.md` explicitly label the interpretation as model-authored and pending review. The underlying Phase 4 artifacts are retained separately for replay.
- Full artifacts contain tables, execution logs, input fingerprints and a replay script. Sidebar previews are bounded and explicitly labeled; **Open** displays pages of the complete saved text, including the executed script. The script calls registered Python functions; it is not arbitrary code generated by the LLM.
- No full causal graph, compiled call resolution, IFs execution, autonomous bug declarations, arbitrary Python execution or source modification is exposed.

## Runtime boundaries

The chat loop allows at most 16 model requests (14 research plus writer and one optional correction), 32 requested tool calls, 8 executed calls per response, and approximately 140,000 serialized context characters (a compact notebook replaces the full transcript), 6,000 requested output tokens per response and 300 seconds per UI job. HTTP requests time out after 60 seconds of inactivity and responses are bounded at 2 MB; the parent job deadline covers a slow streaming response. Smaller models may need narrower questions; these limits do not guarantee every model's context capacity.

Windows jobs own the worker process tree. **Stop** terminates the worker and legacy decoder descendants; partial local outputs are not declared completed findings. This ownership behavior is verified on Windows. Other operating systems have not passed this milestone's acceptance testing.

The HTTP interface checks loopback Host, Origin and a per-process request token; it does not enable CORS. Retrieved content is rendered as inert text. Provider requests do not follow redirects or use ambient proxy credentials. Trusted local processes remain within the local machine trust boundary; this is not a multi-user service or an arbitrary-code sandbox.

Conversation/tool logs live under `workspace/agent/conversations/`. The server retains up to 12 user/assistant messages; the most recent six provide follow-up context; exact retrieved evidence must be fetched again when needed. Browser reload restores the current process's visible event trace, but prior chats are not automatically loaded after a restart. New chat clears active model context without deleting saved logs. Changing model/source settings also resets context.

## MCP integration

An external MCP client supplies its own model. It does not need to use the in-house chatbox or its provider settings. Configure a local **stdio** server using the absolute Python and config paths:

```json
{
  "mcpServers": {
    "ifs-research": {
      "command": "D:\\IFs Dev Code\\ifs-research-assistant\\.venv\\Scripts\\python.exe",
      "args": [
        "-m", "ifs_agent", "--project", "D:\\IFs Dev Code\\ifs-research-assistant",
        "mcp", "--config", "D:\\IFs Dev Code\\ifs-research-assistant\\resources\\research.json"
      ]
    }
  }
}
```

For a different registered installation, use its `research.json` under `workspace/agent/installations/`. Standard output is reserved for MCP messages. The official Python MCP client has been tested against this server as a separate subprocess. Individual desktop clients may use different configuration screens; no claim is made that Claude Desktop or Cherry Studio has been exercised here.

MCP hosts control their model loop, timeouts and cancellation; the UI's process-tree deadline is specific to the in-house chat. Cancelling an MCP request does not forcibly terminate a Python tool already running in the SDK worker thread. Those tools can finish writing local analysis artifacts; they cannot alter IFs inputs or execute arbitrary code.

## Validation and remaining release gates

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/validate_investigation.py
```

`scripts/ui_smoke_agent.py` starts an explicitly **simulated** provider fixture on ports 8766/8767 for browser testing against actual pilot evidence. It does not test an LLM's reasoning. It stores outputs under `workspace/ui-smoke/` without changing normal Settings.

Both API protocols are covered by HTTP fixtures that request real tools and consume their results; tests also exercise MCP, malformed arguments, unknown provenance, source changes, credential redaction, HTTP origin checks, context budgets and Windows cancellation including descendants. See `docs/phase5-validation.md` for the current results.

**Release evaluation:** DeepSeek online pilot testing has started; a local tool-capable model is not configured. Continue evaluating both model types on code explanation, explicit GDP ranking, and conditional I/INVS investigation. Record unsupported tool behavior and model errors rather than treating protocol fixtures as model evaluations. Phase 5's live-model acceptance gate remains open. Distribution/update packaging and broader IFs-version numerical onboarding remain Phase 6 work.

Protocol references: [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling), [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility), and [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).


Provider discovery references: [OpenAI models](https://developers.openai.com/api/reference/resources/models/methods/list), [Gemini compatibility and model listing](https://ai.google.dev/gemini-api/docs/openai), [Anthropic model listing](https://platform.claude.com/docs/en/api/models/list), [Claude tool schemas](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools), and [DeepSeek model listing](https://api-docs.deepseek.com/api/list-models/).

Provider-settings validation adds eight tests for live-response model identifiers, native Claude tool round trips, pagination, failed requests, redirects, malformed/oversized lists and credential isolation. Live account access still requires the user’s own key; these tests use simulated provider responses.


### Efficient investigation workflow

The current notebook, structural index, local semantic retrieval, usage accounting, and separate writer replace the earlier overflow-only context handling. See [Efficient investigations](efficient-investigations.md) for setup, limits, evaluation and explicit parser limitations.

Older evidence is saved intact in artifacts and referenced by evidence IDs. Each research request receives a compact notebook and selected original excerpts. Completed requests are reused; omitted content is not treated as fully read. The writer has no tools and receives at most one correction attempt. Partial and failed runs are never labeled completed findings.
