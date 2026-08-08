#!/usr/bin/env python3
"""Generate frozen Chinese-calendar facts from JPL DE440s with Skyfield.

This reproducible build tool keeps the ephemeris and build-only Python packages
outside the runtime artifact.  It emits only event facts and the independently
implemented fixed-UTC+8 month index needed by the Node adapter.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import re
from bisect import bisect_right
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from skyfield import almanac
from skyfield.api import load
from skyfield.framelib import ecliptic_frame


DAY_MS = 86_400_000
UNIX_EPOCH_JD = 2_440_587.5
BEIJING_OFFSET_MS = 8 * 3_600_000
KERNEL_SHA256 = "c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2"
DELTA_DATA_SHA256 = "9f88e53593495a09219fe956eeadea0fa9f8e3e02c310b2aa2b70852383cdf6f"
DELTA_PREDS_SHA256 = "5d864fddd30b2c64d2a86d3debbb25604eb5de44370c96bccf2abd5463f3db08"
SKYFIELD_VERSION = "1.54"
CALENDAR_GUARD_SECONDS = 600

DELTA_T_SOURCE_CODES = {
    "NASA_PRE1973": 0,
    "USNO_MEASURED": 1,
    "USNO_PREDICTED": 2,
    "CONTINUOUS_LINEAR_SCENARIO": 3,
}

TERM_NAMES = [
    "春分", "清明", "谷雨", "立夏", "小满", "芒种",
    "夏至", "小暑", "大暑", "立秋", "处暑", "白露",
    "秋分", "寒露", "霜降", "立冬", "小雪", "大雪",
    "冬至", "小寒", "大寒", "立春", "雨水", "惊蛰",
]

# These are validation findings, not a copied calendar table.  They identify
# dates where a historical published calendar and the explicitly proleptic
# modern fixed-UTC+8 convention use different month-start civil dates.
HISTORICAL_MONTH_DIVERGENCES = [
    {
        "nominal_month_start_beijing_date": "1914-11-18",
        "historical_oracle_month_start_date": "1914-11-17",
        "code": "HISTORICAL_CALENDAR_AUTHORITY_DIVERGENCE",
        "source_locator": "HKO Gregorian-Lunar Calendar Conversion Table, T1914e.txt",
    },
    {
        "nominal_month_start_beijing_date": "1916-02-04",
        "historical_oracle_month_start_date": "1916-02-03",
        "code": "HISTORICAL_CALENDAR_AUTHORITY_DIVERGENCE",
        "source_locator": "HKO Gregorian-Lunar Calendar Conversion Table, T1916e.txt",
    },
    {
        "nominal_month_start_beijing_date": "1920-11-11",
        "historical_oracle_month_start_date": "1920-11-10",
        "code": "HISTORICAL_CALENDAR_AUTHORITY_DIVERGENCE",
        "source_locator": "HKO Gregorian-Lunar Calendar Conversion Table, T1920e.txt",
    },
]

HISTORICAL_TERM_DATE_DIVERGENCES = [
    {"term": "小雪", "year": 1912, "computed_beijing_date": "1912-11-22",
     "historical_oracle_date": "1912-11-23", "kind": "qi",
     "code": "HISTORICAL_SOLAR_TERM_DATE_DIVERGENCE",
     "source_locator": "HKO Gregorian-Lunar Calendar Conversion Table, T1912e.txt"},
    {"term": "秋分", "year": 1913, "computed_beijing_date": "1913-09-23",
     "historical_oracle_date": "1913-09-24", "kind": "qi",
     "code": "HISTORICAL_SOLAR_TERM_DATE_DIVERGENCE",
     "source_locator": "HKO Gregorian-Lunar Calendar Conversion Table, T1913e.txt"},
    {"term": "大雪", "year": 1917, "computed_beijing_date": "1917-12-08",
     "historical_oracle_date": "1917-12-07", "kind": "jie",
     "code": "HISTORICAL_SOLAR_TERM_DATE_DIVERGENCE",
     "source_locator": "HKO Gregorian-Lunar Calendar Conversion Table, T1917e.txt"},
    {"term": "白露", "year": 1927, "computed_beijing_date": "1927-09-09",
     "historical_oracle_date": "1927-09-08", "kind": "jie",
     "code": "HISTORICAL_SOLAR_TERM_DATE_DIVERGENCE",
     "source_locator": "HKO Gregorian-Lunar Calendar Conversion Table, T1927e.txt"},
    {"term": "夏至", "year": 1928, "computed_beijing_date": "1928-06-22",
     "historical_oracle_date": "1928-06-21", "kind": "qi",
     "code": "HISTORICAL_SOLAR_TERM_DATE_DIVERGENCE",
     "source_locator": "HKO Gregorian-Lunar Calendar Conversion Table, T1928e.txt"},
    {"term": "大寒", "year": 1979, "computed_beijing_date": "1979-01-20",
     "historical_oracle_date": "1979-01-21", "kind": "qi",
     "code": "HISTORICAL_SOLAR_TERM_DATE_DIVERGENCE",
     "source_locator": "HKO Gregorian-Lunar Calendar Conversion Table, T1979e.txt"},
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_input(path: Path, expected: str, label: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise SystemExit(f"{label} SHA-256 mismatch: expected {expected}, got {actual}")


def decimal_year_from_jd(jd: float) -> float:
    milliseconds = (jd - UNIX_EPOCH_JD) * DAY_MS
    value = datetime.fromtimestamp(milliseconds / 1000, UTC)
    start = datetime(value.year, 1, 1, tzinfo=UTC).timestamp()
    end = datetime(value.year + 1, 1, 1, tzinfo=UTC).timestamp()
    return value.year + (value.timestamp() - start) / (end - start)


def nasa_delta_t(decimal_year: float) -> float:
    """NASA GSFC/Espenak-Meeus piecewise polynomial, seconds."""
    if decimal_year < 1920:
        t = decimal_year - 1900
        return (
            -2.79 + 1.494119 * t - 0.0598939 * t**2
            + 0.0061966 * t**3 - 0.000197 * t**4
        )
    if decimal_year < 1941:
        t = decimal_year - 1920
        return 21.20 + 0.84493 * t - 0.076100 * t**2 + 0.0020936 * t**3
    if decimal_year < 1961:
        t = decimal_year - 1950
        return 29.07 + 0.407 * t - t**2 / 233 + t**3 / 2547
    if decimal_year < 1986:
        t = decimal_year - 1975
        return 45.45 + 1.067 * t - t**2 / 260 - t**3 / 718
    if decimal_year < 2005:
        t = decimal_year - 2000
        return (
            63.86 + 0.3345 * t - 0.060374 * t**2 + 0.0017275 * t**3
            + 0.000651814 * t**4 + 0.00002373599 * t**5
        )
    t = decimal_year - 2000
    return 62.92 + 0.32217 * t + 0.005589 * t**2


def parse_delta_data(path: Path) -> tuple[np.ndarray, np.ndarray]:
    mjd = []
    values = []
    for line in path.read_text(encoding="ascii").splitlines():
        fields = line.split()
        if len(fields) != 4:
            continue
        year, month, day = map(int, fields[:3])
        value = float(fields[3])
        unix_ms = datetime(year, month, day, tzinfo=UTC).timestamp() * 1000
        mjd.append(40_587.0 + unix_ms / DAY_MS)
        values.append(value)
    return np.array(mjd), np.array(values)


def parse_delta_preds(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mjd = []
    years = []
    values = []
    errors = []
    pattern = re.compile(
        r"^\s*(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+"
        r"(?:[-+]?\d+(?:\.\d+)?)?\s+(\d+(?:\.\d+)?)\s*$"
    )
    for line in path.read_text(encoding="ascii").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        mjd.append(float(match.group(1)))
        years.append(float(match.group(2)))
        values.append(float(match.group(3)))
        errors.append(float(match.group(4)))
    return np.array(mjd), np.array(years), np.array(values), np.array(errors)


class DeltaTModel:
    def __init__(self, data_path: Path, preds_path: Path):
        self.data_mjd, self.data_values = parse_delta_data(data_path)
        self.pred_mjd, self.pred_years, self.pred_values, self.pred_errors = parse_delta_preds(preds_path)
        x = self.pred_years[-4:]
        y = self.pred_values[-4:]
        centered_x = x - x.mean()
        least_squares_slope = float((centered_x * (y - y.mean())).sum() / (centered_x**2).sum())
        if round(least_squares_slope, 3) != 0.364:
            raise ValueError(f"unexpected USNO last-four-point slope: {least_squares_slope}")
        self.scenario_start_slope = round(least_squares_slope, 3)

    def scenario_delta_t(self, mjd: float) -> float:
        """Continuous engineering scenario after the USNO prediction horizon."""
        start_mjd, value, slope = (
            self.pred_mjd[-1], self.pred_values[-1], self.scenario_start_slope
        )
        elapsed_years = (mjd - start_mjd) / 365.2425
        return value + slope * elapsed_years

    def evaluate(self, tt_jd: float) -> tuple[float, str, float | None, int]:
        # A single iteration is already far below millisecond precision because
        # Delta T is only tens of seconds and changes slowly.
        ut_jd = tt_jd - 70.0 / 86_400
        mjd = ut_jd - 2_400_000.5
        decimal_year = decimal_year_from_jd(ut_jd)
        if mjd < self.data_mjd[0]:
            return nasa_delta_t(decimal_year), "NASA_PRE1973", None, 600
        if mjd <= self.data_mjd[-1]:
            return (
                float(np.interp(mjd, self.data_mjd, self.data_values)),
                "USNO_MEASURED", None, 2,
            )
        if mjd <= self.pred_mjd[-1]:
            error = float(np.interp(mjd, self.pred_mjd, self.pred_errors))
            return (
                float(np.interp(mjd, self.pred_mjd, self.pred_values)),
                "USNO_PREDICTED",
                error,
                math.ceil(error) + 2,
            )
        return (
            self.scenario_delta_t(mjd),
            "CONTINUOUS_LINEAR_SCENARIO",
            None,
            10,
        )

    def tt_to_ut_proxy_ms(self, tt_jd: float) -> tuple[int, str, float | None, int]:
        delta_t, source, prediction_error, model_guard = self.evaluate(tt_jd)
        ut_jd = tt_jd - delta_t / 86_400
        return (
            round((ut_jd - UNIX_EPOCH_JD) * DAY_MS), source,
            prediction_error, model_guard,
        )


def delta_t_boundary_diagnostics(model: DeltaTModel) -> dict:
    epsilon_days = 1e-6

    def value_at_mjd(mjd: float) -> float:
        # Offset the synthetic TT input by the same initial 70-second estimate
        # used inside evaluate(), making the requested proxy-UT MJD explicit.
        tt_jd = mjd + 2_400_000.5 + 70.0 / 86_400
        return model.evaluate(tt_jd)[0]

    diagnostics = {}
    boundaries = [
        ("nasa_to_usno_measured", model.data_mjd[0], 0.2),
        ("usno_measured_to_predicted", model.data_mjd[-1], 0.1),
        ("usno_predicted_to_linear_scenario", model.pred_mjd[-1], 1e-5),
    ]
    for name, mjd, maximum in boundaries:
        left = value_at_mjd(mjd - epsilon_days)
        right = value_at_mjd(mjd + epsilon_days)
        jump = right - left
        if abs(jump) > maximum:
            raise ValueError(f"Delta-T segment boundary {name} jumps by {jump} seconds")
        diagnostics[name] = {
            "boundary_mjd": float(mjd),
            "left_seconds": round(left, 9),
            "right_seconds": round(right, 9),
            "signed_jump_seconds": round(jump, 9),
            "asserted_max_abs_jump_seconds": maximum,
        }
    return diagnostics


def beijing_day(utc_ms: int) -> int:
    return math.floor((utc_ms + BEIJING_OFFSET_MS) / DAY_MS)


def iso_day(day: int) -> str:
    return datetime.fromtimestamp(day * 86_400, UTC).date().isoformat()


def midnight_margin_ms(utc_ms: int) -> int:
    position = (utc_ms + BEIJING_OFFSET_MS) % DAY_MS
    return min(position, DAY_MS - position)


def beijing_day_position_ms(utc_ms: int) -> int:
    return (utc_ms + BEIJING_OFFSET_MS) % DAY_MS


def model_alternative_day_delta(event: dict) -> int:
    position = beijing_day_position_ms(event["utc_ms"])
    guard_ms = event["model_guard_seconds"] * 1000
    if position <= guard_ms:
        return -1
    if DAY_MS - position <= guard_ms:
        return 1
    return 0


def generate_events(kernel: Path, delta_t: DeltaTModel) -> tuple[list[dict], list[dict]]:
    ts = load.timescale(builtin=True)
    eph = load(str(kernel))
    earth = eph["earth"]
    sun = eph["sun"]

    # TT endpoints avoid making the astronomical search itself depend on a
    # historical UTC convention.  The small context buffer supports lunar year
    # 1900 and the next term after 2033-12-31.
    t0 = ts.tt(1900, 1, 1)
    t1 = ts.tt(2035, 3, 1)

    phase_times, phase_codes = almanac.find_discrete(t0, t1, almanac.moon_phases(eph))
    new_moons = []
    for time, code in zip(phase_times, phase_codes):
        if int(code) != 0:
            continue
        tt_jd = float(time.tt)
        utc_ms, source, prediction_error, model_guard = delta_t.tt_to_ut_proxy_ms(tt_jd)
        new_moons.append({
            "tt_jd": tt_jd,
            "utc_ms": utc_ms,
            "beijing_day": beijing_day(utc_ms),
            "midnight_margin_ms": midnight_margin_ms(utc_ms),
            "delta_t_source": source,
            "delta_t_prediction_error_seconds": prediction_error,
            "model_guard_seconds": model_guard,
        })

    def solar_term_index(time):
        apparent = earth.at(time).observe(sun).apparent()
        longitude = apparent.frame_latlon(ecliptic_frame)[1].degrees
        return np.floor((longitude % 360.0) / 15.0).astype(np.int8)

    solar_term_index.step_days = 7.0
    term_times, term_codes = almanac.find_discrete(t0, t1, solar_term_index)
    terms = []
    for time, code in zip(term_times, term_codes):
        tt_jd = float(time.tt)
        utc_ms, source, prediction_error, model_guard = delta_t.tt_to_ut_proxy_ms(tt_jd)
        index = int(code)
        terms.append({
            "tt_jd": tt_jd,
            "utc_ms": utc_ms,
            "beijing_day": beijing_day(utc_ms),
            "midnight_margin_ms": midnight_margin_ms(utc_ms),
            "index": index,
            "name": TERM_NAMES[index],
            "delta_t_source": source,
            "delta_t_prediction_error_seconds": prediction_error,
            "model_guard_seconds": model_guard,
        })
    return new_moons, terms


def containing_new_moon(new_moons: list[dict], day: int) -> int:
    starts = [row["beijing_day"] for row in new_moons]
    index = bisect_right(starts, day) - 1
    if index < 0:
        raise ValueError(f"no new moon before Beijing day {day}")
    return index


def build_lunar_months(new_moons: list[dict], terms: list[dict]) -> list[dict]:
    winter = {
        datetime.fromtimestamp(row["utc_ms"] / 1000, UTC).year: row
        for row in terms if row["index"] == 18
    }
    major_terms = [row for row in terms if row["index"] % 2 == 0]
    rows = []
    for sui_year in range(1900, 2034):
        first_winter = winter[sui_year]
        second_winter = winter[sui_year + 1]
        first = containing_new_moon(new_moons, first_winter["beijing_day"])
        second = containing_new_moon(new_moons, second_winter["beijing_day"])
        count = second - first
        if count not in (12, 13):
            raise ValueError(f"invalid lunation count for sui {sui_year}: {count}")
        leap_offset = None
        if count == 13:
            for offset in range(1, count):
                start = new_moons[first + offset]["beijing_day"]
                end = new_moons[first + offset + 1]["beijing_day"]
                if not any(start <= term["beijing_day"] < end for term in major_terms):
                    leap_offset = offset
                    break
            if leap_offset is None:
                raise ValueError(f"no leap month in 13-lunation sui {sui_year}")

        for offset in range(count):
            is_leap = offset == leap_offset
            ordinal = offset - 1 if leap_offset is not None and offset >= leap_offset else offset
            month_number = ((10 + ordinal) % 12) + 1
            start = new_moons[first + offset]
            end = new_moons[first + offset + 1]
            rows.append({
                "start_day": start["beijing_day"],
                "end_day": end["beijing_day"],
                "lunar_year": sui_year if month_number >= 11 else sui_year + 1,
                "month": month_number,
                "leap": is_leap,
                "start": start,
                "end": end,
            })

    unique = {}
    for row in rows:
        existing = unique.get(row["start_day"])
        if existing is not None:
            identity = ("lunar_year", "month", "leap", "end_day")
            if any(existing[key] != row[key] for key in identity):
                raise ValueError(
                    f"overlapping sui rows disagree at {iso_day(row['start_day'])}: "
                    f"{existing} versus {row}"
                )
            if existing["start"]["utc_ms"] != row["start"]["utc_ms"]:
                raise ValueError("overlapping sui rows use different new-moon events")
            continue
        unique[row["start_day"]] = row
    return [unique[key] for key in sorted(unique)]


def assert_boundary_guards_preserve_major_term_membership(
    months: list[dict], terms: list[dict]
) -> None:
    """Reject a freeze whose event guards make the leap-month sequence non-unique.

    A new-moon guard that crosses Beijing midnight gives the affected month
    boundary two candidate civil dates.  A major term can independently have
    two candidate civil dates under its own event guard.  Test their Cartesian
    product explicitly: if either event could move the major term across that
    month boundary, the nominal month/leap sequence is not a sufficient runtime
    representation and explicit alternate sequences must be generated instead.
    """
    major_terms = [term for term in terms if term["index"] % 2 == 0]
    for row in months[1:]:
        nominal_boundary = row["start_day"]
        boundary_delta = model_alternative_day_delta(row["start"])
        if boundary_delta == 0:
            continue
        boundary_candidates = {nominal_boundary, nominal_boundary + boundary_delta}
        for term in major_terms:
            term_delta = model_alternative_day_delta(term)
            term_candidates = {term["beijing_day"]}
            if term_delta:
                term_candidates.add(term["beijing_day"] + term_delta)
            nominal_is_on_or_after_boundary = term["beijing_day"] >= nominal_boundary
            candidate_memberships = {
                term_day >= boundary_day
                for boundary_day in boundary_candidates
                for term_day in term_candidates
            }
            if candidate_memberships != {nominal_is_on_or_after_boundary}:
                raise ValueError(
                    "new-moon and major-term model guards make lunar-month "
                    f"membership non-unique at {iso_day(nominal_boundary)} for "
                    f"{term['name']} on {iso_day(term['beijing_day'])}; generate "
                    "and encode explicit alternate month sequences before release"
                )


def encode_months(months: list[dict], terms: list[dict]) -> tuple[list[list], dict, list[list]]:
    historical_by_nominal = {
        item["nominal_month_start_beijing_date"]: item
        for item in HISTORICAL_MONTH_DIVERGENCES
    }
    encoded = []
    term_divergence_days = {
        math.floor(datetime.fromisoformat(item[key]).replace(tzinfo=UTC).timestamp() / 86_400)
        for item in HISTORICAL_TERM_DATE_DIVERGENCES if item["kind"] == "qi"
        for key in ("computed_beijing_date", "historical_oracle_date")
    }
    month_starts = [row["start_day"] for row in months]
    uncertainty_events: dict[int, list[list]] = {index: [] for index in range(len(months))}
    blocking_term_months: set[int] = set()

    # A major term can change lunar-month membership only when its own model
    # guard crosses midnight *and* the alternate civil date lies across a
    # lunar-month boundary.  Merely being near midnight inside a month is a
    # review fact, not a blocking uncertainty.
    for term in terms:
        if term["index"] % 2:
            continue
        nominal_index = bisect_right(month_starts, term["beijing_day"]) - 1
        if not 0 <= nominal_index < len(months):
            continue
        if term["midnight_margin_ms"] <= CALENDAR_GUARD_SECONDS * 1000:
            uncertainty_events[nominal_index].append([
                2, term["utc_ms"], term["index"], term["midnight_margin_ms"],
                term["model_guard_seconds"], DELTA_T_SOURCE_CODES[term["delta_t_source"]],
                0, model_alternative_day_delta(term),
            ])
        position = beijing_day_position_ms(term["utc_ms"])
        guard_ms = term["model_guard_seconds"] * 1000
        affected: set[int] = set()
        if position <= guard_ms and term["beijing_day"] == months[nominal_index]["start_day"]:
            affected.update((nominal_index - 1, nominal_index))
        if DAY_MS - position <= guard_ms and term["beijing_day"] == months[nominal_index]["end_day"] - 1:
            affected.update((nominal_index, nominal_index + 1))
        for index in sorted(index for index in affected if 0 <= index < len(months)):
            blocking_term_months.add(index)
            uncertainty_events[index].append([
                3, term["utc_ms"], term["index"], term["midnight_margin_ms"],
                term["model_guard_seconds"], DELTA_T_SOURCE_CODES[term["delta_t_source"]],
                1, model_alternative_day_delta(term),
            ])
    if blocking_term_months:
        raise ValueError(
            "a major-term model guard changes lunar-month membership; "
            "generate and encode explicit alternate month sequences before release"
        )

    flagged = {
        "new_moon_within_600s_review": 0,
        "major_term_within_600s_review": 0,
        "model_guard_changes_calendar_date_or_membership": 0,
        "historical_divergence": 0,
        "historical_term_date_divergence_audit": 0,
    }
    for row_index, row in enumerate(months):
        flags = 0
        start_near = row["start"]["midnight_margin_ms"] <= CALENDAR_GUARD_SECONDS * 1000
        end_near = row["end"]["midnight_margin_ms"] <= CALENDAR_GUARD_SECONDS * 1000
        if start_near:
            flags |= 1
            uncertainty_events[row_index].append([
                0, row["start"]["utc_ms"], -1, row["start"]["midnight_margin_ms"],
                row["start"]["model_guard_seconds"],
                DELTA_T_SOURCE_CODES[row["start"]["delta_t_source"]],
                int(row["start"]["midnight_margin_ms"] <= row["start"]["model_guard_seconds"] * 1000),
                model_alternative_day_delta(row["start"]),
            ])
        if end_near:
            flags |= 2
            uncertainty_events[row_index].append([
                1, row["end"]["utc_ms"], -1, row["end"]["midnight_margin_ms"],
                row["end"]["model_guard_seconds"],
                DELTA_T_SOURCE_CODES[row["end"]["delta_t_source"]],
                int(row["end"]["midnight_margin_ms"] <= row["end"]["model_guard_seconds"] * 1000),
                model_alternative_day_delta(row["end"]),
            ])
        if any(event[0] in (2, 3) for event in uncertainty_events[row_index]):
            flags |= 4
        new_moon_blocking = (
            row["start"]["midnight_margin_ms"] <= row["start"]["model_guard_seconds"] * 1000
            or row["end"]["midnight_margin_ms"] <= row["end"]["model_guard_seconds"] * 1000
        )
        if new_moon_blocking or row_index in blocking_term_months:
            flags |= 8
        start_date = iso_day(row["start_day"])
        end_date = iso_day(row["end_day"])
        if start_date in historical_by_nominal:
            flags |= 16
        if end_date in historical_by_nominal:
            flags |= 32
        if any(row["start_day"] <= day < row["end_day"] for day in term_divergence_days):
            flags |= 64
        if start_near or end_near:
            flagged["new_moon_within_600s_review"] += 1
        if flags & 4:
            flagged["major_term_within_600s_review"] += 1
        if flags & 8:
            flagged["model_guard_changes_calendar_date_or_membership"] += 1
        if flags & (16 | 32):
            flagged["historical_divergence"] += 1
        if flags & 64:
            flagged["historical_term_date_divergence_audit"] += 1
        encoded.append([
            row["start_day"], row["lunar_year"], row["month"], int(row["leap"]),
            row["end_day"] - row["start_day"], row["start"]["utc_ms"],
            row["start"]["midnight_margin_ms"], row["start"]["model_guard_seconds"],
            DELTA_T_SOURCE_CODES[row["start"]["delta_t_source"]], flags,
        ])
    flattened_events = [
        [months[index]["start_day"], *event]
        for index in range(len(months))
        for event in sorted(set(tuple(item) for item in uncertainty_events[index]))
    ]
    return encoded, flagged, flattened_events


def build_dataset(kernel: Path, delta_data: Path, delta_preds: Path) -> dict:
    verify_input(kernel, KERNEL_SHA256, "DE440s")
    verify_input(delta_data, DELTA_DATA_SHA256, "USNO deltat.data")
    verify_input(delta_preds, DELTA_PREDS_SHA256, "USNO deltat.preds")
    version = importlib.metadata.version("skyfield")
    if version != SKYFIELD_VERSION:
        raise SystemExit(f"Skyfield version mismatch: expected {SKYFIELD_VERSION}, got {version}")

    delta_t = DeltaTModel(delta_data, delta_preds)
    boundary_diagnostics = delta_t_boundary_diagnostics(delta_t)
    new_moons, terms = generate_events(kernel, delta_t)
    for fact in HISTORICAL_TERM_DATE_DIVERGENCES:
        matches = [
            row for row in terms
            if row["name"] == fact["term"]
            and datetime.fromtimestamp((row["utc_ms"] + BEIJING_OFFSET_MS) / 1000, UTC).year
            == fact["year"]
        ]
        if len(matches) != 1:
            raise ValueError(f"expected one JPL event for validation fact: {fact}")
        computed = iso_day(matches[0]["beijing_day"])
        if computed != fact["computed_beijing_date"]:
            raise ValueError(
                f"JPL validation fact changed for {fact['year']} {fact['term']}: "
                f"expected {fact['computed_beijing_date']}, got {computed}"
            )
    months = build_lunar_months(new_moons, terms)
    assert_boundary_guards_preserve_major_term_membership(months, terms)
    encoded_months, flagged_months, lunar_uncertainty_events = encode_months(months, terms)
    encoded_terms = [
        [
            row["utc_ms"], row["index"],
            row["model_guard_seconds"],
            DELTA_T_SOURCE_CODES[row["delta_t_source"]],
        ]
        for row in terms
    ]

    support_start = datetime(1901, 1, 1, tzinfo=UTC).timestamp() * 1000
    support_end = datetime(2034, 1, 1, tzinfo=UTC).timestamp() * 1000
    near_new_moons = [
        row for row in new_moons
        if support_start <= row["utc_ms"] < support_end
        and row["midnight_margin_ms"] <= CALENDAR_GUARD_SECONDS * 1000
    ]
    near_terms = [
        row for row in terms
        if support_start <= row["utc_ms"] < support_end
        and row["midnight_margin_ms"] <= CALENDAR_GUARD_SECONDS * 1000
    ]
    return {
        "schema_version": "xuanshu-calendar-data-v0.2",
        "calendar_core_version": "jpl-de440s-skyfield-1.54-v1",
        "coverage": {
            "supported_gregorian_year_min": 1901,
            "supported_gregorian_year_max": 2033,
            "public_solar_start": "1901-01-01",
            "public_solar_end": "2033-12-31",
            "lunar_label_year_envelope_min": 1900,
            "lunar_label_year_envelope_max": 2033,
            "lunar_year_padding_min": 1900,
            "lunar_label_edge_policy": "the_1900_and_2033_label_years_are_partial; accept_only_when_the_unique_nominal_label_converts_within_public_solar_start_and_public_solar_end",
            "first_nominal_lunar_label": {"year": 1900, "month": 11, "day": 11, "leap_month": False},
            "last_nominal_lunar_label": {"year": 2033, "month": 11, "day": 10, "leap_month": True},
            "context_events_from": "1900-01-01",
            "context_events_through": "2035-02-28",
        },
        "frame": {
            "calendar_day_boundary": "fixed_UTC+08:00",
            "event_time_scale": "TT_minus_frozen_DeltaT_as_UT1_proxy_for_UTC",
            "term_longitude": "geocentric_apparent_ecliptic_of_date",
            "month_rule": "month_11_contains_winter_solstice; first_no-major-term_month_is_leap",
        },
        "sources": {
            "ephemeris": {
                "name": "JPL DE440s",
                "source": "https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de440s.bsp",
                "mirror": "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp",
                "sha256": KERNEL_SHA256,
                "build_dependency_runtime_distributed": False,
            },
            "generator": {
                "name": "Skyfield",
                "version": SKYFIELD_VERSION,
                "license": "MIT",
                "source": "https://github.com/skyfielders/python-skyfield/tree/1.54",
                "build_dependency_runtime_distributed": False,
            },
            "delta_t_measured": {
                "source": "https://maia.usno.navy.mil/ser7/deltat.data",
                "sha256": DELTA_DATA_SHA256,
            },
            "delta_t_predictions": {
                "source": "https://maia.usno.navy.mil/ser7/deltat.preds",
                "sha256": DELTA_PREDS_SHA256,
                "last_prediction_decimal_year": 2033.75,
                "last_prediction_mjd": 63871.0,
            },
            "delta_t_historical": {
                "source": "https://eclipse.gsfc.nasa.gov/SEcat5/deltatpoly.html",
                "implementation": "independent transcription of published piecewise polynomials",
            },
            "delta_t_context_scenario": {
                "name": "continuous linear engineering scenario",
                "start": {
                    "mjd": 63871.0,
                    "seconds": 71.25,
                    "slope_seconds_per_year": delta_t.scenario_start_slope,
                    "slope_derivation": "ordinary_least_squares_last_4_quarterly_USNO_prediction_points",
                    "slope_sample_count": 4,
                    "slope_x_axis": "USNO_decimal_year",
                    "slope_sample_decimal_year_range": [2033.0, 2033.75],
                    "slope_sample_mjd_range": [63597.0, 63871.0],
                    "slope_formula": "sum((x-mean(x))*(y-mean(y)))/sum((x-mean(x))^2)",
                },
                "formula": "delta_t=71.25+slope*(mjd-63871.0)/365.2425",
                "context_limit": "2035-02-28",
                "status": "SCENARIO_NOT_PREDICTION",
            },
        },
        "uncertainty": {
            "near_midnight_review_seconds": CALENDAR_GUARD_SECONDS,
            "near_midnight_review_is_certified_error_bound": False,
            "per_event_model_guard_is_certified_error_bound": False,
            "model_guard_role": "engineering_review_and_fail_closed_threshold_not_probability_or_confidence_interval",
            "per_event_model_guard_policy": {
                "pre_1973_seconds": 600,
                "usno_measured_seconds": 2,
                "usno_predicted_seconds": "ceil(published_error_seconds)+2",
                "post_USNO_context_linear_scenario_seconds": 10,
            },
            "lunar_input_policy": "fail_closed_only_when_the_requested_date_is_affected_by_a_model_guard_crossing_or_explicit_historical_calendar_divergence",
            "gregorian_chart_policy": "return_nominal_fixed_UTC+8_value_with_uncertainty_metadata",
            "near_midnight_new_moon_count_1901_2033": len(near_new_moons),
            "near_midnight_term_count_1901_2033": len(near_terms),
            "flagged_lunar_month_rows": flagged_months,
            "historical_calendar_divergences": HISTORICAL_MONTH_DIVERGENCES,
            "delta_t_segment_boundary_diagnostics": boundary_diagnostics,
        },
        "validation_facts": {
            "oracle_role": "local_validation_only; not a generation input; no source text redistributed",
            "oracle_source": "https://www.hko.gov.hk/en/gts/time/conversion1_text.htm",
            "compared_gregorian_day_rows_1901_2033": 48_578,
            "compared_solar_term_rows_1901_2033": 3_192,
            "historical_month_start_date_divergences": HISTORICAL_MONTH_DIVERGENCES,
            "solar_term_date_divergences": HISTORICAL_TERM_DATE_DIVERGENCES,
        },
        "encoding": {
            "term_names_by_index": TERM_NAMES,
            "delta_t_source_codes": {
                "0": "NASA_PRE1973",
                "1": "USNO_MEASURED",
                "2": "USNO_PREDICTED",
                "3": "CONTINUOUS_LINEAR_SCENARIO",
            },
            "terms": [
                "unix_ms_ut1_proxy", "term_index", "model_guard_seconds",
                "delta_t_source_code",
            ],
            "lunar_months": [
                "start_beijing_unix_day", "lunar_year", "month", "leap_flag", "length_days",
                "start_unix_ms_ut1_proxy", "start_midnight_margin_ms", "start_model_guard_seconds",
                "start_delta_t_source_code", "uncertainty_flags",
            ],
            "lunar_uncertainty_events": [
                "month_start_beijing_unix_day", "event_type", "event_unix_ms_ut1_proxy",
                "term_index_or_minus_one", "midnight_margin_ms", "model_guard_seconds",
                "delta_t_source_code", "changes_calendar_assignment",
                "alternative_beijing_day_delta",
            ],
            "lunar_uncertainty_event_types": {
                "0": "START_NEW_MOON_REVIEW",
                "1": "END_NEW_MOON_REVIEW",
                "2": "MAJOR_TERM_NEAR_MIDNIGHT_REVIEW",
                "3": "MAJOR_TERM_MODEL_GUARD_CHANGES_MONTH_MEMBERSHIP",
            },
            "lunar_uncertainty_flags": {
                "1": "START_NEW_MOON_WITHIN_600S_OF_BEIJING_MIDNIGHT",
                "2": "END_NEW_MOON_WITHIN_600S_OF_BEIJING_MIDNIGHT",
                "4": "RELATED_MAJOR_TERM_WITHIN_600S_OF_BEIJING_MIDNIGHT",
                "8": "EVENT_MODEL_GUARD_CHANGES_CALENDAR_DATE_OR_MONTH_MEMBERSHIP",
                "16": "HISTORICAL_CALENDAR_DIVERGENCE_AT_START",
                "32": "HISTORICAL_CALENDAR_DIVERGENCE_AT_END",
                "64": "HISTORICAL_MAJOR_TERM_DATE_DIVERGENCE_AUDIT",
            },
        },
        "terms": encoded_terms,
        "lunar_months": encoded_months,
        "lunar_uncertainty_events": lunar_uncertainty_events,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", required=True, type=Path)
    parser.add_argument("--delta-data", required=True, type=Path)
    parser.add_argument("--delta-preds", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    dataset = build_dataset(args.kernel, args.delta_data, args.delta_preds)
    payload = json.dumps(dataset, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    args.output.write_text(payload, encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "sha256": sha256(args.output),
        "term_count": len(dataset["terms"]),
        "lunar_month_count": len(dataset["lunar_months"]),
        "uncertainty": dataset["uncertainty"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
