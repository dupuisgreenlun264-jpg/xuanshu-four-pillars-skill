# Input contract

## Contents

1. Minimal JSON
2. Field rules
3. Ambiguity behavior
4. Examples

## Minimal JSON

```json
{
  "birth": {
    "calendar": "gregorian",
    "date": "1988-02-15",
    "time": "23:30:00",
    "timezone": "Asia/Shanghai",
    "longitude": 121.4737,
    "fold": null,
    "uncertainty_minutes": 0
  },
  "traditional_sex_for_dayun": null,
  "rules": {
    "time_basis": "civil_clock",
    "day_boundary": "both",
    "child_limit_provider": "default",
    "decade_count": 8,
    "boundary_guard_seconds": 120
  }
}
```

## Field rules

| Field | Allowed values | Rule |
| --- | --- | --- |
| `birth.calendar` | `gregorian`, `chinese_lunar` | Supply one calendar only. |
| `birth.date` | `YYYY-MM-DD` | Required for Gregorian input; public range 1901-01-01 through 2033-12-31. |
| `birth.lunar` | year, month, day, leap_month | Required for lunar input; label-year envelope 1900–2033 and `leap_month` must be explicit. Both edge years are partial, and the resolved Gregorian candidate must remain in the public Gregorian range. |
| `birth.time` | `HH:MM[:SS]`, null | A local wall-clock reading without UTC offset. |
| `birth.time_range` | `{start,end}` | Mutually exclusive with `time`; an end earlier than start crosses midnight. |
| `birth.uncertainty_minutes` | 0–1440 | Symmetric interval around `time`. |
| `birth.timezone` | IANA zone | Required; fixed labels such as CST are not accepted. |
| `birth.longitude` | -180–180 | Degrees east; required for solar-time correction. |
| `birth.fold` | 0, 1, null | Select one repeated DST time; null preserves both. |
| `traditional_sex_for_dayun` | `man`, `woman`, null | A legacy rule parameter, requested only for Dayun. |
| `rules.time_basis` | civil, mean solar, apparent solar | Use the exact engine spellings below. |
| `rules.day_boundary` | both, early-next, late-same | Use the exact engine spellings below. |
| `rules.year_boundary` | `computed_lichun_instant` only | Any unsupported alternative fails closed. |
| `rules.month_boundary` | `computed_jie_instant` only | Any unsupported alternative fails closed. |
| `rules.term_frame` | `absolute_instant` only | Any unsupported alternative fails closed. |
| `rules.decade_count` | integer 1–20 | Used only when Dayun is authorized. |
| `rules.boundary_guard_seconds` | integer 1–3600 | Review band, not a certified error bound. |

Exact spellings:

- `civil_clock`
- `local_mean_solar`
- `local_apparent_solar`
- `both`
- `zi_initial_next_day`
- `late_zi_same_day`
- Child-limit providers: `default`, `china95`, `lunar_sect1`, `lunar_sect2`

All fields are type-strict. Numeric strings and booleans used as integers are rejected. Chinese-lunar input requires an explicit JSON boolean `leap_month`. Unknown fields and unsupported convention values fail closed instead of being ignored.

## Ambiguity behavior

- Missing time: partition the full local date with deterministic grid points plus detected timezone-transition points; return chart candidates and disclose that formal continuous event-boundary certification has not been completed.
- Time range or uncertainty: retain unique chart states without probabilities. A 30-minute interior grid is augmented with exact interval endpoints and detected fold/gap boundaries; it is not described as a proof of continuous completeness.
- DST fold: preserve both UTC instants when `fold` is null.
- DST gap: reject the local time.
- Solar or Zi boundary: return separate candidates when pillars differ.
- Approximate apparent-solar review band: label the nominal result `input_candidate` and any ±guard perturbation `sensitivity_bracket`; the latter is not an asserted input candidate or an empirical error interval.
- `rules.boundary_guard_seconds` is an input/chart sensitivity setting. Do not conflate it with a frozen event's dataset-provided `model_guard_seconds` or with an HKO publication-table authority divergence; callers cannot override either source condition by enlarging or shrinking the user guard.
- A guarded Jie that can change year/month classification creates two valid `calendar_model_variant` rows, not `sensitivity_bracket` rows. More than one applicable guarded Jie fails closed with `CALENDAR_BOUNDARY_UNRESOLVED` unless an exhaustive variant set is encoded.
- Gregorian input near a lunar boundary receives the nominal fixed-UTC+8 lunar value plus `boundary_uncertainty`. If `unresolved_result_change_without_enumerated_variant` is true, treat the lunar label as indeterminate; do not use it as a unique premise.
- Lunar input: interpret the lunar label in a proleptic modern Chinese fixed UTC+8 frame using the hash-verified frozen calendar data, intersect it with the supplied local wall time/zone, and require an input-to-output lunar round trip. Reverse conversion fails closed when the requested label is affected by an event model-guard crossing or explicit historical-authority divergence; `REVIEW_ONLY` does not block conversion. Overseas local dates may differ by one day from the UTC+8 reference date.
- Dayun with an uncertain time: block the provider-specific symbolic start in v0.1 instead of presenting sampled instants as a continuous candidate set.
- Gregorian dates outside 1901-01-01 through 2033-12-31: reject in v0.1. Chinese-lunar label years outside 1900–2033 also reject. Within the envelope, 1900 month 11 day 11 (non-leap) is the first accepted nominal label and leap month 11 day 10 of 2033 is the last; adjacent labels convert outside public Gregorian coverage and fail closed. The 1900–2034 calendar frame and context events through 2035-02-28 do not expand the public input contract.
- Pre-1901 clock records: not supported in v0.1 because LMT/legal-time authority needs separate historical evidence.

## Gregorian + approximate local apparent-solar example

```json
{
  "birth": {
    "calendar": "gregorian",
    "date": "1990-05-15",
    "time": "14:36",
    "timezone": "Asia/Shanghai",
    "longitude": 116.4074
  },
  "traditional_sex_for_dayun": "woman",
  "rules": {
    "time_basis": "local_apparent_solar",
    "compare_civil_clock": true,
    "day_boundary": "both",
    "child_limit_provider": "default"
  }
}
```

## Chinese lunar example

```json
{
  "birth": {
    "calendar": "chinese_lunar",
    "lunar": {"year": 2019, "month": 12, "day": 12, "leap_month": false},
    "time": "11:22",
    "timezone": "Asia/Shanghai"
  },
  "rules": {"time_basis": "civil_clock", "day_boundary": "both"}
}
```
