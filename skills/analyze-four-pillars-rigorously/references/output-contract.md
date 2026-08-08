# Output contract

## Required order

1. Nature and validation status
2. Input and time normalization
3. Ruleset and conventions
4. Stable chart facts
5. Conditional candidates
6. Dayun, if authorized
7. Traditional interpretation, if requested
8. Sensitivity and unknowns
9. Low-risk reflection and disclaimer

## Header

Always state:

- “Traditional-cultural analysis; not a scientifically validated life prediction.”
- `validation_status`
- `scientific_prediction_status`
- ruleset, Node response schema/core SHA-256, frozen calendar-data schema/SHA-256, event-time basis (`unix_ms_ut1_proxy`), tzdb version, and local time basis

## Calculation table

| Item | Value | Evidence |
| --- | --- | --- |
| Recorded local time | exact input or interval | user input |
| IANA timezone / fold | zone, offset, fold | L1A TIME |
| UTC instant | one or multiple | L1A TIME |
| Solar correction | longitude, EoT, total | L1A TIME plus U for unbounded approximation |
| Four pillars | stable or named candidate plus frozen-data identity | L1B CALENDAR |
| Lunar date | nominal value, or explicit indeterminate boundary state | L1B CALENDAR plus U when unresolved |
| Hidden stems / Ten Gods / Nayin / Dayun | provider-specific mapping | L1C TRAD-MAP |
| Nearest boundaries | distance in the documented UT1-as-UTC proxy frame, model/source guard, and interval crossing | L1A/L1B plus U when uncertified |

## Candidate display

When results differ, use one row per candidate:

| Candidate | Source case | Calendar-model state | Scenario | Year | Month | Day | Hour | Dayun start |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

List stable pillars from `valid_input_result_ids` above the table. Put `sensitivity_only_result_ids` in a separate table headed “uncertified sensitivity bracket”; those rows are counterfactual perturbations, not valid-input candidates or a probability interval. Do not choose a winner without new evidence. `symbolic_start_utc_under_provider` is a traditional provider result, not an observed astronomical event. If the birth time is uncertain, show `BLOCKED_UNCERTAIN_BIRTH_TIME` instead of sampled Dayun start instants.

For `xuanshu-four-pillars-core-response-v0.2`, one guarded Jie expands a normalized source case into `birth_before_term` and `birth_after_term` `calendar_model_variant` rows. Display `source_case_id`, variant state, `solar_term_boundary_uncertainty`, affected year/month pillars, event `model_guard_seconds`, `delta_t_source_code`, and time scale. These are valid candidates and contribute to `valid_input_result_ids`; compute stable/variable pillars across them. More than one guarded Jie without an exhaustive encoding fails closed with `CALENDAR_BOUNDARY_UNRESOLVED`.

`sensitivity_only_result_ids` remains reserved for input-side or apparent-solar counterfactuals. Do not put guarded-Jie variants there.

For a Gregorian chart, `lunar_date_beijing_frame` can contain a nominal value whose `boundary_uncertainty.unresolved_result_change_without_enumerated_variant` is true. Report the lunar label as indeterminate and omit any conclusion that requires it as a unique premise; do not imply that the engine enumerated a complete alternate lunar-month sequence. This lunar condition does not by itself erase otherwise stable four pillars. For Chinese-lunar input, show the stable fail-closed code when reverse conversion is blocked by `LUNAR_BOUNDARY_MODEL_GUARD` or `HISTORICAL_CALENDAR_AUTHORITY_DIVERGENCE`. A `REVIEW_ONLY` condition remains a visible, non-blocking review fact.

If a frozen new moon or solar term is close enough to a Beijing calendar-date or pillar boundary that the documented source/model guard can cross it, display the review condition and all engine-returned consequences. Keep these separate in the table: (1) the caller's `boundary_guard_seconds`, (2) the event's dataset `model_guard_seconds` and `delta_t_source_code`, and (3) any HKO authority divergence. A term object's field named `utc` is the formatted `TT_MINUS_FROZEN_DELTAT_AS_UT1_PROXY` value; do not relabel it as an independently certified exact UTC event time. Do not hide a known HKO-oracle disagreement, substitute an HKO table row for the frozen model, or describe any guard as a confidence probability. The post-2033.75 context scenario is not an official prediction. A modern event within 600 seconds of midnight may require review but does not inherit the pre-1973 600-second model guard or automatically fail.

## Traditional conclusion table

| Traditional conclusion | Premises | Rule ID | Source/location | Applies to | Conflict |
| --- | --- | --- | --- | --- | --- |

Every material L2 statement needs a row and a matching entry in `rule-registry.json`. Avoid isolated prose conclusions, runtime-invented rule IDs, or citations that are only a book title.

## Dual-language mode

- Expert version: name structures, gates, methods, source conflicts, and boundary conventions.
- Plain version: translate the same L1/L2 content into direct language.
- Do not remove limitations or make the plain version more certain.
- Do not add different facts to one version.

## Completion gate

Before sending, confirm:

- No missing input was invented.
- No candidate was silently removed.
- No L2 statement is presented as L1.
- No fake quotation or source location appears.
- The frozen calendar-data identity was reported, and any data-integrity failure stopped the report.
- Every returned boundary/source-model review condition remains visible.
- A lunar label marked unresolved was not used as a unique L2 premise.
- No high-stakes, frightening, fatalistic, or dependency-forming claim appears.
- The user can see what would change the answer.
