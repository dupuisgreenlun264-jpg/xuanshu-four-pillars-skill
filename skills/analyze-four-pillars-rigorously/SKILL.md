---
name: analyze-four-pillars-rigorously
description: Create auditable Four Pillars (Sizhu) charts and source-constrained traditional interpretations with a deterministic versioned calendar wrapper, frozen historical timezone dependency, computed solar-term boundaries, approximate local apparent-solar time, explicit Zi-hour policies, uncertainty candidates, and guarded Dayun handling. Use when a user asks to calculate, analyze, verify, compare, or explain 八字、四柱、命盘、大运、流年, Four Pillars, or Sizhu from birth data, including professional/plain-language reports. Treat every traditional reading as cultural reflection in a development release, not scientifically validated prediction. Do not use for I Ching divination, Tarot, Western astrology, or a generic cultural discussion that does not request a Four Pillars chart or Sizhu-specific analysis.
---

# Analyze Four Pillars Rigorously

Produce a reproducible chart first, then a source-labeled traditional reading. Keep calculation facts, school-dependent rules, and real-life advice visibly separate.

## Route the request

Choose the smallest workflow that satisfies the user:

- **Chart only**: normalize time and run the deterministic engine. Do not add life predictions.
- **Verify or compare**: run every engine-supported convention as a separate scenario and show the field that changes. Mark unsupported conventions `U`; never simulate them with a default.
- **Traditional analysis**: calculate first, then follow `references/interpretation-protocol.md`.
- **Dayun**: read `references/provider-manifest.json`, then request the traditional male/female parameter only after explaining that it selects a legacy direction rule and need not describe gender identity. V0.1 returns a deterministically computed symbolic start under the named provider only for a precise birth time; an uncertain time blocks that field.
- **Theory or methodology**: read `references/calculation-contract.md` and distinguish engineering accuracy from empirical predictive validity.

Read only the references needed for the route:

- Always read `references/input-contract.md` before collecting or normalizing birth data.
- Always read `references/output-contract.md` before presenting a result.
- Read `references/calculation-contract.md` and `references/provenance-manifest.json` for boundary cases, verification, apparent-solar time, lunar input, or methodology questions.
- Read `references/interpretation-protocol.md`, `references/rule-registry.json`, and `references/classical-source-map.md` before any traditional interpretation. Use only registered rules.
- Read `references/evaluation-contract.md` before making accuracy, benchmark, validation, or comparison claims.

## Collect the minimum input

Accept complete information in one message. Do not force a questionnaire.

Require:

1. One calendar date: Gregorian, or Chinese lunar with leap-month status.
2. Local birth time, time range, or an explicit statement that time is unknown.
3. IANA timezone such as `Asia/Shanghai`. Resolve a named birthplace to an IANA timezone only when a reliable lookup is available; never infer historical clock standards silently.
4. Longitude in degrees east only when using local mean or apparent solar time.

Ask at most one combined follow-up for missing fields. Do not request name, former name, exact street address, living status, career history, relationship history, or past events. Do not request both Gregorian and lunar dates.

If the time is approximate, preserve it as an interval. If a DST fold has two valid instants, keep both unless the user can identify the occurrence. If a local time never existed, stop and ask for a corrected record.

## Freeze conventions before calculation

Use this default computation contract unless the user selects another:

- `year_boundary`: computed Lichun instant under the pinned calendar core.
- `month_boundary`: computed twelve Jie instants under the pinned calendar core.
- `term_frame`: `absolute_instant`; compare each case's `absolute_utc` directly with the frozen solar term's absolute event instant. Use fixed Beijing UTC+8 only to construct and label the modern Chinese-lunar frame, never to decide a year or month pillar boundary.
- `time_basis`: `civil_clock`; use `local_apparent_solar` only when requested and longitude is known.
- `day_boundary`: `both`; deduplicate when the Zi-hour schools agree and retain parallel candidates when they differ.
- `child_limit_provider`: `default`; label alternatives rather than blending them.
- `boundary_guard_seconds`: 120.

Never silently change a convention to make a chart match a desired answer.

## Run the deterministic engine

Create a temporary JSON input that follows `references/input-contract.md`, then run:

```bash
python3 "$SKILL_DIR/scripts/four_pillars_engine.py" --input /absolute/path/input.json --pretty
```

Resolve `SKILL_DIR` to this skill's directory. Do not calculate pillars from memory. Do not replace the script with mental arithmetic, a generic web calculator, or an unsourced calendar table.

Treat a nonzero exit as a blocked calculation. Report the stable error code and rejected field; do not invent a fallback value. In particular:

- `LUNAR_BOUNDARY_MODEL_GUARD`: the frozen new-moon model guard can cross Beijing midnight and change the requested lunar label.
- `HISTORICAL_CALENDAR_AUTHORITY_DIVERGENCE`: the frozen model and the pinned HKO publication-table oracle disagree on an authority-sensitive lunar boundary.

For either lunar-boundary code, fail closed: do not select a Gregorian date, produce a unique chart, or continue to a unique traditional interpretation. State what evidence is unresolved and what independent authority review is needed.

Use the returned fields as follows:

- `summary.stable_pillars`: facts shared by every valid scenario.
- `summary.variable_pillars`: facts conditional on time, timezone fold, or school.
- `summary.sensitivity_pillars`: outcomes from an uncertified review bracket; disclose them separately and never call them valid input candidates.
- `scenarios`: inputs and conventions that map to each result. Respect `scenario_kind`: `input_candidate` versus `sensitivity_bracket`.
- `results`: unique chart candidates and, only when authorized and time-exact, provider-specific Dayun results.
- `summary.boundary_review`: keep the caller guard, dataset event-model guard, and HKO authority divergence separate; disclose every returned review condition.
- `validation_status`: engineering release status, not a prediction score.

Before presenting a chart, disclose `engine.node_core_sha256` and `engine.calendar_dataset.sha256`, and confirm that the core's self-attested hashes agree. For each relevant solar-term or new-moon boundary, retain its absolute event time, `delta_t_source_code`, and `model_guard_seconds`. Preserve any HKO authority divergence and lunar-boundary uncertainty exactly as returned. These are source conditions, not confidence probabilities, and the caller's `boundary_guard_seconds` cannot override them.

## Interpret without crossing evidence layers

Label every claim with one layer:

- **L1A TIME**: user input, frozen-tzdb resolution, UTC, fold, and numerical time correction.
- **L1B CALENDAR**: lunar date, solar terms, and four pillars under the named versioned algorithm and convention; not astronomical ground truth.
- **L1C TRAD-MAP**: deterministic but school-dependent tables such as hidden stems, Ten Gods, terrain, Nayin, Zi policy, and Dayun provider.
- **L2 INTERPRET**: a registered traditional rule with `rule_id`, premises, source location, and conflicting school if any.
- **L3 REFLECT**: a low-risk reflection or reversible action option.
- **U UNKNOWN**: missing, ambiguous, unsupported, approximate, or not independently certified.

Do not turn raw element counts into a scientific percentage. Do not collapse 调候、扶抑、格局 and 病药 into one unnamed “用神算法.” Compare them in parallel when more than one method is relevant.

Do not invent a `rule_id`. If no applicable entry exists in `references/rule-registry.json`, omit the material interpretation and state that the registry does not yet cover it. Do not quote a classic unless the exact text and location are present in an inspected source. Otherwise paraphrase and cite the title plus chapter/topic. Never invent page numbers, chapter names, quotations, or ancient-author consensus.

If multiple chart candidates remain, interpret stable facts first and place candidate-specific readings in separate subsections. Never average candidates or assign probabilities without evidence.

## Present the result

Follow `assets/report-template.md` and `references/output-contract.md`. Lead with:

1. Nature and validation status.
2. Input, timezone, time basis, correction, and conventions.
3. Stable chart facts and candidate branches.
4. Dayun only when the required legacy parameter and an exact birth time were supplied.
5. Traditional analysis in expert, plain, or both modes requested by the user.
6. Sensitivity, unknowns, and limitations.

Plain and expert versions must share identical L1 facts. Plain language may simplify wording but must not strengthen certainty.

## Protect validation integrity

Do not use the reference project's “predict past events, ask whether they fit, then tune the chart” loop. That is feedback leakage, not validation.

If the user asks to calibrate an unknown birth time, require a preregistered protocol: freeze candidate charts and predictions first, collect independently described events second, separate calibration and sealed holdout events, include random-chart/Barnum controls, and never modify production rules from same-session feedback.

Do not claim “100× more accurate” unless the exact criteria in `references/evaluation-contract.md` have passed. Until then say only that this skill removes specific failure modes through deterministic calculation, explicit conventions, and tests. Never describe traditional life prediction as scientifically validated.

## Safety boundaries

- Frame Four Pillars as traditional culture and reflective practice, not established causal science.
- Do not predict death, disaster, severe illness, criminality, infidelity, fertility, or unavoidable misfortune.
- Do not diagnose health conditions or issue legal, financial, medical, employment, marriage, or reproductive decisions.
- Avoid fear, fatalism, dependency, coercion, and high-frequency checking.
- Prefer reversible actions grounded in the user's real circumstances.
- Do not save birth data unless the user explicitly requests a reusable report; redact identifiers by default.
