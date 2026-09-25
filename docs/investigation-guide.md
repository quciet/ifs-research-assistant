# Phase 4: code-first investigations

Phase 4 adds a reusable investigation backend. The supplied IFs implementation controls explanations; a user's expectation is recorded as a question, not adopted as a model requirement. Wiki passages provide supporting explanations and preserve approved/fallback labels.

This is a Python/CLI backend. It does not yet autonomously interpret arbitrary natural-language questions. A researcher, or the later model/tool loop, reviews retrieved source and supplies a bounded investigation specification. The runner binds that review to source hashes, performs the saved-result checks, and preserves the evidence. No IFs execution, arbitrary generated Python execution, model API, chatbox, or MCP service is introduced.

## Start from a question

```powershell
.\.venv\Scripts\python.exe -m ifs_research investigation-start --question 'Why is I different from INVS?' --variables I INVS --dataset IFsBase
```

This creates a draft under `workspace/research/investigations`, with all paginated lexical references for the named variables and a small set of documentation search candidates. The draft contains no assumed identity or automatically invented explanation. Follow assignments, routine calls, initialization, dimension mappings, conditions, bounds, saved-state dependencies, and later overwrites using the existing code-read/reference tools. Single-letter identifiers such as I can also be local loop variables; lexical hits are not resolved symbol bindings.

A reviewed specification requires:

- Question and optional user expectation, selected dataset, and the source snapshot actually reviewed.
- Code evidence IDs with snapshot-relative path, line window, full-file SHA-256 and exact returned text SHA-256.
- Explanations that cite those evidence IDs; comments alone do not establish executable behavior.
- Optional immutable wiki section IDs. Their approval does not establish code-version compatibility.
- Explicit preconditions with `established`, `unknown`, or `contradicted` status. Determinate statuses require an evidence statement.
- Numerical checks with explicit stage, expression, purpose and tolerances. Purpose is either `observation` or `implemented_relation`.

Set `review_status` to `reviewed` only after that source review. The label records an explicit review decision; the runner validates the bindings, not the semantic correctness of arbitrary prose. It is not an approval prompt or claim of compiler verification.

## First reviewed example

```powershell
.\.venv\Scripts\python.exe -m ifs_research investigation-run resources/investigations/i-vs-invs-872.json
```

The example is tied to the reviewed local 8.72 source snapshot and cached wiki citations. It is an acceptance case, not a universal rule for every IFs release. Another source snapshot requires a new review, even when variables retain the same names. Another installation also needs its own registered datasets, reviewed aggregation metadata, indexed source, and locally available evidence IDs. Automatic folder discovery and the two-field Settings experience remain later work.

The reviewed code establishes:

1. Initialization sums sectoral INVS into I, then applies a 0.001 floor and assigns IGCF from I. Equality to the sector sum is conditional on that floor being inactive.
2. Origin shares are initialized from INVS/IGCF. Forecast INVS is allocated from IGCF using those shares.
3. The forecast inventory calculation sets I to IGCF plus the sum of `PFD + MS - CS - INVS - GS - XS` across sectors. The active statements do not add that stock-change term into INVS.
4. The dispatcher orders the allocation before the inventory calculation. Exogenous replacement of I and a possible later dyadic recalculation qualify a claim about final saved values.

Thus forecast equality is not required. Equality can still occur when relevant terms cancel; non-equality is not itself an error. The first stored year is labeled separately and is not automatically assumed to be initialization.

The example observes the I–INVS gap, tests the initialization-with-floor relationship, tests conditional forecast inventory accounting, and separately observes allocation differences and inventory residuals. It does not require I–INVS to equal zero in forecast years. Absolute tolerance 0.001 and relative tolerance 1e-6 are explicit pilot choices for floating-point comparisons, not universal IFs correctness criteria. Units are the registered billion-model-currency family; the saved run's dollar base year remains unverified.

## Reusable calculation contract

A check can express weighted sums of registered variables, with an optional floor applied at country level. For example, an unrelated resource balance can compare:

```json
{
  "id": "resource_balance",
  "purpose": "implemented_relation",
  "stage": "all",
  "lhs": {"terms": {"RESOURCES": 1}},
  "rhs": {"terms": {"DOMESTIC": 1, "IMPORTS": 1}},
  "atol": 0.001,
  "rtol": 0.000001,
  "code_evidence": ["resource_assignment"],
  "explanation": "The reviewed assignment adds domestic supply and imports."
}
```

This is a contract example, not a claim that these exact variables exist in IFs. Expressions are data, not executable strings: no `eval`, shell code, or unrestricted Python is accepted. More complex equations require later bounded operators or a separately reviewed calculation implementation; the runner does not approximate them silently.

Checks support `all`, `first_stored_year`, or `subsequent_year`. Optional `period` selects first/last years, and `country_ids` selects a nonempty reviewed country subset. All intervening observations must be complete. Aggregation uses the existing reader's reviewed SUM rules and dimension membership, excludes precomputed country groups, and rejects incompatible units or unknown aggregation. Country-level calculations precede aggregation. A world total cannot hide failed country-level relationships. An empty stage cannot pass vacuously.

## Interpretation is separate from measurement

Each result preserves three distinctions:

- `code_assessment`: explanation reviewed against the supplied implementation.
- `numeric_consistency`: whether applicable reviewed relationships match saved observations within tolerance.
- `outcome`: whether the combined evidence supports attribution to the saved run.

| Outcome | Meaning |
|---|---|
| `supported` | Reviewed relationships match, documented version correspondence is supplied, and applicable conditions are established. |
| `potential_inconsistency` | A reviewed relationship differs under documented matching provenance and established conditions; investigate before declaring a bug. |
| `insufficient_evidence` | Numbers/code can still be explained, but provenance, conditions, stage coverage or numerical data are insufficient for combined attribution. |
| `incompatible_inputs` | Documented provenance does not match the selected inputs, or a required condition is contradicted. |

Observational differences never trigger `potential_inconsistency`. Numerical agreement cannot prove a generating version. Unknown provenance does not block code explanation or numerical analysis. Missing/incomplete numerical evidence produces a report retaining the code explanation and the limitation; it does not manufacture a successful numeric check.

Optional `version_evidence` is an absolute path to a JSON document containing `source_snapshot`, `dataset_sha256`, and a nonempty `basis` explaining their generating relationship. The runner compares those bindings and preserves the document. It labels this **documented** correspondence, not independent verification of the author's statement. Do not create such evidence from a matching equation or a directory/version label. The real pilot has no such generating record and therefore remains unknown.

## Evidence bundle and replay

Every completed run saves:

- `investigation.json`: exact reviewed question, claims, citations, expressions, conditions and tolerances.
- `source-evidence.json`, `source-manifest.json`, `wiki-evidence.json`: snapshot-bound excerpts and provenance.
- `country_values.csv`, `comparisons.csv`: complete country/year values and both country and selected-country-total comparisons, when extraction succeeds.
- `evidence.json`, `report.md`: code explanation, numerical findings, metadata/coverage, scenario relationship and attribution limitations.
- `manifest.json`, `execution.log`, `analysis.py`, and `implementation/`: input fingerprints, status, executable replay wrapper, and archived package source.

Replay using the returned job path:

```powershell
.\.venv\Scripts\python.exe -m ifs_research investigation-replay workspace/research/investigations/JOB-ID
# Equivalent:
.\.venv\Scripts\python.exe workspace/research/investigations/JOB-ID/analysis.py
```

Replay checks input fingerprints, reviewed specification, Python/dependencies, implementation hashes, table bytes and outcome. It refuses changed code or data. Reindexing changed source does not silently reauthorize an old explanation. Historical artifacts remain available even when a fresh review is needed. Wiki refresh does not replace previously cited section snapshots.

## Python interface and verification

```python
from ifs_investigation import draft, run, replay, evaluate

folder = draft('resources/research.json', 'Why is I different from INVS?', ['I', 'INVS'], 'IFsBase')
job = run('resources/research.json', 'resources/investigations/i-vs-invs-872.json')
new_job = replay(job)
# evaluate(reader, reviewed_spec, compatibility='unknown') returns values, comparisons, evidence without writing a job.
```

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B scripts/validate_investigation.py
```

The synthetic tests use an unrelated balance equation, including an intentionally perturbed case whose country errors cancel at the aggregate level. The pilot validator independently recomputes selected raw-observation sums and equations for three countries and three years, checks complete-run tables through replay, and verifies the existing numerical baseline's engine/input fingerprints remain unchanged. It writes `workspace/research/phase4-validation.json`.

The next milestone can expose discovery, evidence reads, review specifications, run status, and artifacts through MCP, then let the model/tool loop conduct the source review and create the investigation record. The chatbox should present the explanation first and allow users to inspect the code, numbers, and limitations.
