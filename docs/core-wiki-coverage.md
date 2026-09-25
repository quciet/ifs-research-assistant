# Core wiki coverage audit

Checked against the public wiki on 2026-09-24. The original 39 articles were a broad, capped pilot, not the wiki's total size or the size of the user's chosen documentation scope.

## Active scope

The default configuration now starts only from:

1. [Understand the Model](https://pardeewiki.du.edu/index.php?title=Understand_the_Model), displayed as **Understand IFs** in the site's navigation.
2. [Guide to Scenario Analysis in International Futures (IFs)](https://pardeewiki.du.edu/index.php?title=Guide_to_Scenario_Analysis_in_International_Futures_(IFs)).

It follows main-namespace article links recursively from each selected revision, with approved-first/latest-fallback selection on every article. In-page anchors are sections, not separate articles. Referenced supporting articles remain included; unrelated cached pilot pages no longer become implicit crawl roots or search results.

The focused live refresh exhausted this linked graph without a page/depth cap or retrieval failure:

- **20 articles**, with **873 MediaWiki section headings**.
- **952 searchable passages** after extraction and splitting long sections.
- **19 approved article revisions**; **one latest fallback**, Economics (approval absent).
- **Five unavailable linked titles**, recorded below; no retrievable linked article pending.
- The cache retains 40 articles in total. Twenty earlier pilot articles are outside active search; their historical citations remain readable.

The scope is much smaller than the whole site because most model documentation is consolidated into long module articles. For example, Economics has 290 headings in one article; the scenario guide has 106. Neither is reduced to an introduction-only excerpt: the stored revision includes the complete returned wikitext and rendered article HTML.

## Article inventory

| Article | Section headings | Searchable passages |
|---|---:|---:|
| Understand the Model | 0 | 1 |
| Guide to Scenario Analysis in International Futures (IFs) | 106 | 114 |
| Agriculture | 79 | 89 |
| Economics | 290 | 330 |
| Education | 43 | 45 |
| Energy | 11 | 20 |
| Environment | 12 | 11 |
| Governance | 38 | 41 |
| Health | 85 | 78 |
| Infrastructure | 50 | 49 |
| Interstate Politics (IP) | 21 | 23 |
| Population | 23 | 24 |
| Socio-Political | 39 | 40 |
| Transport | 6 | 6 |
| Understand IFs | 15 | 15 |
| Water model documentation | 27 | 28 |
| Introduction to IFs | 5 | 8 |
| Define, Drivers, Explain, Code and Delete | 0 | 1 |
| Extended Features | 23 | 23 |
| IFs Bibliography | 0 | 6 |
| **Total** | **873** | **952** |

A heading can group child sections without text of its own; long sections can produce multiple passages. These counts therefore measure different things.

## Whole-site check

The live MediaWiki statistics report **237 content articles** and **3,060 total pages**, with **2,450 uploaded files**. A separately paginated inventory returned **596 main-namespace page titles**. The main-namespace inventory includes titles that do not qualify as content articles in MediaWiki's statistics, so these numbers are not interchangeable. No literal `Parent/Child` page titles were found beneath either entry title or any of the 20 included article titles. Here, “subpages” primarily means linked articles and sections within articles.

The page-title inventory and root API responses are saved in `workspace/research/core-wiki-live-audit.json`; they do not add unrelated articles to search.

## Known gaps

The API reports these linked titles unavailable:

- Agriculture: `Section`, `Livestock`, `Transmission/distribution loss to food demand`.
- Economics: `ED-Section(1 Intro)`.
- Education: `The IFs pre-Processor`.

These are broken/unavailable wiki targets, not successfully imported pages. Existing prose and equations within the parent articles remain available. External documents, OCR of diagrams/image equations, and independent approval verification of templates/attachments remain outside this article coverage claim. Approved documentation is not automatically compatible with the current IFs source or saved results.

## Reproduce and inspect

From the project folder:

```powershell
.\.venv\Scripts\python.exe -m ifs_research wiki-sync
.\.venv\Scripts\python.exe -m ifs_research wiki-status
.\.venv\Scripts\python.exe -B scripts/audit_core_wiki.py
.\.venv\Scripts\python.exe -B scripts/validate_research.py
```

The scoped sync has safety ceilings of 200 attempted titles and depth ten, but this run completed at depth three. If a future run reaches a ceiling, fails a download, or cannot resolve a root, it reports incomplete and does not replace the active scope membership. Completed article refreshes remain cached. A complete run switches active search membership together; excluded snapshots are retained.

`wiki-status` distinguishes all cached `pages` from `searchable_pages`, and exposes the active roots, approval counts, and last sync report. `workspace/research/core-wiki-coverage.json` records the exact inventory, parent/depth paths, unavailable links, and excluded cached titles. The audit checks that every linked article is either included or explicitly unavailable. The five existing retrieval examples still pass in this narrower scope, and numerical-baseline provenance remains unchanged.
