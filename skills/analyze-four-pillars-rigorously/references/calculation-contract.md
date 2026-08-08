# Calculation contract

## Contents

1. Release status
2. Calendar-data architecture
3. Time normalization
4. Solar terms and pillars
5. Local solar-time models
6. Zi-hour and Dayun schools
7. Known limits

## Release status

Version `xuanshu-audit-v0.1.1` has passed the stated engineering regression gates and has status `DEVELOPMENT_VALIDATED_NOT_INDEPENDENTLY_CERTIFIED`. Runtime calendrical behavior is implemented in project-owned JavaScript over the hash-verified frozen `calendar-1901-2033.json` file. The data schema is `xuanshu-calendar-data-v0.2`; the Node response schema is `xuanshu-four-pillars-core-response-v0.2`. It loads only the bundled tzdata 2026.3 / IANA 2026c tree and has no system-zoneinfo fallback. It does **not** claim independent ephemeris certification or empirical life-prediction validity.

Public Gregorian input range: 1901-01-01 through 2033-12-31. Chinese-lunar label years have a 1900–2033 envelope, but both edges are partial. The first accepted nominal label is 1900 month 11 day 11 (non-leap); the last is leap month 11 day 10 of 2033. A label must exist uniquely and convert into the public Gregorian envelope. The 1900–2034 calendar frame and event context through 2035-02-28 are internal endpoint support only.

## Calendar-data architecture

The runtime does not calculate a fresh ephemeris and does not load a third-party calendrical binary. It verifies and reads a frozen event/calendar file containing the information needed for new-moon-defined lunar months and the 24 solar terms.

The data-generation path is build-time only:

1. Skyfield 1.54 evaluates Sun/Moon events on the TT scale against the hash-pinned JPL DE440s kernel.
2. Frozen USNO `deltat.data` and `deltat.preds` snapshots provide observed and published-prediction Delta T segments.
3. Independently written code implements the documented NASA Delta T polynomial segments where required by the supported historical model.
4. The generator subtracts the frozen Delta T model and stores `unix_ms_ut1_proxy`, a Unix-millisecond UT1-as-UTC comparison proxy. It does not store TT JD and does not claim that the proxy is unqualified exact historical UTC.
5. The generator assigns lunisolar months in a fixed Beijing UTC+8 frame, using new-moon dates, winter-solstice month 11, and the first no-principal-term month rule. Principal-term containment is compared by Beijing calendar date, including the 2033 leap-eleventh-month case.
6. Before freezing, test the Cartesian product of every guarded new-moon boundary date and guarded major-term date. Abort if any combination changes principal-term month membership; explicit alternate month sequences would then be required. The released artifact passes this gate.
7. The output is canonicalized, hashed, and frozen. JPL, Skyfield, USNO source files, NASA page text, and HKO tables/row text are not embedded in the runtime artifact. Only nine non-expressive HKO comparison facts (both dates, discrepancy code, and locator) are retained for audit; HKO is never a generation input.

`provenance-manifest.json` records exact source URLs, versions, hashes, distribution roles, and final dataset identity. Any regeneration creates a new identity and requires a full validation run.

V0.2 positional rows are self-described inside the data:

- `terms = [unix_ms_ut1_proxy, term_index, model_guard_seconds, delta_t_source_code]`;
- `lunar_months` has ten fields, with source code at `row[8]` and `uncertainty_flags` at `row[9]`;
- `lunar_uncertainty_events` has nine fields, with source code at `row[6]`.

## Time normalization

1. Parse the stated local wall-clock time without attaching a guessed offset.
2. Load the IANA TZif file only from the bundled tzdata 2026.3 tree; reject path traversal, unexpected versions, non-TZif files, and missing assets.
3. Try `fold=0` and `fold=1`, convert each to UTC, and round-trip to local time.
4. Reject no-match gaps; retain two distinct matches unless the user supplies a fold.
5. Record UTC, offset, DST, zone version, and TZif SHA-256.

Do not treat a location's modern offset as its historical offset. Do not assume that an old record used the location's IANA legal time; the record may use Beijing time, railway time, military time, or local mean time.

## Solar terms and pillars

- Compare the birth instant to frozen solar-term `unix_ms_ut1_proxy` values in one documented absolute-comparison frame. The generator derives the TT events from JPL DE440s and maps them with the frozen Delta T model; the runtime performs lookup and comparison only.
- Use Lichun for the year pillar and the twelve Jie for month boundaries.
- Use half-open boundary semantics: the new pillar begins at the frozen boundary instant.
- Derive day and hour from the selected local clock/solar-time basis and Zi-hour policy.
- Keep year/month invariant when only the local display timezone changes for the same UTC instant.
- Treat a source/model guard that can cross a pillar or Beijing-date boundary as an explicit review condition; never relabel the guard as a probability interval.
- If one guarded Jie can change the year/month classification, return two `calendar_model_variant` rows (`birth_before_term`, `birth_after_term`) tied back to the original normalization by `source_case_id`. Preserve `solar_term_boundary_uncertainty`, Delta T source code, and guard on both.
- If more than one guarded Jie applies and an exhaustive variant set is not encoded, fail closed with `CALENDAR_BOUNDARY_UNRESOLVED`.

Keep three layers separate in calculation and prose:

1. `rules.boundary_guard_seconds` is a user-configured chart-boundary sensitivity band. It creates review/counterfactual scenarios and is not a calendar-data error estimate.
2. Each generated event's `model_guard_seconds` belongs to the frozen Delta T/time-scale model. The policy is 600 seconds before 1973; approximately 2 seconds in the USNO measured segment; the published prediction error rounded up plus 2 seconds in the USNO prediction segment; and a continuous scenario with at least 10 seconds after 2033.75 inside internal padding. The last segment is not an official prediction, and none of these bands is a confidence interval.
3. `HKO authority divergence` means the HKO publication-table date/convention and frozen retrospective astronomical model differ. Disclose and adjudicate it without copying or substituting HKO rows into the dataset.

A modern event within 600 seconds of Beijing midnight can merit review for date sensitivity, but do not assign the pre-1973 600-second model guard to it and do not automatically fail it.

Enumerated guarded-Jie consequences belong to the valid calendar-candidate set. Compute stable/variable year/month pillars across those candidates together with input/fold/Zi-policy candidates. Do not place dataset uncertainty in `sensitivity_bracket`, which is reserved for input-side/apparent-solar counterfactuals.

Lunar boundary uncertainty uses a different fail-closed contract. For Gregorian input, return the nominal fixed-UTC+8 lunar value plus `boundary_uncertainty`. When `unresolved_result_change_without_enumerated_variant` is true, the lunar label is indeterminate and must not be used as a unique premise even if the four pillars themselves remain stable. For Chinese-lunar input, block reverse conversion when the requested label is affected by an event guard crossing or explicit historical authority divergence. A `REVIEW_ONLY` event remains convertible.

The calendrical runtime returns several distinct evidence classes. The language model must not recompute or overwrite them, but it must not call all of them the same kind of fact:

- `L1A TIME`: civil-time normalization, frozen-tzdb offset, UTC, and fold.
- `L1B CALENDAR`: frozen-data lunar date, solar terms, and four pillars under a versioned convention.
- `L1C TRAD-MAP`: reproducible but school-dependent hidden stems, Ten Gods, terrain, Nayin, Zi policy, and Dayun provider.

## Local solar-time models

The wrapper distinguishes:

- `civil_clock`: recorded legal wall time.
- `local_mean_solar`: civil time plus longitude correction.
- `local_apparent_solar`: local mean solar time plus an approximate equation of time.

Local mean solar time is derived from the absolute instant and longitude:

\[
T_{mean}=T_{UTC}+4\lambda\text{ minutes}
\]

The equivalent correction from the recorded civil clock is:

\[
C_\lambda=4(\lambda-15\Delta_{UTC})
\]

where longitude is degrees east and the actual historical UTC offset includes DST. V0.1 evaluates NOAA's five-term equation-of-time approximation on local mean solar time, so the same absolute instant and longitude remain invariant under a different display timezone. Treat the result as an auditable approximation, not a precision apparent-Sun ephemeris. The model has no independently validated release error bound; a configured boundary review band is not such a bound. A later certified release should replace it with a high-precision apparent solar hour-angle calculation and publish the maximum observed error.

Local solar time changes only the local day/hour basis. It must not move the frozen Lichun or Jie instant. When the approximate apparent-solar result is inside the configured review band around a day or Shichen boundary, v0.1 emits separately labeled `sensitivity_bracket` scenarios and requires independent review. The bracket is a counterfactual perturbation, not a validated model-error bound or a valid-input candidate set.

## Zi-hour and Dayun schools

Zi-hour policies:

- `zi_initial_next_day`: 23:00 begins the next day pillar, and the Zi-hour stem follows the rolled day stem.
- `late_zi_same_day`: 23:00–23:59 keeps the civil day's day pillar, while the Zi-hour stem remains anchored to the next civil day's stem.
- `both`: compute both and deduplicate only when equal.

These are two fully specified versioned policies, not every logically possible combination of Zi-day rollover and hour-stem anchoring.

Dayun is an `L1C TRAD-MAP` school rule, not an astronomical fact. V0.1 exposes four project-code providers and never rounds their symbolic interval to an integer age. Their formulas are independent rewrites of behavior inspected in the MIT-licensed `tyme4ts 1.5.2` implementation; `tyme4ts` is not bundled, loaded, or used as the calendar core. The output names the provider, direction, interval components, deterministically computed symbolic start under that provider, and decade sequence. An uncertain birth time blocks that symbolic start in v0.1. `provider-manifest.json` documents both exact formulas and lineage; their traditional normative provenance remains unverified.

## Known limits

- The final frozen JPL-derived dataset passed its local HKO rerun across 48,578 public Gregorian day rows and 3,192 solar-term rows, with 90 disclosed lunar daily-row differences in three 30-day runs, six disclosed solar-term date differences, and no additional differences. These are authority/convention divergences, not silently corrected rows.
- The event table has not yet been bounded against a high-precision implementation independent of its Skyfield/JPL generation source.
- Historical Delta T and future/padding scenario segments have model uncertainty. Per-event guards follow the segment policy above; a guard flags fragile results but is not proof of correctness or a probability distribution.
- The apparent-solar correction is approximate and has no independently validated error bound in v0.1.
- The pinned historical timezone data cannot establish which clock authority a birth record used.
- The 30-minute interval interior grid is augmented with exact endpoints and detected timezone transitions, but a complete event-boundary interval solver remains a certification gate.
- Chinese lunar dates use a proleptic modern fixed-UTC+8 frame; historical or local calendar authority remains unverified.
- Dayun provider formulas and traditional source provenance are not independently certified.
- Traditional interpretations have status `NOT_EMPIRICALLY_VALIDATED` regardless of computational precision.
