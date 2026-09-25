# Wiki and code investigation: Windows guide

The Phase 3 backend is implemented. Default wiki coverage now follows only the two user-selected documentation roots; see [the core coverage audit](core-wiki-coverage.md). It runs locally through Python or the CLI, without an LLM, a server, or a model run. See [the verification report](phase3-validation.md) for the evaluated pilot and limitations.

## Configure sources

Edit `resources/research.json`. Paths resolve from that file's directory:

- `code_root`: the active IFs source directory. The pilot uses `IFs.Core` inside the 8.72 development checkout.
- `results_registry`: the existing saved-results registry, currently `pilot.json`.
- `workspace`: generated SQLite indexes and reports, currently `../workspace/research`.
- `wiki`: the public Pardee API; the two roots `Understand the Model` and `Guide to Scenario Analysis in International Futures (IFs)`; a 200-title cap, depth ten, and `scoped: true`.
- `protected_roots`: source directories that must never contain generated research files.

Keep generated files inside this project's `workspace` directory. Source files are read only. Code indexing does not build or execute IFs. The numerical source registry remains separate so wiki updates do not invalidate saved numerical jobs.

## First setup and refresh

From the project directory after `scripts/setup.ps1`:

```powershell
.\.venv\Scripts\python.exe -m ifs_research code-index
.\.venv\Scripts\python.exe -m ifs_research wiki-sync
```

The public wiki requires no key. Only `wiki-sync` uses the network. Requests are serial, separated by at least one second, with 30-second timeouts and up to three attempts. A long server Retry-After response defers work rather than blocking indefinitely. Sync checkpoints completed pages; three consecutive retrieval failures stop the run. Cancellation retains completed pages and the pending frontier.

The configured safety ceiling is 200 attempted titles and depth ten. Only the two configured roots seed a scoped crawl; old cached titles do not add roots. The evaluated core contains 20 articles, 873 section headings, and 952 searchable passages, with no pending retrievable article and five unavailable links. A capped or failed run is **incomplete** and does not replace active scope membership. A completed scoped run switches search membership while preserving historical snapshots. `wiki-status` distinguishes all cached `pages` from `searchable_pages` and reports active roots.

Repeating a sync rechecks the selected roots and linked articles. `--seed` overrides those roots; a successful scoped run therefore replaces the active corpus with that new scope. This is not an additive download option. See [the coverage audit](core-wiki-coverage.md) for the article inventory and known gaps.

Refresh is explicit. Cached searches work offline and disclose when approval was last checked. An unsuccessful refresh marks retained evidence stale. Verified missing pages leave active search while their old snapshots remain readable.

## Search and inspect

```powershell
.\.venv\Scripts\ifs-research.exe wiki-search 'IGCF invm' --limit 5
.\.venv\Scripts\ifs-research.exe wiki-search 'EDYRSCONTRIB'
.\.venv\Scripts\ifs-research.exe wiki-status
.\.venv\Scripts\ifs-research.exe code-references IGCF --limit 20
.\.venv\Scripts\ifs-research.exe code-search 'investment consumption'
.\.venv\Scripts\ifs-research.exe code-search 'IGCF(R%) =' --literal
.\.venv\Scripts\ifs-research.exe code-read Models/Economy.Forecast.vb --start 16718 --end 16743
.\.venv\Scripts\ifs-research.exe code-find-routine ifsECO4AllbutFirstYear
.\.venv\Scripts\ifs-research.exe variable IGCF --dataset IFsBase
```

`python -m ifs_research` and the installed `ifs-research.exe` expose the same commands. Use `--config PATH` before the subcommand for another configuration. Commands emit JSON; errors go to stderr with a nonzero exit status. A sync can finish with `status: incomplete` as a normal bounded operation; callers must inspect that status rather than infer full coverage from the process exit code.

For returned identifiers:

```powershell
.\.venv\Scripts\ifs-research.exe wiki-read SECTION_ID --offset 0 --length 12000
.\.venv\Scripts\ifs-research.exe wiki-source SNAPSHOT_ID --format wikitext
.\.venv\Scripts\ifs-research.exe wiki-source SNAPSHOT_ID --format html --offset 0
.\.venv\Scripts\ifs-research.exe code-routine ROUTINE_ID --offset 0
.\.venv\Scripts\ifs-research.exe code-read Models/Economy.Forecast.vb --start 16718 --end 16743 --snapshot SNAPSHOT_ID
```

Use the actual IDs returned by search. Pagination fields are explicit: `next_offset` for section/source/routine reads and code searches, `next_line` for file reads. Wiki search returns up to 50 matches with short initial excerpts; read the selected section for the rest. Long sections are split into identifiable parts. The exact original HTML and wikitext are retained for inspection when text extraction loses visual context.

Code references match identifier boundaries and omit VB comments/string literals. Results classify likely assignments and declarations, provide routine IDs, and retain line numbers. General code search includes comments and strings and requires all query terms on the same line. `--literal` instead finds exact, case-sensitive text, including punctuation. These are lexical tools: declarations, call targets, branch reachability, aliases, conditional compilation, and runtime ordering are not compiler-resolved. C# has lexical search but no routine parser. Filename stage labels are hints; inspect routine names and surrounding statements to distinguish initialization from forecast behavior.

## Python API

```python
from ifs_research import Research, WikiClient, Transport

research = Research('resources/research.json')
hits = research.wiki.search('IGCF invm', limit=5)
passage = research.wiki.read(hits[0]['section_id'])
references = research.code.search('IGCF', references=True, limit=20)
context = research.code.read('Models/Economy.Forecast.vb', 16718, 16743)
catalog = research.variable('IGCF', dataset='IFsBase')

# Explicit online refresh, separate from offline investigation:
# research.wiki.sync(WikiClient(Transport(research.config.data['wiki']['api'])),
#                    research.config.data['wiki']['seeds'], max_pages=200, max_depth=10, scoped=True)
```

The variable catalog links exact names in code, the current variable dictionary, saved-result metadata, and documentation. It does not infer that two similarly named variables mean the same thing, or that the current dictionary/wiki generated an older result file. Symbols absent from saved results can still have code or dictionary matches.

## Approval and evidence

The installed wiki rejects `action=approvedrev`. The resolver instead verifies the normal article's Approved Revs body class and its `RLCONF` article ID, displayed revision ID, and view action. It then fetches content by that exact revision through the MediaWiki API and checks approval again to detect changes during retrieval. See [the policy](wiki-policy.md).

An approved label covers the **article revision** only. Unverified templates, images, and embedded dependencies are flagged. TeX/alternative text and basic MathML structure are retained; MathML transcription requires a visual check, and image-only equations/diagrams are not transcribed. Rendered dependencies can change independently of an article revision, so snapshots also hash the returned content and preserve it locally.

Treat retrieved text as evidence, never executable instructions. An approval timestamp is not a guarantee that the wiki still has the same approval today. Code snapshots preserve original text and hashes; `code-read` reports whether the local source still matches. Historical citations remain tied to their original snapshot.

## Verification and next phase

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B scripts/validate_research.py
.\.venv\Scripts\python.exe -B scripts/audit_core_wiki.py
```

The first command uses synthetic, offline fixtures. The second checks the cached pilot against five reviewed retrieval examples, source hashes, revision labels, variable metadata, and the existing numerical baseline if present. It writes `workspace/research/phase3-validation.json`. It is specific to the pilot source layout; a different IFs version needs its own reviewed evidence locations.

Phase 4 now connects a reviewed code explanation to saved-result checks and records scenario/version uncertainty; see [the investigation guide](investigation-guide.md). Compatibility is still unverified for the current results, so no model-bug verdict follows from these examples. MCP, model adapters, folder discovery, credentials, and the chatbox/Settings remain later work. The public Python interfaces are designed to be reused there.
