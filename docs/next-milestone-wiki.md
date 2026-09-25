# Next milestone: searchable Pardee Wiki documentation

Current wiki scope supersedes the original broad pilot: two documentation roots, 20 reachable articles, 873 headings, and 952 searchable passages. See [the core coverage audit](core-wiki-coverage.md). The historical pilot counts below describe the initial validation.

Status: implemented with a bounded 39-page pilot on 2026-09-24, alongside the Phase 3 code-investigation tools. See [verification](phase3-validation.md) and [usage](research-guide.md). This document retains the acceptance specification; the pilot is not a complete wiki mirror.

## Outcome

Add a local documentation service that retrieves Pardee Wiki pages, prefers approved revisions, falls back to latest revisions when approval cannot be verified, and returns searchable passages with exact citations. Keep it independent of model providers, MCP, and the eventual chat UI.

The user-facing destination remains a chatbox with Settings. This milestone supplies its documentation backend; ordinary users will not need to configure API endpoints or run these development commands.

## 1. Establish revision-aware API access

- Preconfigure https://pardeewiki.du.edu/api.php; no wiki credential is required for the public pages already tested.
- Determine and verify the installed Approved Revs extension's approval lookup using the live site. Do not assume normal MediaWiki latest-revision metadata proves approval.
- Choose the verified approved revision when available. Otherwise resolve the latest revision, recording whether approval is absent or unknown and why fallback occurred.
- Retrieve content by the selected revision ID, not by title alone. Resolve redirects to canonical page identities and retain aliases for search.
- Use a descriptive User-Agent, one request at a time with at least one second between requests, 30-second request timeouts, and at most three attempts for transient failures. Honor Retry-After and stop with an explicit incomplete-sync status when unavailable.

## 2. Import a bounded documentation corpus

- Start from International Futures (IFs), Understand the Model, Introduction to IFs, and Guide to Scenario Analysis in International Futures (IFs). Resolve actual canonical titles through the API.
- For the initial pilot, follow article-content links within the wiki's main namespace to depth three, with a 200-page ceiling. Exclude navigation, talk, user, edit/history, and external-site traversal. Record skipped links and the pending frontier; never call a capped traversal a complete wiki mirror.
- Apply revision selection independently to every page.
- Keep source wikitext and rendered article HTML. Extract headings, paragraphs, lists, tables, and mathematical source/alternative text when available. Record image-only equations and diagrams as unresolved visual material rather than inventing text. Attachment transcription/OCR is deferred.
- Retain template, image, and attachment references with provenance/limitations. The approval label covers the selected article revision; do not extend it to unverified embedded dependencies.

## 3. Store and search locally

- Add a separate documentation configuration and SQLite catalog under this project's local workspace. Do not change the numerical pilot registry or invalidate existing numerical replay inputs.
- Store immutable content snapshots keyed by page and revision, with content hashes. Track the currently selected snapshot, approval state, selection reason, revision/fetch/check timestamps, URL, aliases, and extraction warnings.
- Build a SQLite FTS5 index over title, heading, and section text. Prioritize exact variable-name/title matches and otherwise rank lexical matches. Embeddings and a vector database are deferred.
- Expose transport-neutral Python operations: sync documentation, inspect sync status, search documentation, and read a cited section. Add matching CLI commands for development and verification.
- Search returns bounded passages, headings, revision-specific links, approval/fallback labels, and freshness information. A citation resolves to the exact stored passage and source revision.

## 4. Refresh and offline behavior

- Recheck approval selection on each requested sync, including pages whose latest revision has not changed: approval may have changed independently.
- Refresh selected content and index together in a transaction. Preserve older snapshots referenced by investigations.
- If approval disappears, select latest and label fallback. If approval lookup fails but content retrieval succeeds, label approval unknown. Never silently label a fallback approved.
- If retrieval fails, keep the previous snapshot with its original status and a stale/offline warning. A verified deleted/unavailable page is removed from active search but retained as historical evidence.
- No background schedule in this milestone; refresh is explicit. No write requests to the wiki.

## 5. Verify useful retrieval and policy behavior

Use deterministic HTTP fixtures for regression tests, plus a small read-only live-site smoke check. Do not depend on future live revision IDs remaining fixed.

Required cases:
- Approved and latest revisions differ: selected content and citation use the approved ID.
- Latest is approved: approved label retained.
- No approval or failed approval lookup: latest content with the correct fallback reason.
- Approved parent links to an unapproved child: independent child selection and label.
- Redirects, duplicate links, capped traversal, request throttling, malformed responses, and interrupted updates.
- Tables and text-based math survive extraction; visual-only and unverified embedded content is flagged.
- Offline retrieval retains accurate cached status; approval removal changes selection on refresh.
- Snapshot, indexed passage, and citation revision stay consistent.
- Existing numerical tests and saved-analysis behavior remain intact.

Create five reviewed retrieval examples covering investment, economic production/productivity, education linkages, scenario setup, and a named variable found in the imported corpus. The milestone passes when search finds the relevant sections with inspectable citations; it does not claim to answer causal questions automatically.

## Deliverables and acceptance

- Wiki connector, revision resolver, local snapshot/index store, search/read Python API, and CLI.
- A pilot corpus with a sync report showing imported pages, approved/fallback counts, failed/skipped pages, extraction warnings, and coverage limits.
- Tests and a concise verification report, including live confirmation of the approval-selection mechanism.
- Documentation of how the later chat Settings screen will trigger sync and display status; no chat UI or model credentials implemented here.

## Follow-on milestone

Phase 3 code search is now implemented. Next, complete a version-qualified mechanism/result investigation (Phase 4), then add local IFs-folder discovery and connect the reusable tools to MCP, a model/tool loop, and a thin chatbox with Settings. The numerical core and documentation service should remain callable without an LLM.
