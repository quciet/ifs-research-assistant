# Phase 3 verification — wiki and code investigation

Current wiki scope supersedes the original broad pilot: two documentation roots, 20 reachable articles, 873 headings, and 952 searchable passages. See [the core coverage audit](core-wiki-coverage.md). The historical pilot counts below describe the initial validation.

Validated on Windows with Python 3.12.14 on 2026-09-24. The research backend is implemented; combined mechanism/result diagnosis remains Phase 4.

## Executed checks

- 63 offline unit tests passed: 27 existing numerical tests and 36 research tests.
- A public, read-only sync imported 39 articles without failures under a 40-title, depth-three pilot bound. The cache contains 30 verified approved article revisions and nine latest-revision fallbacks with approval absent. Coverage remains incomplete; pending traversal is recorded.
- The final extraction produced 1,134 searchable sections/parts. Both source wikitext and rendered HTML are retained. Approval is checked per page; embedded dependencies and visual transcription limitations are exposed.
- The selected IFs.Core tree contains 53 indexed source files. Three generated/assembly files were excluded. Indexing preserves original bytes' SHA-256 hashes, decoded source text, routine boundaries, and line citations.
- Tests cover older approved revisions, latest already approved, absent/unknown approval, approval removal and races, conflicting markers, redirects, child policy independence, retries/throttling, malformed JSON, caps, cancellation checkpoints, stale/deleted pages, atomic updates, historical citations, MathML/tables/images, identifier boundaries, source changes, and pagination.
- `scripts/validate_research.py` records the five retrieval checks below, code excerpts, source hashes, variable links, and numerical-baseline provenance under `workspace/research/phase3-validation.json`.

## Live revision selection

The site's Approved Revs extension does not provide its documented `action=approvedrev` endpoint. Public article HTML supplies `approvedRevs-approved` or `approvedRevs-noapprovedrev` and the displayed revision in `RLCONF`. The resolver verifies page identity and view action, then uses `action=parse&oldid=...`; it rechecks approval and independently queries the selected revision's timestamp.

Observed during this sync, not assumed fixed for future updates:

| Article | Selected revision | Latest at selection | Selection |
|---|---:|---:|---|
| International Futures (IFs) | 13782 | 13872 | Approved |
| Understand the Model | 8509 | 13544 | Approved |
| Introduction to IFs | 12058 | 14010 | Approved |
| Economics | 10954 | 10954 | Latest fallback; approval absent |

This behavior is consistent with the [Approved Revs documentation](https://www.mediawiki.org/wiki/Extension:Approved_Revs). The specific API limitation and HTML markers were confirmed against Pardee itself. Failed or conflicting approval verification yields an explicitly unknown fallback, not inferred approval.

## Five reviewed retrieval examples

| Case | Query | Reviewed retrieval |
|---|---|---|
| Investment | `IGCF invm` | Economics, section 3.3.5: consumption/investment intervention |
| Production/productivity | `Cobb Douglas` | Economics, section 2.8.1: changing factor contributions/returns |
| Education linkage | `EDYRSCONTRIB` | Health, Forward Linkages / Productivity |
| Scenario setup | `Add Scenario Component` | Scenario guide, Prepackaged Scenarios |
| Named variable | `GDP` | Economics, section 12.3.1: GDP and GDP per capita |

All five were found within the first ten results with inspectable section IDs, selected revisions, approval status, and revision-specific URLs. This is a retrieval evaluation, not a benchmark of automated causal answers. Broad queries can return related sectors; users or a later investigator must inspect the passage. Approved scenario instructions can describe an older interface.

## Reviewed mechanism: investment and consumption

[Economics, revision 10954, section 3.3.5](https://pardeewiki.du.edu/index.php?title=Economics&oldid=10954#3.3.5_Consumption_and_investment:_Exogenous_intervention) describes an investment multiplier transferring resources from consumption to gross capital formation. This page is a **latest fallback**, not approved.

The indexed `Models/Economy.Forecast.vb`, lines 16718–16721, executes the local relationship:

```text
invm = clamp(invm, 0.5, 1.5)
iadj = IGCF * (invm - 1)
IGCF = IGCF + iadj
C = C - iadj
```

This transcription summarizes the code; the archived evidence retains the exact VB statements. If entry IGCF is positive and other entry values are held fixed, increasing an unclamped multiplier increases this adjustment and reduces C at these statements. The clamp limits that local response. Lines 16731–16738 subsequently constrain IGCF using either GDPPOTRPA or GDP according to `gdprext`. Lines 16916–16938 contain additional conditional consumption/investment adjustments. The local transfer is therefore not a promise about final saved values or net scenario effects.

Investment allocation provides another useful check: lines 12744–12785 conditionally compute sector investment demand, apply bounds, sum it into `tids`, and rescale each sector by `IGCF/tids`. In exact arithmetic, that final rescaling sums to IGCF when `tids` is finite and nonzero and all included sectors are summed. This does not establish that saved `INVS`, `I`, and `IGCF` are interchangeable or that a particular output file came from this code.

## Reviewed linkage: education and productivity

[Health, approved revision 9031, Productivity](https://pardeewiki.du.edu/index.php?title=Health&oldid=9031#Productivity) identifies education attainment as one human-capital productivity contribution. The indexed code at lines 7850–7867 computes an education-years contribution from the difference between attainment and a comparison value, multiplied by `mfpedyrs`, and combines it with other components. It includes additional terms beyond that older approved description.

Forecast code at lines 14249–14263 uses `sedyrsag15` rather than the direct attainment array used at line 7850. This exposes a saved-state dependency for further investigation; the lexical search alone does not establish every update's runtime timing. A positive local response requires a positive coefficient and a held-fixed comparison value. Neither the older wiki nor one assignment proves the final GDP response.

## Provenance and limits

The cited source snapshot is `0a6ef81100f8602ca0ac07f021146866f414ced040e1395d7180d12fb93f0a11`. The Economy.Forecast.vb byte hash is `7006d47e28af823e4518e174d3f0a04c3e55823aa4d0aad9ec2ffbc97b285ba8`. The local report preserves snippets and wiki snapshot IDs even if current indexes later change.

The variable catalog connects IGCF to its saved-result metadata (79 years, 188 countries/territories), current dictionary, code occurrences, and documentation. All version-compatibility relationships remain explicitly unverified. The current IFsBase and Working datasets are byte-identical and their generating code version remains unknown.

The validation script checks every indexed source hash and confirms the earlier numerical engine and registered baseline inputs have not changed. Synthetic numerical replay is also part of the passing test suite. This milestone does not execute IFs or claim a supported/failed model-result mechanism case; that is the next phase.
