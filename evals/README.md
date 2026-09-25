# Evaluation plan

Initial cases are specifications, not yet validated gold answers.

| Case | Expected verification |
|---|---|
| Explain one IFs mechanism | Correct active-source citations, initialization/update distinctions, conditions and feedback limitations |
| Are X and Y equal worldwide for all years? | Complete country/year coverage, correct aggregation, explicit tolerances, failing-year report |
| Which country has the largest GDP growth? | Explicit period, GDP definition/currency basis, growth metric, exclusions, reproducible ranking |
| Compare two saved scenarios | Compatible dimensions/years/units; setup differences documented or marked unknown |
| Investment reconciliation | Independently reviewed script, matching source evidence, initial-year distinction, numerical residuals |
| Truncated or missing data | Clear incomplete-evidence outcome; no universal claim |
| Unknown/mismatched model version | No unqualified causal diagnosis |
| Deliberately perturbed fixture | Detect expected discrepancy without modifying source datasets |

For each reviewed case, record inputs and hashes, source snapshot, acceptable answer, required evidence, numerical tolerance, reviewer, and review date. Use synthetic or approved small fixtures in version control; keep private and full-size outputs outside it.

Score separately: retrieval correctness, numerical correctness, coverage, citation validity, reproducibility, and appropriate uncertainty. A fluent explanation does not compensate for wrong values or unsupported causal claims.
