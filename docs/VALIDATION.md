# Validation status

## Current verdict

```yaml
release: 0.1.1
plugin_distribution: 0.1.1
calculation_status: DEVELOPMENT_VALIDATED_NOT_INDEPENDENTLY_CERTIFIED
traditional_prediction_status: NOT_EMPIRICALLY_VALIDATED
agent_behavior_e2e: NOT_RUN
skill_forward_behavior_smoke: PASS_1_POSITIVE_1_NEGATIVE_NON_HOST
plugin_manifest_contract: LOCAL_VALIDATED
repo_marketplace_contract: LOCAL_VALIDATED
plugin_host_install_e2e: NOT_RUN
public_directory_package_preflight: LOCAL_PASS
candidate_archive: xuanshu-four-pillars-plugin-0.1.1.zip
candidate_archive_sha256: af0121796c00ec57e79af56a2bf084c2131a956e00452fb24c725ad0a5af7763
candidate_archive_compressed_bytes: 577357
candidate_archive_extracted_bytes: 1077122
candidate_archive_entries: 649
public_directory_submission: NOT_SUBMITTED
public_gregorian_input_range: 1901-01-01/2033-12-31
public_chinese_lunar_label_year_envelope: 1900-2033_PARTIAL_EDGES
first_accepted_nominal_lunar_label: 1900-11-11_NON_LEAP
last_accepted_nominal_lunar_label: 2033-LEAP_11-10
calendar_data_schema: xuanshu-calendar-data-v0.2
node_response_schema: xuanshu-four-pillars-core-response-v0.2
node_core_sha256: 8b3cb09cd9468ab9bfb6c199c58fd053f1e025fca2ac059fe7ee846755773655
calendar_data_sha256: 65189952013b9471e6a0e8a63109ce6305d6242588ec6e3fabdb8ddd0bdd4509
generator_sha256: 6f30b0579347cedfade4077e407dfaabd94f9819125c61d89bd2c014fc735405
build_requirements_sha256: 6cfa326d743d96c47739eedd1acafb642ce0abdb4dc91d256d05755e8908f4d8
offline_regression_suite: SEE_CURRENT_CI_RUN
repository_release_suite: SEE_CURRENT_CI_RUN
final_hko_rerun: PASS_WITH_DISCLOSED_DIVERGENCES
independent_ephemeris_differential: NOT_RUN
public_100x_claim: PROHIBITED
```

Test counts are intentionally not frozen into prose. The current CI run is authoritative for the exact number of collected and passing gates.

The non-host forward smoke ran a fresh-agent direct Zi-hour comparison and a fresh-agent high-risk forced-binary request. The first produced the two auditable chart candidates; the second refused the forced format and offered a real-world checklist after the safety instruction was strengthened. This checks Skill behavior in the current work environment, but it is not the installed desktop-host evaluation.

## Covered release behavior

- Known four-pillar and Gregorian/lunar fixtures, cross-zone lunar round trip, explicit lunar fold, and strict leap-month type.
- Exact public edge labels: 1900 month 11 day 11 (non-leap) maps to 1901-01-01, and leap month 11 day 10 of 2033 maps to 2033-12-31. The adjacent outside labels fail closed.
- Parallel 23:00 rollover schools.
- DST repeated and nonexistent local time, including a historical short fold.
- Timezone path containment; bundled tzdata 2026.3 / IANA 2026c; exact 625-file match to the pinned upstream wheel; pinned bundle manifest; and selected TZif hash.
- Timezone-invariant year/month and same-instant/same-longitude apparent-solar result.
- Exact 4-minute mean-solar shift per longitude degree.
- Consecutive day-pillar progression and 60-day recurrence.
- Strict rejection of unknown rules, conflicting fields, invalid folds, duplicate JSON keys, and unsafe type/size limits.
- Interval-grid rounding, boundary-crossing review, and uncertain-time Dayun blocking.
- Node and data byte-level attestation, v0.2 schema/coverage sentinels, source-code validation, and core hash inclusion in ruleset identity.
- One guarded Jie expands into two before/after calendar-model variants; guarded events retain their model guard, Delta T source, time scale, and affected-pillar metadata.
- Applicable lunar event guards and historical-authority divergences fail closed on reverse conversion; review-only lunar events remain convertible with visible metadata.
- User boundary sensitivity, dataset event-model guards, and HKO authority divergence remain separate.
- Fixed and unique experimental traditional-rule registry plus runtime-bound registry/provider/provenance/data identities.
- Repeat-run canonical equality.
- Repository examples, release metadata, local links, generated-artifact exclusion, source hashes, and full-SHA CI Action references.
- Skills-only Plugin manifest and repo Marketplace identity, source, policy, version, path containment, and safety-copy consistency.

## Frozen v0.2 data checks

The frozen artifact contains 3,244 solar-term rows, 1,657 lunar-month rows, and 77 lunar uncertainty-event rows including endpoint context. Its positional encoding is:

- term rows: `[unix_ms_ut1_proxy, term_index, model_guard_seconds, delta_t_source_code]`;
- lunar-month rows: ten fields, with source code at `row[8]` and uncertainty flags at `row[9]`;
- lunar uncertainty events: nine fields, with source code at `row[6]`.

All four Delta T source codes occur in the frozen data. Segment-boundary continuity diagnostics pass their asserted maximum jumps. The post-USNO segment is explicitly `CONTINUOUS_LINEAR_SCENARIO`, not a prediction.

The generator's combined-guard gate evaluates the Cartesian product of a guarded new moon's and major term's alternative Beijing dates. It aborts if any combination can change principal-term month membership, because that would require explicit alternate month sequences. The frozen artifact passes: the month/leap sequence stays unique under the combined guards, while date-level uncertainty remains encoded.

## HKO oracle result

The final local rerun compared every Gregorian day from 1901-01-01 through 2033-12-31 (48,578 rows) and 24 solar terms per year (3,192 rows). Status: `PASS_WITH_DISCLOSED_DIVERGENCES`.

There are exactly 90 lunar daily-row divergences in three contiguous 30-day runs:

- 1914-11-17 through 1914-12-16;
- 1916-02-03 through 1916-03-03;
- 1920-11-10 through 1920-12-09.

There are exactly six solar terms assigned to a different Beijing calendar date:

- 1912 小雪;
- 1913 秋分;
- 1917 大雪;
- 1927 白露;
- 1928 夏至;
- 1979 大寒.

No additional differences were found. These are disclosed authority/convention differences between a retrospective astronomical model and a publication-table oracle, not proof that either source is universally correct. The frozen artifact stores nine non-expressive comparison facts—three month-start facts and six solar-term facts—but no HKO table, row text, or complete dataset. Every regeneration must repeat the local oracle comparison.

## Three separate uncertainty layers

| Layer | Meaning | Required interpretation |
| --- | --- | --- |
| User `boundary_guard_seconds` | Input/chart-boundary sensitivity requested by the caller | Counterfactual review band; not a data error estimate |
| Dataset event `model_guard_seconds` | Delta T/time-scale model guard stored with a source code on every event | `NASA_PRE1973`: 600 s; `USNO_MEASURED`: 2 s; `USNO_PREDICTED`: published error rounded up + 2 s; `CONTINUOUS_LINEAR_SCENARIO`: 10 s |
| HKO authority divergence | Publication-table date/convention differs from the frozen retrospective model | Disclose and adjudicate; do not substitute HKO rows into generated calendar mapping |

None is a probability distribution or confidence interval, and the context scenario is not an official prediction. A modern event within 600 seconds of Beijing midnight may be reviewed for date sensitivity, but the historical 600-second model guard is not assigned to all modern events and review does not imply automatic failure.

For a guarded Jie, Node enumerates before/after calendar-model variants and they belong to the valid candidate set used to compute stable/variable year and month pillars. More than one simultaneously guarded Jie fails closed with `CALENDAR_BOUNDARY_UNRESOLVED`.

Lunar boundary semantics are deliberately narrower. Gregorian input returns a nominal fixed-UTC+8 lunar value with `boundary_uncertainty`; `unresolved_result_change_without_enumerated_variant=true` means the lunar label is indeterminate and cannot be used as a unique premise. Chinese-lunar reverse conversion fails closed when the requested label is affected by a model-guard crossing or explicit historical authority divergence. A `REVIEW_ONLY` event does not block conversion.

## Why this is not independent certification

JPL DE440s and Skyfield are the generation path for the frozen event table. The release stores `unix_ms_ut1_proxy` (TT minus the frozen Delta T model encoded as Unix milliseconds), not TT JD or unqualified exact historical UTC. Comparing the generated table back to the same path verifies reproducibility, not independence. HKO supplies an independent date-level publication oracle but no UTC/UT1 event-time error bound, and historical table conventions can legitimately differ near midnight.

## Blocking gates for an independently certified release

1. Compare every frozen new moon and solar-term instant against a pinned high-precision implementation independent of the Skyfield/JPL generation path, and publish maximum UTC/UT1 error by Delta T segment.
2. Add -1 second / computed boundary / +1 second cases for every Lichun, Jie, 23:00, 00:00, modeled lunar-date boundary, and timezone transition.
3. Independently reproduce the bundled timezone tree from the pinned upstream source and compare every TZif semantic transition, beyond the current exact published-wheel byte match.
4. Replace approximate apparent-solar EoT with an apparent-Sun hour-angle implementation and independent transit fixtures.
5. Add at least 100,000 property cases for date-cycle, interval monotonicity, round-trip, and Dayun adjacency invariants.
6. Hold out at least 20% of FourPillarsBench cases from development.
7. Run an end-to-end model-adherence evaluation for registry-only interpretation, uncertainty wording, and high-stakes refusal behavior.

Passing computation gates would certify calendrical behavior only. It would not establish that traditional interpretations predict real lives.
