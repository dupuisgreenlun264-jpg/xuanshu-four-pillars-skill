# Changelog

## 0.1.1 — 2026-08-08

- Added public-directory listing metadata, public privacy and terms pages, square Plugin brand assets, and light/dark brand colors.
- Added deterministic skills-only ZIP construction and structural submission preflight.
- Bundled tzdata 2026.3 / IANA 2026c plus its Apache 2.0 notices so the Plugin host does not need to install a Python package at runtime; pinned the upstream wheel and verified all 625 copied files byte-for-byte.
- Added a Windows desktop acceptance protocol plus exactly five positive and three negative reviewer cases.
- Made temporary birth-input deletion an explicit Skill requirement, bumped the Python orchestrator/ruleset to v0.1.1, and kept the Node calendrical core at v0.1.0.
- Preserved `DEVELOPMENT_VALIDATED_NOT_INDEPENDENTLY_CERTIFIED` and `NOT_EMPIRICALLY_VALIDATED`; desktop host installation remains a separate evidence gate.

## 0.1.0 — 2026-08-08

- Added an installable skills-only ChatGPT/Codex Plugin manifest and a Git-backed repository Marketplace entry, with matching release gates and desktop installation instructions.
- Added a deterministic, offline chart engine implemented in project-owned JavaScript around a hash-verified frozen `calendar-1901-2033.json` data file.
- Added a reproducible build-time data path based on Skyfield 1.54, JPL DE440s, frozen USNO Delta T records/predictions, and independently implemented NASA Delta T polynomial segments. Build inputs are recorded by source and SHA-256; the ephemeris kernel and build dependencies are not runtime artifacts.
- Froze `xuanshu-calendar-data-v0.2`, including per-event Delta T source codes, lunar row flags at `row[9]`, uncertainty-event source codes at `row[6]`, segment continuity diagnostics, and a combined new-moon/major-term guard gate.
- Set the public Gregorian input range to 1901-01-01 through 2033-12-31. Defined the partial Chinese-lunar edge labels as 1900 month 11 day 11 (non-leap) through leap month 11 day 10 of 2033, with wider calendar/event context used only at the endpoints.
- Removed the bundled `tyme4ts` calendrical binary. Reimplemented the four Dayun child-limit formulas in project code while retaining the upstream MIT license and explicit formula-lineage attribution.
- Added fail-closed `tzdata==2026.3` / IANA `2026c` loading, path containment, DST gap/fold preservation, and TZif hashing.
- Separated absolute frozen solar-term comparison from civil, mean, and approximate apparent local time.
- Added parallel fully described Zi-hour policies, cross-zone lunar round-trip filtering, timezone-transition interval points, and guarded Dayun providers.
- Added L1A/L1B/L1C/L2/L3 evidence layers, a revision-pinned experimental rule registry, provider/provenance manifests, anti-Barnum controls, and high-stakes safety boundaries.
- Added strict JSON field/type/range validation and deterministic subprocess resource limits.
- Added offline regression tests, repository release gates, and GitHub Actions CI; exact gate counts are reported by the current CI run rather than frozen into this changelog.
- Added `xuanshu-four-pillars-core-response-v0.2` guarded-Jie variants, source-case linkage, solar-term boundary metadata, lunar reverse-conversion failure codes, and nominal-but-indeterminate Gregorian lunar-boundary reporting.
- Completed the final HKO oracle rerun: 48,578 day rows and 3,192 solar-term rows, with 90 disclosed lunar daily-row differences in three runs, six disclosed solar-term date differences, and no additional differences. HKO remains validation-only and no table/row text or complete dataset is redistributed.
- Froze the Node core, calendar data, generator, and build-requirements identities in `NOTICE` and the provenance manifests; added a build-only reproduction guide under `tools/`.
- Marked the release `DEVELOPMENT_VALIDATED_NOT_INDEPENDENTLY_CERTIFIED` and traditional prediction `NOT_EMPIRICALLY_VALIDATED`.
