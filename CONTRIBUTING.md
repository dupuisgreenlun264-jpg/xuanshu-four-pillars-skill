# Contributing

Contributions are welcome when they improve reproducibility, source traceability, boundary handling, privacy, or safety.

## Before opening a pull request

1. Use synthetic birth inputs only.
2. Add a regression test for every calculation change.
3. State the exact convention and source; do not call a school rule universal.
4. Keep L1A time, L1B calendar, L1C traditional mappings, L2 interpretation, and L3 reflection separate.
5. Do not add unverified numerical strength weights, fabricated quotations, or retrospective “accuracy” anecdotes.
6. Run:

```bash
python skills/analyze-four-pillars-rigorously/scripts/self_test.py
python -m unittest tests/test_repository.py -v
```

Use `python -B` or `PYTHONDONTWRITEBYTECODE=1` during release checks so generated cache files do not enter the tree.

## Source changes

For a classical rule, add it to `rule-registry.json` with title, exact section/topic, pinned revision or edition, premises, exclusions, conflicts, and a stable `rule_id`. Separate base text from modern commentary; a bibliography-only citation is insufficient.

For a calendrical change, document supported dates and partial lunar-label edges, time scale, reference zone, boundary semantics, model-guard policy/source code, independent oracle, and before/after fixtures. Follow [tools/README.md](tools/README.md): verify every build-input hash, generate twice, require byte equality, rerun the complete local HKO comparison, and review the combined new-moon/major-term guard gate.

Do not commit JPL kernels, USNO snapshots, HKO tables/rows, build virtual environments, or local comparison datasets. A regenerated calendar file must receive a new reviewed identity. Update the Node/data/generator/build-requirements hashes in `NOTICE`, provider/provenance manifests, runtime pins, tests, and changelog as one atomic change.

For v0.2 data-shape changes, update the embedded `encoding` map and runtime decoder together. Preserve the term source code at `row[3]`, lunar-month source code at `row[8]`, lunar-month flags at `row[9]`, and lunar uncertainty-event source code at `row[6]`, or introduce a new schema version and migration.

Boundary changes must retain the distinction between user sensitivity, event `model_guard_seconds`, and HKO authority divergence. A guarded Jie must enumerate both model states or fail closed. A lunar label marked `unresolved_result_change_without_enumerated_variant` must never be presented as unique.

## Pull-request gate

A PR must not:

- silently change frozen defaults;
- delete a valid ambiguity candidate;
- weaken a limitation or validation-status label;
- collect new personal data without a calculation need;
- alter L1 facts from the interpretation layer;
- include generated caches, reports, or real user data.
