#!/usr/bin/env python3
"""Auditable Four Pillars input normalization and deterministic chart orchestration.

The script separates historical civil-time resolution from the calendrical core.
It never infers a missing timezone, longitude, DST fold, or day-rollover school.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.resources
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


ENGINE_VERSION = "0.1.0"
RULESET_VERSION = "xuanshu-audit-v0.1"
SUPPORTED_YEAR_MIN = 1901
SUPPORTED_YEAR_MAX = 2033
SUPPORTED_LUNAR_YEAR_MIN = 1900
SUPPORTED_LUNAR_YEAR_MAX = 2033
CALENDAR_FRAME_YEAR_MIN = 1900
CALENDAR_FRAME_YEAR_MAX = 2034
EXPECTED_TZDATA_PACKAGE_VERSION = "2026.3"
EXPECTED_TZDB_VERSION = "2026c"
MAX_TZIF_BYTES = 4 * 1024 * 1024
MAX_JSON_INPUT_BYTES = 1024 * 1024
MAX_NODE_INPUT_BYTES = 4 * 1024 * 1024
MAX_NODE_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_NORMALIZED_CASES = 3000
NODE_TIMEOUT_SECONDS = 30
CORE_RESPONSE_SCHEMA = "xuanshu-four-pillars-core-response-v0.2"
MAX_CORE_VARIANTS_PER_SOURCE_CASE = 8
CORE_EVENT_TIME_SCALE = "TT_MINUS_FROZEN_DELTAT_AS_UT1_PROXY"
CORE_ENGINE_NAME = "xuanshu-four-pillars-core"
CORE_ENGINE_VERSION = "0.1.0"
CORE_TERM_FRAME = (
    "absolute_instant_against_frozen_TT_minus_DeltaT_UT1_proxy_events"
)
CORE_CALENDAR_DAY_FRAME = "fixed_UTC+08:00"
DELTA_T_SOURCE_CODES = frozenset({
    "NASA_PRE1973",
    "USNO_MEASURED",
    "USNO_PREDICTED",
    "CONTINUOUS_LINEAR_SCENARIO",
})
TERM_NAMES = (
    "春分", "清明", "谷雨", "立夏", "小满", "芒种",
    "夏至", "小暑", "大暑", "立秋", "处暑", "白露",
    "秋分", "寒露", "霜降", "立冬", "小雪", "大雪",
    "冬至", "小寒", "大寒", "立春", "雨水", "惊蛰",
)
TERM_KIND_BY_NAME = {
    name: ("jie" if index % 2 else "qi")
    for index, name in enumerate(TERM_NAMES)
}
STEMS = tuple("甲乙丙丁戊己庚辛壬癸")
BRANCHES = tuple("子丑寅卯辰巳午未申酉戌亥")
STEM_ELEMENT = dict(zip(STEMS, ("木", "木", "火", "火", "土", "土", "金", "金", "水", "水")))
BRANCH_ELEMENT = dict(zip(BRANCHES, ("水", "土", "木", "木", "土", "火", "火", "土", "金", "金", "土", "水")))
STEM_ELEMENT_INDEX = (0, 0, 1, 1, 2, 2, 3, 3, 4, 4)
ELEMENT_GENERATES = (1, 2, 3, 4, 0)
ELEMENT_CONTROLS = (2, 3, 4, 0, 1)
YIN_YANG = ("yang", "yin")
TEN_GODS = frozenset({
    "日主", "比肩", "劫财", "食神", "伤官", "偏财", "正财",
    "七杀", "正官", "偏印", "正印",
})
HIDDEN_STEM_ROLES = frozenset({"main", "middle", "residual"})
TERRAIN_SEQUENCE = (
    "长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死",
    "墓", "绝", "胎", "养",
)
TERRAINS = frozenset(TERRAIN_SEQUENCE)
TERRAIN_START = (11, 6, 2, 9, 2, 9, 5, 0, 8, 3)
NAYIN = (
    "海中金", "炉中火", "大林木", "路旁土", "剑锋金", "山头火",
    "涧下水", "城头土", "白蜡金", "杨柳木", "泉中水", "屋上土",
    "霹雳火", "松柏木", "长流水", "沙中金", "山下火", "平地木",
    "壁上土", "金箔金", "覆灯火", "天河水", "大驿土", "钗钏金",
    "桑柘木", "大溪水", "沙中土", "天上火", "石榴木", "大海水",
)
HIDDEN_STEMS = (
    (("癸", "main"),),
    (("己", "main"), ("癸", "middle"), ("辛", "residual")),
    (("甲", "main"), ("丙", "middle"), ("戊", "residual")),
    (("乙", "main"),),
    (("戊", "main"), ("乙", "middle"), ("癸", "residual")),
    (("丙", "main"), ("庚", "middle"), ("戊", "residual")),
    (("丁", "main"), ("己", "middle")),
    (("己", "main"), ("丁", "middle"), ("乙", "residual")),
    (("庚", "main"), ("壬", "middle"), ("戊", "residual")),
    (("辛", "main"),),
    (("戊", "main"), ("辛", "middle"), ("丁", "residual")),
    (("壬", "main"), ("甲", "middle")),
)
LUNAR_MONTH_NAMES = (
    "正月", "二月", "三月", "四月", "五月", "六月",
    "七月", "八月", "九月", "十月", "十一月", "十二月",
)
LUNAR_DAY_NAMES = (
    "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
)
LUNAR_BOUNDARY_STATUSES = frozenset({
    "CLEAR",
    "REVIEW_ONLY",
    "MODEL_GUARD_CROSSES_BEIJING_MIDNIGHT",
    "HISTORICAL_CONVENTION_DIVERGENCE",
    "MULTIPLE_BOUNDARY_UNCERTAINTIES",
})
LUNAR_EVENT_NAMES = frozenset({
    "start_new_moon_review",
    "end_new_moon_review",
    "major_term_near_midnight_review",
    "major_term_model_guard_changes_month_membership",
})
CORE_INPUT_ERROR_CODES = frozenset({
    "INVALID_UTF8",
    "INVALID_JSON",
    "INVALID_CORE_REQUEST",
    "INVALID_LUNAR_DATE",
    "LUNAR_DATE_OUTSIDE_GREGORIAN_COVERAGE",
    "LUNAR_BOUNDARY_MODEL_GUARD",
    "HISTORICAL_CALENDAR_AUTHORITY_DIVERGENCE",
    "INCONSISTENT_ABSOLUTE_AND_BEIJING_TIME",
    "UNSUPPORTED_CALENDAR_RANGE",
    "CALENDAR_BOUNDARY_UNRESOLVED",
})
SCRIPT_DIR = Path(__file__).resolve().parent
NODE_CORE = SCRIPT_DIR / "four_pillars_core.js"
CALENDAR_DATA = SCRIPT_DIR / "data" / "calendar-1901-2033.json"
# Release-pinned artifact digests. Future replacement requires reviewed
# regeneration, a ruleset/version bump, and a corresponding validation update.
NODE_CORE_SHA256 = "8b3cb09cd9468ab9bfb6c199c58fd053f1e025fca2ac059fe7ee846755773655"
CALENDAR_DATA_SHA256 = "65189952013b9471e6a0e8a63109ce6305d6242588ec6e3fabdb8ddd0bdd4509"
REFERENCE_DIR = SCRIPT_DIR.parent / "references"
MANIFEST_HASHES = {
    "rule_registry": (
        REFERENCE_DIR / "rule-registry.json",
        "6c456ef5a07bd25c25f623e4454dceeb95380c30135d8e0abd4be34ab50d816d",
    ),
    "provider_manifest": (
        REFERENCE_DIR / "provider-manifest.json",
        "fe1ee21985395c378bf99b03adf988fcae29e4af127735bc631b06a42c480f29",
    ),
    "provenance_manifest": (
        REFERENCE_DIR / "provenance-manifest.json",
        "3a219920f4d9b373e415ca2c767740aecd7bc133682a4cd147cfa7235598af28",
    ),
}


class InputContractError(ValueError):
    """Raised when a user input cannot be resolved without guessing."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or self.__class__.__name__


@dataclass(frozen=True)
class ZoneBundle:
    zone: ZoneInfo
    source: str
    version: str
    sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_calendar_data() -> str:
    """Return the digest of the frozen runtime dataset after a fail-closed check."""
    if not CALENDAR_DATA.is_file():
        raise RuntimeError(f"Frozen calendar dataset is missing: {CALENDAR_DATA}")
    actual = sha256_file(CALENDAR_DATA)
    if CALENDAR_DATA_SHA256.startswith("PENDING_"):
        raise RuntimeError(
            "Frozen calendar dataset has not been release-pinned; replace "
            "CALENDAR_DATA_SHA256 with its reviewed SHA-256 digest"
        )
    if actual != CALENDAR_DATA_SHA256:
        raise RuntimeError(
            "Frozen calendar dataset integrity check failed; update the ruleset "
            "version and pinned digest only after regenerating and reviewing it"
        )
    return actual


def verify_node_core() -> str:
    """Return the digest of the reviewed Node core after a fail-closed check."""
    if not NODE_CORE.is_file():
        raise RuntimeError(f"Calendrical core is missing: {NODE_CORE}")
    actual = sha256_file(NODE_CORE)
    if NODE_CORE_SHA256.startswith("PENDING_"):
        raise RuntimeError(
            "Calendrical core has not been release-pinned; replace "
            "NODE_CORE_SHA256 with its reviewed SHA-256 digest"
        )
    if actual != NODE_CORE_SHA256:
        raise RuntimeError("Calendrical core integrity check failed")
    return actual


def load_manifest_identity() -> dict[str, dict[str, str]]:
    identity: dict[str, dict[str, str]] = {}
    for name, (path, expected) in MANIFEST_HASHES.items():
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(
                f"{name} integrity check failed; update the ruleset version and pinned hash"
            )
        value = json.loads(path.read_text(encoding="utf-8"))
        schema = value.get("schema_version")
        if not isinstance(schema, str) or not schema:
            raise RuntimeError(f"{name} has no valid schema_version")
        identity[name] = {"schema_version": schema, "sha256": actual}
    return identity


def load_frozen_zone(key: str) -> ZoneBundle:
    if not isinstance(key, str) or not key:
        raise InputContractError("birth.timezone must be an IANA timezone such as Asia/Shanghai")
    if key.startswith(("/", "\\")) or "\\" in key:
        raise InputContractError("birth.timezone must be a canonical relative IANA key")
    parts = key.split("/")
    if any(
        part in {"", ".", ".."} or re.fullmatch(r"[A-Za-z0-9._+-]+", part) is None
        for part in parts
    ):
        raise InputContractError("birth.timezone contains an invalid IANA path component")
    try:
        package_version = importlib.metadata.version("tzdata")
        if package_version != EXPECTED_TZDATA_PACKAGE_VERSION:
            raise InputContractError(
                "Frozen timezone dependency mismatch: "
                f"expected tzdata {EXPECTED_TZDATA_PACKAGE_VERSION}, received {package_version}"
            )
        root = Path(str(importlib.resources.files("tzdata").joinpath("zoneinfo"))).resolve()
        zone_path = root.joinpath(*parts).resolve()
        try:
            zone_path.relative_to(root)
        except ValueError as exc:
            raise InputContractError("birth.timezone escaped the frozen timezone root") from exc
        if not zone_path.is_file():
            raise InputContractError(f"Unknown IANA timezone: {key}")
        size = zone_path.stat().st_size
        if not 1 <= size <= MAX_TZIF_BYTES:
            raise InputContractError(f"Invalid or oversized TZif file for timezone: {key}")
        try:
            with zone_path.open("rb") as handle:
                zone = ZoneInfo.from_file(handle, key=key)
        except (OSError, ValueError) as exc:
            raise InputContractError(f"Invalid TZif data for timezone: {key}") from exc
        version_line = root.joinpath("tzdata.zi").read_text(encoding="utf-8").splitlines()[0]
        version = version_line.removeprefix("# version ").strip()
        if version != EXPECTED_TZDB_VERSION:
            raise InputContractError(
                f"Frozen tzdb mismatch: expected {EXPECTED_TZDB_VERSION}, received {version}"
            )
        return ZoneBundle(zone, "python-tzdata-frozen", version, sha256_file(zone_path))
    except ModuleNotFoundError as exc:
        raise InputContractError(
            f"tzdata=={EXPECTED_TZDATA_PACKAGE_VERSION} is required; system-zoneinfo fallback is disabled"
        ) from exc


def parse_date(value: str) -> date:
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        raise InputContractError("birth.date must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise InputContractError("birth.date must use YYYY-MM-DD") from exc
    if not SUPPORTED_YEAR_MIN <= parsed.year <= SUPPORTED_YEAR_MAX:
        raise InputContractError(
            f"Supported development range is {SUPPORTED_YEAR_MIN}-{SUPPORTED_YEAR_MAX}; received {parsed.year}"
        )
    return parsed


def parse_time(value: str) -> time:
    if not isinstance(value, str) or re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", value) is None:
        raise InputContractError("birth.time values must use HH:MM or HH:MM:SS")
    try:
        parsed = time.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise InputContractError("birth.time values must use HH:MM or HH:MM:SS") from exc
    if parsed.tzinfo is not None:
        raise InputContractError("birth.time must be a local wall-clock time without an offset")
    if parsed.microsecond:
        raise InputContractError("birth.time supports whole seconds only")
    return parsed


def strict_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputContractError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise InputContractError(f"{field} must be between {minimum} and {maximum}")
    return value


def strict_number(value: Any, field: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputContractError(f"{field} must be a JSON number")
    try:
        parsed = float(value)
    except (OverflowError, ValueError) as exc:
        raise InputContractError(
            f"{field} must be finite and between {minimum} and {maximum}"
        ) from exc
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise InputContractError(f"{field} must be finite and between {minimum} and {maximum}")
    return parsed


def strict_choice(value: Any, field: str, allowed: set[str]) -> str:
    """Validate a JSON string enum without hashing attacker-controlled values."""
    if not isinstance(value, str) or value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise InputContractError(f"{field} must be one of: {choices}")
    return value


def strict_json_loads(text: str) -> Any:
    """Decode JSON while rejecting duplicate keys and non-standard numbers."""
    if len(text.encode("utf-8")) > MAX_JSON_INPUT_BYTES:
        raise InputContractError("JSON input exceeds the safe 1 MiB limit")

    def reject_constant(value: str) -> None:
        raise InputContractError(f"Non-standard JSON number is not allowed: {value}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise InputContractError(f"Duplicate JSON object key is not allowed: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except InputContractError:
        raise
    except RecursionError as exc:
        raise InputContractError("JSON input nesting is too deep") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise InputContractError("Input is not one valid strict JSON document") from exc


def reject_unknown_fields(value: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise InputContractError(f"Unsupported {field} field(s): {', '.join(unknown)}")


def validate_payload(payload: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(payload, dict):
        raise InputContractError("Top-level input must be a JSON object")
    reject_unknown_fields(
        payload, {"birth", "rules", "traditional_sex_for_dayun"}, "top-level"
    )
    birth = payload.get("birth")
    if not isinstance(birth, dict):
        raise InputContractError("birth must be an object")
    reject_unknown_fields(
        birth,
        {
            "calendar", "date", "lunar", "time", "time_range", "timezone",
            "longitude", "fold", "uncertainty_minutes",
        },
        "birth",
    )
    rules = payload["rules"] if "rules" in payload else {}
    if not isinstance(rules, dict):
        raise InputContractError("rules must be an object")
    reject_unknown_fields(
        rules,
        {
            "year_boundary", "month_boundary", "term_frame", "time_basis",
            "compare_civil_clock", "day_boundary", "child_limit_provider",
            "decade_count", "boundary_guard_seconds",
        },
        "rules",
    )

    calendar = strict_choice(
        birth.get("calendar", "gregorian"),
        "birth.calendar",
        {"gregorian", "chinese_lunar"},
    )
    if calendar == "gregorian":
        if "date" not in birth or "lunar" in birth:
            raise InputContractError("Gregorian input requires birth.date and forbids birth.lunar")
    else:
        if "lunar" not in birth or "date" in birth:
            raise InputContractError("Chinese-lunar input requires birth.lunar and forbids birth.date")
        lunar = birth["lunar"]
        if not isinstance(lunar, dict):
            raise InputContractError("birth.lunar must be an object")
        reject_unknown_fields(lunar, {"year", "month", "day", "leap_month"}, "birth.lunar")
        if set(lunar) != {"year", "month", "day", "leap_month"}:
            raise InputContractError(
                "birth.lunar requires year, month, day, and an explicit boolean leap_month"
            )
        strict_int(
            lunar["year"],
            "birth.lunar.year",
            SUPPORTED_LUNAR_YEAR_MIN,
            SUPPORTED_LUNAR_YEAR_MAX,
        )
        strict_int(lunar["month"], "birth.lunar.month", 1, 12)
        strict_int(lunar["day"], "birth.lunar.day", 1, 30)
        if not isinstance(lunar["leap_month"], bool):
            raise InputContractError("birth.lunar.leap_month must be a JSON boolean")

    has_time = birth.get("time") is not None
    has_range = birth.get("time_range") is not None
    if has_time and has_range:
        raise InputContractError("birth.time and birth.time_range are mutually exclusive")
    if has_time:
        parse_time(birth["time"])
    if has_range:
        interval = birth["time_range"]
        if not isinstance(interval, dict):
            raise InputContractError("birth.time_range must be an object")
        reject_unknown_fields(interval, {"start", "end"}, "birth.time_range")
        if set(interval) != {"start", "end"}:
            raise InputContractError("birth.time_range requires exactly start and end")
        parse_time(interval["start"])
        parse_time(interval["end"])
    if has_range and "uncertainty_minutes" in birth:
        raise InputContractError("uncertainty_minutes cannot be combined with time_range")
    if "uncertainty_minutes" in birth:
        strict_int(birth["uncertainty_minutes"], "birth.uncertainty_minutes", 0, 1440)
        if not has_time:
            raise InputContractError("uncertainty_minutes requires birth.time")
    if "fold" in birth and birth["fold"] is not None:
        strict_int(birth["fold"], "birth.fold", 0, 1)
        if not has_time or birth.get("uncertainty_minutes", 0) != 0:
            raise InputContractError("birth.fold may select only one exact repeated local time")
    if "longitude" in birth and birth["longitude"] is not None:
        strict_number(birth["longitude"], "birth.longitude", -180, 180)
    if not isinstance(birth.get("timezone"), str):
        raise InputContractError("birth.timezone must be an IANA timezone string")

    supported_fixed = {
        "year_boundary": "computed_lichun_instant",
        "month_boundary": "computed_jie_instant",
        "term_frame": "absolute_instant",
    }
    for field, expected in supported_fixed.items():
        if field in rules and rules[field] != expected:
            raise InputContractError(f"rules.{field} currently supports only {expected}")
    strict_choice(
        rules.get("time_basis", "civil_clock"),
        "rules.time_basis",
        {"civil_clock", "local_mean_solar", "local_apparent_solar"},
    )
    if "compare_civil_clock" in rules and not isinstance(rules["compare_civil_clock"], bool):
        raise InputContractError("rules.compare_civil_clock must be a JSON boolean")
    strict_choice(
        rules.get("day_boundary", "both"),
        "rules.day_boundary",
        {"both", "zi_initial_next_day", "late_zi_same_day"},
    )
    strict_choice(
        rules.get("child_limit_provider", "default"),
        "rules.child_limit_provider",
        {"default", "china95", "lunar_sect1", "lunar_sect2"},
    )
    if "decade_count" in rules:
        strict_int(rules["decade_count"], "rules.decade_count", 1, 20)
    if "boundary_guard_seconds" in rules:
        strict_int(rules["boundary_guard_seconds"], "rules.boundary_guard_seconds", 1, 3600)

    traditional_sex = payload.get("traditional_sex_for_dayun")
    if traditional_sex is not None:
        strict_choice(
            traditional_sex,
            "traditional_sex_for_dayun",
            {"man", "woman"},
        )
    return birth, rules


def local_iso(value: datetime) -> str:
    naive = value.replace(tzinfo=None)
    return naive.isoformat(timespec="microseconds" if naive.microsecond else "seconds")


def utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_local_datetime(
    naive: datetime, bundle: ZoneBundle, requested_fold: int | None
) -> list[datetime]:
    candidates: dict[tuple[datetime, timedelta | None], datetime] = {}
    for fold in (0, 1):
        aware = naive.replace(tzinfo=bundle.zone, fold=fold)
        candidate_utc = aware.astimezone(UTC)
        round_trip = candidate_utc.astimezone(bundle.zone).replace(tzinfo=None)
        if round_trip == naive:
            candidates.setdefault((candidate_utc, aware.utcoffset()), aware)
    values = sorted(candidates.values(), key=lambda item: item.astimezone(UTC))
    if not values:
        raise InputContractError(
            f"Nonexistent local time in {bundle.zone.key}: {local_iso(naive)} (DST or legal-time gap)"
        )
    if requested_fold is not None:
        if len(values) == 1:
            raise InputContractError("birth.fold was supplied for a non-repeated local time")
        selected = [item for item in values if item.fold == requested_fold]
        if not selected:
            raise InputContractError(f"fold={requested_fold} does not resolve this local time")
        return selected
    return values


def equation_of_time_minutes(value: datetime) -> float:
    """NOAA five-term approximation; deterministic but not a precision ephemeris."""
    days = 366 if value.year % 4 == 0 and (value.year % 100 != 0 or value.year % 400 == 0) else 365
    fraction = (value.hour - 12) / 24 + value.minute / 1440 + value.second / 86400
    gamma = 2 * math.pi / days * (value.timetuple().tm_yday - 1 + fraction)
    return 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )


def solar_basis(
    naive: datetime, aware: datetime, basis: str, longitude: float | None
) -> tuple[datetime, dict[str, Any]]:
    offset = aware.utcoffset()
    if offset is None:
        raise InputContractError("Timezone offset could not be resolved")
    offset_minutes = offset.total_seconds() / 60
    dst = aware.dst() or timedelta(0)
    longitude_minutes = 0.0
    eot_minutes = 0.0
    eot_argument: datetime | None = None
    if basis in {"local_mean_solar", "local_apparent_solar"}:
        if longitude is None:
            raise InputContractError(f"birth.longitude is required for rules.time_basis={basis}")
        standard_meridian = offset_minutes / 4
        longitude_minutes = 4 * (longitude - standard_meridian)
        utc_naive = aware.astimezone(UTC).replace(tzinfo=None)
        corrected = utc_naive + timedelta(minutes=4 * longitude)
    else:
        corrected = naive
    if basis == "local_apparent_solar":
        eot_argument = corrected
        eot_minutes = equation_of_time_minutes(eot_argument)
        corrected += timedelta(minutes=eot_minutes)
    elif basis not in {"civil_clock", "local_mean_solar"}:
        raise InputContractError(f"Unsupported rules.time_basis: {basis}")
    total = longitude_minutes + eot_minutes
    return corrected, {
        "basis": basis,
        "utc_offset_seconds": int(offset.total_seconds()),
        "dst_seconds": int(dst.total_seconds()),
        "longitude_east_deg": longitude,
        "longitude_correction_minutes": round(longitude_minutes, 6),
        "equation_of_time_minutes": round(eot_minutes, 6),
        "total_correction_minutes": round(total, 6),
        "equation_of_time_model": (
            "NOAA_five_term_approximation" if basis == "local_apparent_solar" else None
        ),
        "equation_of_time_argument_local_mean_solar": (
            local_iso(eot_argument) if eot_argument is not None else None
        ),
        "apparent_solar_error_bound_seconds": None,
    }


def closest_clock_boundary_seconds(value: datetime) -> int:
    candidates: list[datetime] = []
    for delta_day in (-1, 0, 1):
        base = datetime.combine(value.date() + timedelta(days=delta_day), time(0, 0))
        for hour in (0, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23):
            candidates.append(base + timedelta(hours=hour))
    return int(min(abs((value - candidate).total_seconds()) for candidate in candidates))


def sample_datetimes(
    birth_date: date, birth: dict[str, Any]
) -> tuple[list[datetime], bool, datetime, datetime]:
    if birth.get("time_range") is not None:
        interval = birth["time_range"]
        if not isinstance(interval, dict) or "start" not in interval or "end" not in interval:
            raise InputContractError("birth.time_range requires start and end")
        start = datetime.combine(birth_date, parse_time(interval["start"]))
        end = datetime.combine(birth_date, parse_time(interval["end"]))
        if end < start:
            end += timedelta(days=1)
        unknown = True
    elif birth.get("time") is not None:
        center = datetime.combine(birth_date, parse_time(birth["time"]))
        uncertainty = birth.get("uncertainty_minutes", 0)
        start = center - timedelta(minutes=uncertainty)
        end = center + timedelta(minutes=uncertainty)
        unknown = uncertainty > 0
    else:
        start = datetime.combine(birth_date, time(0, 0))
        end = datetime.combine(birth_date, time(23, 59, 59))
        unknown = True
    if not (
        SUPPORTED_YEAR_MIN <= start.year <= SUPPORTED_YEAR_MAX
        and SUPPORTED_YEAR_MIN <= end.year <= SUPPORTED_YEAR_MAX
    ):
        raise InputContractError("The resolved time interval crosses outside the supported year range")
    if start == end:
        return [start], unknown, start, end
    samples = {start, end}
    cursor = start.replace(second=0, microsecond=0)
    if cursor < start:
        cursor += timedelta(minutes=1)
    minute_remainder = cursor.minute % 30
    if minute_remainder:
        cursor += timedelta(minutes=30 - minute_remainder)
    while cursor < end:
        samples.add(cursor)
        cursor += timedelta(minutes=30)
    return sorted(samples), unknown, start, end


def offset_at_utc(value: datetime, bundle: ZoneBundle) -> timedelta:
    offset = value.astimezone(bundle.zone).utcoffset()
    if offset is None:
        raise InputContractError("Timezone offset could not be resolved")
    return offset


def timezone_transition_samples(
    start: datetime, end: datetime, bundle: ZoneBundle
) -> list[datetime]:
    """Return local wall times around every offset transition near an input interval."""
    scan_start = (start - timedelta(days=2)).replace(tzinfo=UTC)
    scan_end = (end + timedelta(days=2)).replace(tzinfo=UTC)
    step = timedelta(hours=1)
    cursor = scan_start
    previous_offset = offset_at_utc(cursor, bundle)
    samples: set[datetime] = set()
    while cursor < scan_end:
        right = min(cursor + step, scan_end)
        right_offset = offset_at_utc(right, bundle)
        if right_offset != previous_offset:
            low = cursor
            high = right
            while (high - low).total_seconds() > 1:
                seconds = int((high - low).total_seconds()) // 2
                middle = low + timedelta(seconds=max(seconds, 1))
                if offset_at_utc(middle, bundle) == previous_offset:
                    low = middle
                else:
                    high = middle
            transition = high.replace(microsecond=0)
            before_local = (transition - timedelta(seconds=1)).astimezone(bundle.zone).replace(tzinfo=None)
            after_local = transition.astimezone(bundle.zone).replace(tzinfo=None)
            for candidate in (before_local, after_local):
                if start <= candidate <= end:
                    samples.add(candidate)
            if after_local <= before_local:
                overlap_start = after_local
                overlap_end = before_local + timedelta(seconds=1)
                midpoint = overlap_start + timedelta(
                    seconds=int((overlap_end - overlap_start).total_seconds()) // 2
                )
                for candidate in (overlap_start, midpoint, overlap_end - timedelta(seconds=1)):
                    if start <= candidate <= end:
                        samples.add(candidate)
            previous_offset = right_offset
        cursor = right
    return sorted(samples)


def strict_core_json_loads(text: str, context: str) -> Any:
    """Decode an untrusted child response without duplicate keys or JSON extensions."""

    def reject_constant(value: str) -> None:
        raise RuntimeError(f"{context} contains a non-standard JSON number: {value}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeError(f"{context} contains duplicate object key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except RuntimeError:
        raise
    except (json.JSONDecodeError, RecursionError, TypeError) as exc:
        raise RuntimeError(f"{context} is not one strict JSON document") from exc


def core_contract_error(path: str) -> RuntimeError:
    return RuntimeError(f"Calendrical core response contract violation at {path}")


def require_core_keys(
    value: dict[str, Any], expected: set[str] | frozenset[str], path: str
) -> None:
    """Require an exact v0.2 object shape, including all nullable fields."""
    actual = set(value)
    if actual != set(expected):
        raise core_contract_error(path)


def require_core_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise core_contract_error(path)
    return value


def require_core_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise core_contract_error(path)
    return value


def require_core_string(value: Any, path: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise core_contract_error(path)
    return value


def require_core_int(
    value: Any, path: str, minimum: int = 0, maximum: int = 3600
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise core_contract_error(path)
    return value


def require_core_number(
    value: Any, path: str, minimum: float = 0, maximum: float = 86400
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise core_contract_error(path)
    try:
        parsed = float(value)
    except (OverflowError, ValueError) as exc:
        raise core_contract_error(path) from exc
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise core_contract_error(path)
    return parsed


def require_core_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise core_contract_error(path)
    return value


def parse_core_utc(value: Any, path: str) -> datetime:
    rendered = require_core_string(value, path, maximum=40)
    if not rendered.endswith("Z"):
        raise core_contract_error(path)
    try:
        parsed = datetime.fromisoformat(rendered[:-1] + "+00:00")
    except ValueError as exc:
        raise core_contract_error(path) from exc
    if parsed.tzinfo != UTC:
        raise core_contract_error(path)
    return parsed


def parse_core_local(value: Any, path: str) -> datetime:
    rendered = require_core_string(value, path, maximum=40)
    try:
        parsed = datetime.fromisoformat(rendered)
    except ValueError as exc:
        raise core_contract_error(path) from exc
    if parsed.tzinfo is not None:
        raise core_contract_error(path)
    return parsed


def validate_core_date_parts(value: Any, path: str) -> date:
    parts = require_core_dict(value, path)
    require_core_keys(parts, {"year", "month", "day"}, path)
    year = require_core_int(parts.get("year"), f"{path}.year", 1800, 2200)
    month = require_core_int(parts.get("month"), f"{path}.month", 1, 12)
    day = require_core_int(parts.get("day"), f"{path}.day", 1, 31)
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise core_contract_error(path) from exc


def ganzhi_cycle() -> tuple[str, ...]:
    return tuple(STEMS[index % 10] + BRANCHES[index % 12] for index in range(60))


GANZHI_CYCLE = ganzhi_cycle()
GANZHI_INDEX = {value: index for index, value in enumerate(GANZHI_CYCLE)}


def validate_ganzhi(value: Any, path: str) -> str:
    rendered = require_core_string(value, path, maximum=2)
    if rendered not in GANZHI_INDEX:
        raise core_contract_error(path)
    return rendered


def year_ganzhi(year: int) -> str:
    return GANZHI_CYCLE[(year - 4) % 60]


def ten_god(day_stem: str, target_stem: str) -> str:
    day_index = STEMS.index(day_stem)
    target_index = STEMS.index(target_stem)
    day_element = STEM_ELEMENT_INDEX[day_index]
    target_element = STEM_ELEMENT_INDEX[target_index]
    same_polarity = day_index % 2 == target_index % 2
    if day_element == target_element:
        return "比肩" if same_polarity else "劫财"
    if ELEMENT_GENERATES[day_element] == target_element:
        return "食神" if same_polarity else "伤官"
    if ELEMENT_GENERATES[target_element] == day_element:
        return "偏印" if same_polarity else "正印"
    if ELEMENT_CONTROLS[day_element] == target_element:
        return "偏财" if same_polarity else "正财"
    if ELEMENT_CONTROLS[target_element] == day_element:
        return "七杀" if same_polarity else "正官"
    raise RuntimeError("Unreachable Five-Element relationship")


def terrain_for(day_stem: str, branch: str) -> str:
    stem_index = STEMS.index(day_stem)
    branch_index = BRANCHES.index(branch)
    start = TERRAIN_START[stem_index]
    phase = (
        (branch_index - start) % 12
        if stem_index % 2 == 0
        else (start - branch_index) % 12
    )
    return TERRAIN_SEQUENCE[phase]


def validate_hko_divergence(value: Any, path: str) -> dict[str, Any]:
    divergence = require_core_dict(value, path)
    require_core_keys(
        divergence,
        {
            "code",
            "source_locator",
            "nominal_month_start_beijing_date",
            "historical_oracle_month_start_date",
        },
        path,
    )
    if divergence.get("code") != "HISTORICAL_CALENDAR_AUTHORITY_DIVERGENCE":
        raise core_contract_error(f"{path}.code")
    for field in (
        "source_locator",
        "nominal_month_start_beijing_date",
        "historical_oracle_month_start_date",
    ):
        rendered = require_core_string(
            divergence.get(field), f"{path}.{field}", maximum=512
        )
        if field.endswith("_date"):
            try:
                date.fromisoformat(rendered)
            except ValueError as exc:
                raise core_contract_error(f"{path}.{field}") from exc
    return divergence


def validate_term_evidence(
    value: Any,
    path: str,
    *,
    solar_boundary_event: bool = False,
) -> dict[str, Any]:
    term = require_core_dict(value, path)
    keys = {
        "name",
        "kind",
        "beijing_time",
        "utc",
        "time_scale",
        "model_guard_seconds",
        "delta_t_source_code",
        "historical_oracle_date_divergence",
    }
    if solar_boundary_event:
        keys |= {"absolute_distance_seconds", "changes_calendar_assignment"}
    require_core_keys(term, keys, path)
    name = require_core_string(term.get("name"), f"{path}.name", maximum=32)
    if name not in TERM_KIND_BY_NAME:
        raise core_contract_error(f"{path}.name")
    if term.get("kind") != TERM_KIND_BY_NAME[name]:
        raise core_contract_error(f"{path}.kind")
    beijing = parse_core_local(
        term.get("beijing_time"), f"{path}.beijing_time"
    )
    utc_value = parse_core_utc(term.get("utc"), f"{path}.utc")
    if utc_value.astimezone(UTC).replace(tzinfo=None) + timedelta(hours=8) != beijing:
        raise core_contract_error(f"{path}.beijing_time")
    if term.get("time_scale") != CORE_EVENT_TIME_SCALE:
        raise core_contract_error(f"{path}.time_scale")
    source = require_core_string(
        term.get("delta_t_source_code"),
        f"{path}.delta_t_source_code",
        maximum=64,
    )
    if source not in DELTA_T_SOURCE_CODES:
        raise core_contract_error(f"{path}.delta_t_source_code")
    require_core_int(
        term.get("model_guard_seconds"), f"{path}.model_guard_seconds", 1, 3600
    )
    historical = term.get("historical_oracle_date_divergence")
    if historical is not None:
        historical = require_core_dict(
            historical, f"{path}.historical_oracle_date_divergence"
        )
        require_core_keys(
            historical,
            {
                "term",
                "kind",
                "year",
                "computed_beijing_date",
                "historical_oracle_date",
                "code",
                "source_locator",
            },
            f"{path}.historical_oracle_date_divergence",
        )
        for field in (
            "term",
            "kind",
            "computed_beijing_date",
            "historical_oracle_date",
            "code",
            "source_locator",
        ):
            require_core_string(
                historical.get(field),
                f"{path}.historical_oracle_date_divergence.{field}",
                maximum=512,
            )
        if (
            historical["code"] != "HISTORICAL_SOLAR_TERM_DATE_DIVERGENCE"
            or historical["term"] != name
            or historical["kind"] != term["kind"]
            or historical["computed_beijing_date"] != beijing.date().isoformat()
        ):
            raise core_contract_error(f"{path}.historical_oracle_date_divergence")
        year = require_core_int(
            historical.get("year"),
            f"{path}.historical_oracle_date_divergence.year",
            1900,
            2034,
        )
        if year != beijing.year:
            raise core_contract_error(
                f"{path}.historical_oracle_date_divergence.year"
            )
        for field in ("computed_beijing_date", "historical_oracle_date"):
            try:
                date.fromisoformat(historical[field])
            except ValueError as exc:
                raise core_contract_error(
                    f"{path}.historical_oracle_date_divergence.{field}"
                ) from exc
    if solar_boundary_event:
        if term.get("changes_calendar_assignment") is not True:
            raise core_contract_error(f"{path}.changes_calendar_assignment")
        distance = require_core_number(
            term.get("absolute_distance_seconds"),
            f"{path}.absolute_distance_seconds",
            0,
            86400,
        )
        if distance > term["model_guard_seconds"] + 1e-6:
            raise core_contract_error(f"{path}.absolute_distance_seconds")
    return term


def validate_boundary_uncertainty(value: Any, path: str) -> dict[str, Any]:
    """Validate the calendar-boundary evidence contract in core response v0.2.

      boundary_uncertainty = {
        status, codes[], affects_this_nominal_date,
        reverse_conversion_blocked,
        unresolved_result_change_without_enumerated_variant,
        near_midnight_review_seconds, start_model_guard_seconds,
        start_delta_t_source_code, start_time_scale, events[],
        hko_authority_divergences[]
      }

    Each event minimally carries event, utc, term, midnight_margin_seconds,
    model_guard_seconds, delta_t_source_code, changes_calendar_assignment, and
    alternative_beijing_day_delta. Guards are evidence bands, not probability.
    """
    review = require_core_dict(value, path)
    require_core_keys(
        review,
        {
            "status",
            "codes",
            "affects_this_nominal_date",
            "reverse_conversion_blocked",
            "unresolved_result_change_without_enumerated_variant",
            "near_midnight_review_seconds",
            "nominal_beijing_date",
            "nominal_month_start_beijing_date",
            "start_model_guard_seconds",
            "start_delta_t_source_code",
            "start_time_scale",
            "events",
            "hko_authority_divergences",
        },
        path,
    )
    status = require_core_string(review.get("status"), f"{path}.status", maximum=80)
    if status not in LUNAR_BOUNDARY_STATUSES:
        raise core_contract_error(f"{path}.status")
    codes = require_core_list(review.get("codes"), f"{path}.codes")
    if len(codes) > 32:
        raise core_contract_error(f"{path}.codes")
    for index, code in enumerate(codes):
        require_core_string(code, f"{path}.codes[{index}]", maximum=80)
    flags: dict[str, bool] = {}
    for field in (
        "affects_this_nominal_date",
        "reverse_conversion_blocked",
        "unresolved_result_change_without_enumerated_variant",
    ):
        flags[field] = require_core_bool(review.get(field), f"{path}.{field}")
    require_core_int(
        review.get("near_midnight_review_seconds"),
        f"{path}.near_midnight_review_seconds",
        600,
        600,
    )
    nominal_date = validate_core_date_parts(
        review.get("nominal_beijing_date"), f"{path}.nominal_beijing_date"
    )
    month_start = validate_core_date_parts(
        review.get("nominal_month_start_beijing_date"),
        f"{path}.nominal_month_start_beijing_date",
    )
    if not 0 <= (nominal_date - month_start).days <= 29:
        raise core_contract_error(f"{path}.nominal_beijing_date")
    require_core_int(
        review.get("start_model_guard_seconds"),
        f"{path}.start_model_guard_seconds",
        1,
        3600,
    )
    start_source = require_core_string(
        review.get("start_delta_t_source_code"),
        f"{path}.start_delta_t_source_code",
        maximum=64,
    )
    if start_source not in DELTA_T_SOURCE_CODES:
        raise core_contract_error(f"{path}.start_delta_t_source_code")
    if review.get("start_time_scale") != CORE_EVENT_TIME_SCALE:
        raise core_contract_error(f"{path}.start_time_scale")
    events = require_core_list(review.get("events"), f"{path}.events")
    if len(events) > 32:
        raise core_contract_error(f"{path}.events")
    for index, raw_event in enumerate(events):
        event_path = f"{path}.events[{index}]"
        event = require_core_dict(raw_event, event_path)
        require_core_keys(
            event,
            {
                "event",
                "utc",
                "time_scale",
                "term",
                "midnight_margin_seconds",
                "model_guard_seconds",
                "delta_t_source_code",
                "changes_calendar_assignment",
                "alternative_beijing_day_delta",
            },
            event_path,
        )
        event_name = require_core_string(
            event.get("event"), f"{event_path}.event", maximum=80
        )
        if event_name not in LUNAR_EVENT_NAMES:
            raise core_contract_error(f"{event_path}.event")
        parse_core_utc(event.get("utc"), f"{event_path}.utc")
        if event.get("time_scale") != CORE_EVENT_TIME_SCALE:
            raise core_contract_error(f"{event_path}.time_scale")
        term_name = event.get("term")
        major_event = event_name.startswith("major_term_")
        if major_event:
            if term_name not in TERM_KIND_BY_NAME or TERM_KIND_BY_NAME[term_name] != "qi":
                raise core_contract_error(f"{event_path}.term")
        elif term_name is not None:
            raise core_contract_error(f"{event_path}.term")
        require_core_number(
            event.get("midnight_margin_seconds"),
            f"{event_path}.midnight_margin_seconds",
        )
        require_core_int(
            event.get("model_guard_seconds"),
            f"{event_path}.model_guard_seconds",
            1,
            3600,
        )
        source = require_core_string(
            event.get("delta_t_source_code"),
            f"{event_path}.delta_t_source_code",
            maximum=64,
        )
        if source not in DELTA_T_SOURCE_CODES:
            raise core_contract_error(f"{event_path}.delta_t_source_code")
        require_core_bool(
            event.get("changes_calendar_assignment"),
            f"{event_path}.changes_calendar_assignment",
        )
        require_core_int(
            event.get("alternative_beijing_day_delta"),
            f"{event_path}.alternative_beijing_day_delta",
            minimum=-1,
            maximum=1,
        )
    divergences = require_core_list(
        review.get("hko_authority_divergences"),
        f"{path}.hko_authority_divergences",
    )
    if len(divergences) > 16:
        raise core_contract_error(f"{path}.hko_authority_divergences")
    for index, divergence in enumerate(divergences):
        validate_hko_divergence(
            divergence, f"{path}.hko_authority_divergences[{index}]"
        )

    has_hko = bool(divergences)
    has_model_change = any(event["changes_calendar_assignment"] for event in events)
    has_review_only = any(not event["changes_calendar_assignment"] for event in events)
    expected_blocked = has_hko or has_model_change
    if any(flag != expected_blocked for flag in flags.values()):
        raise core_contract_error(path)
    expected_codes: list[str] = []
    if has_hko:
        expected_codes.append("HISTORICAL_CALENDAR_AUTHORITY_DIVERGENCE")
    if has_model_change:
        expected_codes.append("LUNAR_BOUNDARY_MODEL_GUARD")
    if has_review_only and not has_model_change:
        expected_codes.append("NEAR_MIDNIGHT_REVIEW")
    if codes != expected_codes:
        raise core_contract_error(f"{path}.codes")
    if has_hko and has_model_change:
        expected_status = "MULTIPLE_BOUNDARY_UNCERTAINTIES"
    elif has_hko:
        expected_status = "HISTORICAL_CONVENTION_DIVERGENCE"
    elif has_model_change:
        expected_status = "MODEL_GUARD_CROSSES_BEIJING_MIDNIGHT"
    elif has_review_only:
        expected_status = "REVIEW_ONLY"
    else:
        expected_status = "CLEAR"
    if status != expected_status:
        raise core_contract_error(f"{path}.status")
    return review


def calendar_boundary_unresolved(message: str) -> None:
    raise InputContractError(message, code="CALENDAR_BOUNDARY_UNRESOLVED")


def validate_calendar_model_variant(value: Any, path: str) -> dict[str, Any] | None:
    if value is None:
        return None
    variant = require_core_dict(value, path)
    require_core_keys(
        variant,
        {"variant_id", "state", "classification_rule", "boundary_term"},
        path,
    )
    require_core_string(variant.get("variant_id"), f"{path}.variant_id", maximum=256)
    state = variant.get("state")
    if state not in {"birth_before_term", "birth_after_term"}:
        raise core_contract_error(f"{path}.state")
    expected_rule = (
        "year_and_month_classified_immediately_before_the_guarded_Jie"
        if state == "birth_before_term"
        else "year_and_month_classified_immediately_after_the_guarded_Jie"
    )
    if variant.get("classification_rule") != expected_rule:
        raise core_contract_error(f"{path}.classification_rule")
    boundary = validate_term_evidence(
        variant.get("boundary_term"), f"{path}.boundary_term"
    )
    if boundary["kind"] != "jie":
        raise core_contract_error(f"{path}.boundary_term.kind")
    return variant


def validate_solar_term_boundary_uncertainty(
    value: Any, path: str
) -> dict[str, Any]:
    review = require_core_dict(value, path)
    require_core_keys(
        review,
        {
            "status",
            "codes",
            "affects_year_pillar",
            "affects_month_pillar",
            "unresolved_result_change_without_enumerated_variant",
            "per_event_model_guard_is_certified_error_bound",
            "enumerated_variant_count",
            "calendar_model_variant_state",
            "events",
        },
        path,
    )
    status = require_core_string(review.get("status"), f"{path}.status", maximum=80)
    codes = require_core_list(review.get("codes"), f"{path}.codes")
    if len(codes) > 8:
        raise core_contract_error(f"{path}.codes")
    for index, code in enumerate(codes):
        require_core_string(code, f"{path}.codes[{index}]", maximum=80)
    for field in (
        "affects_year_pillar",
        "affects_month_pillar",
        "unresolved_result_change_without_enumerated_variant",
        "per_event_model_guard_is_certified_error_bound",
    ):
        if not isinstance(review.get(field), bool):
            raise core_contract_error(f"{path}.{field}")
    if review["per_event_model_guard_is_certified_error_bound"]:
        raise core_contract_error(
            f"{path}.per_event_model_guard_is_certified_error_bound"
        )
    variant_count = require_core_int(
        review.get("enumerated_variant_count"),
        f"{path}.enumerated_variant_count",
        minimum=1,
        maximum=MAX_CORE_VARIANTS_PER_SOURCE_CASE,
    )
    state = review.get("calendar_model_variant_state")
    if state is not None and state not in {"birth_before_term", "birth_after_term"}:
        raise core_contract_error(f"{path}.calendar_model_variant_state")
    events = require_core_list(review.get("events"), f"{path}.events")
    if len(events) > 4:
        raise core_contract_error(f"{path}.events")
    for index, raw_event in enumerate(events):
        event_path = f"{path}.events[{index}]"
        event = validate_term_evidence(
            raw_event, event_path, solar_boundary_event=True
        )
        if event["kind"] != "jie":
            raise core_contract_error(f"{event_path}.kind")

    affects_pillar = review["affects_year_pillar"] or review["affects_month_pillar"]
    if review["unresolved_result_change_without_enumerated_variant"]:
        calendar_boundary_unresolved(
            "The solar-term model guard can change a pillar, but the core "
            "reported that its consequences were not enumerated"
        )
    if status == "CLEAR":
        if (
            codes
            or affects_pillar
            or variant_count != 1
            or state is not None
            or events
        ):
            raise core_contract_error(path)
        return review
    if status == "ENUMERATED_CALENDAR_MODEL_VARIANTS":
        if (
            codes != ["SOLAR_TERM_BOUNDARY_MODEL_GUARD"]
            or not review["affects_month_pillar"]
            or variant_count != 2
            or state not in {"birth_before_term", "birth_after_term"}
            or len(events) != 1
        ):
            calendar_boundary_unresolved(
                "The solar-term boundary response did not contain the complete "
                "two-variant before/after enumeration"
            )
        if review["affects_year_pillar"] != (events[0]["name"] == "立春"):
            raise core_contract_error(f"{path}.affects_year_pillar")
        return review
    if affects_pillar:
        calendar_boundary_unresolved(
            "The solar-term boundary claims a pillar consequence without a "
            "recognized exhaustive variant status"
        )
    raise core_contract_error(f"{path}.status")


def validate_chart(value: Any, path: str) -> dict[str, Any]:
    chart = require_core_dict(value, path)
    require_core_keys(
        chart,
        {
            "ganzhi",
            "ganzhi_evidence_layer",
            "derived_field_evidence_layer",
            "year",
            "month",
            "day",
            "hour",
        },
        path,
    )
    if chart.get("ganzhi_evidence_layer") != "L1B_VERSIONED_CALENDAR":
        raise core_contract_error(f"{path}.ganzhi_evidence_layer")
    if chart.get("derived_field_evidence_layer") != "L1C_VERSIONED_TRADITIONAL_MAP":
        raise core_contract_error(f"{path}.derived_field_evidence_layer")
    rendered_pillars: list[str] = []
    for position in ("year", "month", "day", "hour"):
        pillar_path = f"{path}.{position}"
        pillar = require_core_dict(chart.get(position), pillar_path)
        require_core_keys(
            pillar,
            {
                "position",
                "ganzhi",
                "ganzhi_evidence_layer",
                "attribute_evidence_layer",
                "stem",
                "branch",
                "terrain",
                "nayin",
            },
            pillar_path,
        )
        if pillar.get("position") != position:
            raise core_contract_error(f"{pillar_path}.position")
        if pillar.get("ganzhi_evidence_layer") != "L1B_VERSIONED_CALENDAR":
            raise core_contract_error(f"{pillar_path}.ganzhi_evidence_layer")
        if pillar.get("attribute_evidence_layer") != "L1C_VERSIONED_TRADITIONAL_MAP":
            raise core_contract_error(f"{pillar_path}.attribute_evidence_layer")
        ganzhi_name = validate_ganzhi(pillar.get("ganzhi"), f"{pillar_path}.ganzhi")
        rendered_pillars.append(ganzhi_name)

        stem = require_core_dict(pillar.get("stem"), f"{pillar_path}.stem")
        require_core_keys(stem, {"name", "element", "yin_yang", "ten_god"}, f"{pillar_path}.stem")
        stem_name = stem.get("name")
        if stem_name != ganzhi_name[0] or stem_name not in STEMS:
            raise core_contract_error(f"{pillar_path}.stem.name")
        stem_index = STEMS.index(stem_name)
        if stem.get("element") != STEM_ELEMENT[stem_name]:
            raise core_contract_error(f"{pillar_path}.stem.element")
        if stem.get("yin_yang") != YIN_YANG[stem_index % 2]:
            raise core_contract_error(f"{pillar_path}.stem.yin_yang")
        if stem.get("ten_god") not in TEN_GODS:
            raise core_contract_error(f"{pillar_path}.stem.ten_god")
        if (position == "day") != (stem.get("ten_god") == "日主"):
            raise core_contract_error(f"{pillar_path}.stem.ten_god")

        branch = require_core_dict(pillar.get("branch"), f"{pillar_path}.branch")
        require_core_keys(
            branch,
            {"name", "element", "yin_yang", "hidden_stems"},
            f"{pillar_path}.branch",
        )
        branch_name = branch.get("name")
        if branch_name != ganzhi_name[1] or branch_name not in BRANCHES:
            raise core_contract_error(f"{pillar_path}.branch.name")
        branch_index = BRANCHES.index(branch_name)
        if branch.get("element") != BRANCH_ELEMENT[branch_name]:
            raise core_contract_error(f"{pillar_path}.branch.element")
        if branch.get("yin_yang") != YIN_YANG[branch_index % 2]:
            raise core_contract_error(f"{pillar_path}.branch.yin_yang")
        hidden = require_core_list(
            branch.get("hidden_stems"), f"{pillar_path}.branch.hidden_stems"
        )
        if not 1 <= len(hidden) <= 3:
            raise core_contract_error(f"{pillar_path}.branch.hidden_stems")
        hidden_names: set[str] = set()
        hidden_roles: set[str] = set()
        for index, raw_hidden in enumerate(hidden):
            hidden_path = f"{pillar_path}.branch.hidden_stems[{index}]"
            item = require_core_dict(raw_hidden, hidden_path)
            require_core_keys(item, {"name", "role", "ten_god"}, hidden_path)
            name = item.get("name")
            role = item.get("role")
            if name not in STEMS or name in hidden_names:
                raise core_contract_error(f"{hidden_path}.name")
            if role not in HIDDEN_STEM_ROLES or role in hidden_roles:
                raise core_contract_error(f"{hidden_path}.role")
            if item.get("ten_god") not in TEN_GODS - {"日主"}:
                raise core_contract_error(f"{hidden_path}.ten_god")
            hidden_names.add(name)
            hidden_roles.add(role)
        if pillar.get("terrain") not in TERRAINS:
            raise core_contract_error(f"{pillar_path}.terrain")
        require_core_string(pillar.get("nayin"), f"{pillar_path}.nayin", maximum=16)

    expected_chart_name = " ".join(rendered_pillars)
    if chart.get("ganzhi") != expected_chart_name:
        raise core_contract_error(f"{path}.ganzhi")
    day_stem = rendered_pillars[2][0]
    for position, ganzhi_name in zip(
        ("year", "month", "day", "hour"), rendered_pillars
    ):
        pillar_path = f"{path}.{position}"
        pillar = chart[position]
        expected_ten_god = (
            "日主" if position == "day" else ten_god(day_stem, ganzhi_name[0])
        )
        if pillar["stem"]["ten_god"] != expected_ten_god:
            raise core_contract_error(f"{pillar_path}.stem.ten_god")
        branch_index = BRANCHES.index(ganzhi_name[1])
        expected_hidden = HIDDEN_STEMS[branch_index]
        actual_hidden = pillar["branch"]["hidden_stems"]
        if len(actual_hidden) != len(expected_hidden):
            raise core_contract_error(f"{pillar_path}.branch.hidden_stems")
        for index, ((expected_name, expected_role), actual) in enumerate(
            zip(expected_hidden, actual_hidden)
        ):
            if (
                actual["name"] != expected_name
                or actual["role"] != expected_role
                or actual["ten_god"] != ten_god(day_stem, expected_name)
            ):
                raise core_contract_error(
                    f"{pillar_path}.branch.hidden_stems[{index}]"
                )
        if pillar["terrain"] != terrain_for(day_stem, ganzhi_name[1]):
            raise core_contract_error(f"{pillar_path}.terrain")
        if pillar["nayin"] != NAYIN[GANZHI_INDEX[ganzhi_name] // 2]:
            raise core_contract_error(f"{pillar_path}.nayin")
    return chart


def validate_conventions(
    value: Any, expected_case: dict[str, Any], path: str
) -> dict[str, Any]:
    conventions = require_core_dict(value, path)
    require_core_keys(
        conventions,
        {
            "term_frame",
            "calendar_day_frame",
            "day_hour_time_basis",
            "day_boundary",
            "zi_policy",
            "solar_review_offset_seconds",
            "scenario_kind",
        },
        path,
    )
    expected_values = {
        "term_frame": CORE_TERM_FRAME,
        "calendar_day_frame": CORE_CALENDAR_DAY_FRAME,
        "day_hour_time_basis": expected_case.get("time_basis"),
        "day_boundary": expected_case.get("day_boundary"),
        "solar_review_offset_seconds": expected_case.get(
            "solar_review_offset_seconds", 0
        ),
        "scenario_kind": expected_case.get("scenario_kind", "input_candidate"),
    }
    for field, expected in expected_values.items():
        if conventions.get(field) != expected:
            raise core_contract_error(f"{path}.{field}")
    zi = require_core_dict(conventions.get("zi_policy"), f"{path}.zi_policy")
    require_core_keys(
        zi,
        {"provider", "zi_day_rollover", "zi_hour_stem_basis"},
        f"{path}.zi_policy",
    )
    if conventions["day_boundary"] == "zi_initial_next_day":
        expected_zi = {
            "provider": "xuanshu.IndependentZiInitialNextDay",
            "zi_day_rollover": "23:00_begins_next_day_pillar",
            "zi_hour_stem_basis": "day_pillar_after_23:00_rollover",
        }
    else:
        expected_zi = {
            "provider": "xuanshu.IndependentLateZiSameDay",
            "zi_day_rollover": "00:00_begins_next_day_pillar",
            "zi_hour_stem_basis": "23:00_hour_stem_uses_next_civil_day_stem",
        }
    if zi != expected_zi:
        raise core_contract_error(f"{path}.zi_policy")
    return conventions


def validate_lunar_date(
    value: Any, beijing_time: datetime, path: str
) -> dict[str, Any]:
    lunar = require_core_dict(value, path)
    require_core_keys(
        lunar,
        {"year", "month", "day", "leap_month", "display", "boundary_uncertainty"},
        path,
    )
    lunar_year = require_core_int(lunar.get("year"), f"{path}.year", 1900, 2034)
    lunar_month = require_core_int(lunar.get("month"), f"{path}.month", 1, 12)
    lunar_day = require_core_int(lunar.get("day"), f"{path}.day", 1, 30)
    leap_month = require_core_bool(lunar.get("leap_month"), f"{path}.leap_month")
    require_core_string(lunar.get("display"), f"{path}.display", maximum=64)
    expected_display = (
        f"农历{year_ganzhi(lunar_year)}年"
        f"{'闰' if leap_month else ''}{LUNAR_MONTH_NAMES[lunar_month - 1]}"
        f"{LUNAR_DAY_NAMES[lunar_day - 1]}"
    )
    if lunar["display"] != expected_display:
        raise core_contract_error(f"{path}.display")
    review = validate_boundary_uncertainty(
        lunar.get("boundary_uncertainty"), f"{path}.boundary_uncertainty"
    )
    nominal = validate_core_date_parts(
        review["nominal_beijing_date"],
        f"{path}.boundary_uncertainty.nominal_beijing_date",
    )
    start = validate_core_date_parts(
        review["nominal_month_start_beijing_date"],
        f"{path}.boundary_uncertainty.nominal_month_start_beijing_date",
    )
    if nominal != beijing_time.date() or (nominal - start).days + 1 != lunar_day:
        raise core_contract_error(path)
    return lunar


def add_symbolic_interval(birth: datetime, interval: dict[str, int]) -> datetime:
    minute = birth.minute + interval["minutes"]
    hour = birth.hour + interval["hours"] + minute // 60
    minute %= 60
    day_value = birth.day + interval["days"] + hour // 24
    hour %= 24
    month_index = (
        (birth.year + interval["years"]) * 12
        + birth.month
        - 1
        + interval["months"]
    )
    year = month_index // 12
    month = month_index % 12 + 1
    while True:
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        month_length = (next_month - date(year, month, 1)).days
        if day_value <= month_length:
            break
        day_value -= month_length
        month_index += 1
        year = month_index // 12
        month = month_index % 12 + 1
    return datetime(year, month, day_value, hour, minute, birth.second)


def validate_dayun(
    value: Any,
    request: dict[str, Any],
    chart: dict[str, Any],
    normalized_times: dict[str, Any],
    variant: dict[str, Any] | None,
    path: str,
) -> dict[str, Any] | None:
    gender = request.get("gender")
    if gender is None:
        if value is not None:
            raise core_contract_error(path)
        return None
    if value is None:
        raise core_contract_error(path)
    dayun = require_core_dict(value, path)
    require_core_keys(
        dayun,
        {
            "gender_parameter",
            "direction",
            "provider",
            "age_convention",
            "interval",
            "selected_jie",
            "symbolic_start_beijing_time_under_provider",
            "symbolic_start_utc_under_provider",
            "decades",
        },
        path,
    )
    if dayun.get("gender_parameter") != gender:
        raise core_contract_error(f"{path}.gender_parameter")
    if dayun.get("provider") != request.get("child_limit_provider"):
        raise core_contract_error(f"{path}.provider")
    if dayun.get("age_convention") != "provider_traditional_nominal_age":
        raise core_contract_error(f"{path}.age_convention")
    year_stem = chart["year"]["ganzhi"][0]
    yang_year = STEMS.index(year_stem) % 2 == 0
    expected_direction = (
        "forward"
        if (yang_year and gender == "man") or (not yang_year and gender == "woman")
        else "backward"
    )
    if dayun.get("direction") != expected_direction:
        raise core_contract_error(f"{path}.direction")

    interval = require_core_dict(dayun.get("interval"), f"{path}.interval")
    require_core_keys(
        interval, {"years", "months", "days", "hours", "minutes"}, f"{path}.interval"
    )
    limits = {
        "years": (0, 20),
        "months": (0, 11),
        "days": (0, 29),
        "hours": (0, 23),
        "minutes": (0, 59),
    }
    for field, (minimum, maximum) in limits.items():
        require_core_int(
            interval.get(field), f"{path}.interval.{field}", minimum, maximum
        )

    selected = validate_term_evidence(dayun.get("selected_jie"), f"{path}.selected_jie")
    if selected["kind"] != "jie":
        raise core_contract_error(f"{path}.selected_jie.kind")
    selected_utc = parse_core_utc(selected["utc"], f"{path}.selected_jie.utc")
    if variant is None:
        classified_instant = parse_core_utc(
            normalized_times["absolute_utc"], f"{path}.classified_instant"
        )
    else:
        boundary_utc = parse_core_utc(
            variant["boundary_term"]["utc"], f"{path}.classified_boundary"
        )
        classified_instant = boundary_utc + timedelta(
            microseconds=-1 if variant["state"] == "birth_before_term" else 1
        )
    if expected_direction == "forward":
        if not selected_utc > classified_instant:
            raise core_contract_error(f"{path}.selected_jie")
    elif selected_utc > classified_instant:
        raise core_contract_error(f"{path}.selected_jie")

    symbolic_beijing = parse_core_local(
        dayun.get("symbolic_start_beijing_time_under_provider"),
        f"{path}.symbolic_start_beijing_time_under_provider",
    )
    symbolic_utc = parse_core_utc(
        dayun.get("symbolic_start_utc_under_provider"),
        f"{path}.symbolic_start_utc_under_provider",
    )
    if symbolic_utc.replace(tzinfo=None) + timedelta(hours=8) != symbolic_beijing:
        raise core_contract_error(f"{path}.symbolic_start_utc_under_provider")
    birth_beijing = parse_core_local(
        normalized_times["beijing_calendar_frame"], f"{path}.birth_beijing"
    )
    if add_symbolic_interval(birth_beijing, interval) != symbolic_beijing:
        raise core_contract_error(f"{path}.symbolic_start_beijing_time_under_provider")

    decades = require_core_list(dayun.get("decades"), f"{path}.decades")
    decade_count = request.get("decade_count")
    if len(decades) != decade_count:
        raise core_contract_error(f"{path}.decades")
    month_index = GANZHI_INDEX[chart["month"]["ganzhi"]]
    step = 1 if expected_direction == "forward" else -1
    first_age = symbolic_beijing.year - birth_beijing.year + 1
    for index, raw_decade in enumerate(decades, start=1):
        decade_path = f"{path}.decades[{index - 1}]"
        decade = require_core_dict(raw_decade, decade_path)
        require_core_keys(
            decade,
            {
                "index",
                "ganzhi",
                "start_age",
                "end_age",
                "start_year",
                "start_year_ganzhi",
                "end_year",
                "end_year_ganzhi",
            },
            decade_path,
        )
        if require_core_int(decade.get("index"), f"{decade_path}.index", 1, 20) != index:
            raise core_contract_error(f"{decade_path}.index")
        if validate_ganzhi(decade.get("ganzhi"), f"{decade_path}.ganzhi") != GANZHI_CYCLE[(month_index + step * index) % 60]:
            raise core_contract_error(f"{decade_path}.ganzhi")
        start_age = require_core_int(decade.get("start_age"), f"{decade_path}.start_age", 1, 300)
        end_age = require_core_int(decade.get("end_age"), f"{decade_path}.end_age", 1, 309)
        start_year = require_core_int(decade.get("start_year"), f"{decade_path}.start_year", 1800, 2400)
        end_year = require_core_int(decade.get("end_year"), f"{decade_path}.end_year", 1800, 2409)
        if (
            start_age != first_age + (index - 1) * 10
            or end_age != start_age + 9
            or start_year != symbolic_beijing.year + (index - 1) * 10
            or end_year != start_year + 9
            or decade.get("start_year_ganzhi") != year_ganzhi(start_year)
            or decade.get("end_year_ganzhi") != year_ganzhi(end_year)
        ):
            raise core_contract_error(decade_path)
    return dayun


def term_identity(term: dict[str, Any]) -> tuple[Any, ...]:
    return (
        term["name"],
        term["kind"],
        term["beijing_time"],
        term["utc"],
        term["time_scale"],
        term["model_guard_seconds"],
        term["delta_t_source_code"],
    )


def validate_source_variant_set(
    source_id: str, cases: list[dict[str, Any]]
) -> None:
    if len(cases) == 1:
        case = cases[0]
        review = case["solar_term_boundary_uncertainty"]
        if (
            case["calendar_model_variant"] is not None
            or review["status"] != "CLEAR"
            or review["enumerated_variant_count"] != 1
        ):
            calendar_boundary_unresolved(
                f"Source case {source_id} claims a guarded solar-term result "
                "without both before/after variants"
            )
        return
    if len(cases) != 2:
        calendar_boundary_unresolved(
            f"Source case {source_id} did not return exactly one clear result "
            "or two guarded solar-term variants"
        )
    variants = [case["calendar_model_variant"] for case in cases]
    reviews = [case["solar_term_boundary_uncertainty"] for case in cases]
    if any(variant is None for variant in variants):
        calendar_boundary_unresolved(
            f"Source case {source_id} mixed clear and guarded calendar results"
        )
    states = {variant["state"] for variant in variants if variant is not None}
    review_states = {review["calendar_model_variant_state"] for review in reviews}
    if states != {"birth_before_term", "birth_after_term"} or review_states != states:
        calendar_boundary_unresolved(
            f"Source case {source_id} lacks the exhaustive before/after state pair"
        )
    if len({variant["variant_id"] for variant in variants if variant is not None}) != 2:
        raise core_contract_error("$.cases[].calendar_model_variant.variant_id")
    if any(
        review["status"] != "ENUMERATED_CALENDAR_MODEL_VARIANTS"
        or review["enumerated_variant_count"] != 2
        for review in reviews
    ):
        calendar_boundary_unresolved(
            f"Source case {source_id} has inconsistent solar-term enumeration metadata"
        )
    boundary_terms = {
        term_identity(variant["boundary_term"])
        for variant in variants
        if variant is not None
    }
    event_terms = {
        term_identity(review["events"][0])
        for review in reviews
        if len(review["events"]) == 1
    }
    if len(boundary_terms) != 1 or event_terms != boundary_terms:
        raise core_contract_error("$.cases[].calendar_model_variant.boundary_term")
    if (
        cases[0]["normalized_times"] != cases[1]["normalized_times"]
        or cases[0]["conventions"] != cases[1]["conventions"]
        or cases[0]["lunar_date_beijing_frame"]
        != cases[1]["lunar_date_beijing_frame"]
    ):
        calendar_boundary_unresolved(
            f"Source case {source_id} allowed a solar-term model variant to alter "
            "normalized time, conventions, or independent lunar/HKO evidence"
        )
    by_state = {
        case["calendar_model_variant"]["state"]: case
        for case in cases
        if case["calendar_model_variant"] is not None
    }
    boundary_term = next(
        variant["boundary_term"] for variant in variants if variant is not None
    )
    if (
        term_identity(by_state["birth_before_term"]["solar_terms"]["next"])
        != term_identity(boundary_term)
        or term_identity(
            by_state["birth_after_term"]["solar_terms"]["previous_or_current"]
        )
        != term_identity(boundary_term)
    ):
        calendar_boundary_unresolved(
            f"Source case {source_id} does not bind before/after states to the "
            "guarded term context"
        )
    if reviews[0]["events"] != reviews[1]["events"]:
        raise core_contract_error(
            "$.cases[].solar_term_boundary_uncertainty.events"
        )
    affects_year = {review["affects_year_pillar"] for review in reviews}
    affects_month = {review["affects_month_pillar"] for review in reviews}
    if len(affects_year) != 1 or affects_month != {True}:
        calendar_boundary_unresolved(
            f"Source case {source_id} has inconsistent declared pillar consequences"
        )
    pillar_values = {
        pillar: {case["chart"][pillar]["ganzhi"] for case in cases}
        for pillar in ("year", "month", "day", "hour")
    }
    if len(pillar_values["month"]) != 2:
        calendar_boundary_unresolved(
            f"Source case {source_id} claims a month-pillar boundary without "
            "enumerating distinct month outcomes"
        )
    if (True in affects_year) != (len(pillar_values["year"]) == 2):
        calendar_boundary_unresolved(
            f"Source case {source_id} does not match its declared year-pillar consequence"
        )
    if len(pillar_values["day"]) != 1 or len(pillar_values["hour"]) != 1:
        raise core_contract_error("$.cases[].chart")


def validate_core_success(
    response: Any,
    request: dict[str, Any],
    calendar_data_sha256: str,
    node_core_sha256: str,
) -> dict[str, Any]:
    root = require_core_dict(response, "$")
    expected_mode = request.get("mode")
    root_keys = {"ok", "schema_version", "mode", "engine"}
    root_keys.add("conversion" if expected_mode == "convert_lunar" else "cases")
    require_core_keys(root, root_keys, "$")
    if root.get("ok") is not True:
        raise core_contract_error("$.ok")
    if root.get("schema_version") != CORE_RESPONSE_SCHEMA:
        raise core_contract_error("$.schema_version")
    if root.get("mode") != expected_mode:
        raise core_contract_error("$.mode")
    engine = require_core_dict(root.get("engine"), "$.engine")
    require_core_keys(
        engine,
        {
            "name",
            "version",
            "calendar_dataset_sha256",
            "node_core_sha256",
            "source",
            "coverage",
            "uncertainty",
        },
        "$.engine",
    )
    if engine.get("name") != CORE_ENGINE_NAME or engine.get("version") != CORE_ENGINE_VERSION:
        raise core_contract_error("$.engine")
    for field in ("source", "coverage", "uncertainty"):
        require_core_dict(engine.get(field), f"$.engine.{field}")
    if engine.get("calendar_dataset_sha256") != calendar_data_sha256:
        raise RuntimeError(
            "Calendrical core did not attest the release-pinned calendar dataset digest"
        )
    if engine.get("node_core_sha256") != node_core_sha256:
        raise RuntimeError(
            "Calendrical core did not attest its release-pinned executable digest"
        )

    if expected_mode == "convert_lunar":
        conversion = require_core_dict(root.get("conversion"), "$.conversion")
        require_core_keys(
            conversion,
            {
                "input_lunar",
                "beijing_reference_solar_time",
                "boundary_uncertainty",
            },
            "$.conversion",
        )
        converted_input = require_core_dict(
            conversion.get("input_lunar"), "$.conversion.input_lunar"
        )
        if converted_input != request.get("lunar"):
            raise core_contract_error("$.conversion.input_lunar")
        reference = require_core_string(
            conversion.get("beijing_reference_solar_time"),
            "$.conversion.beijing_reference_solar_time",
            maximum=32,
        )
        try:
            converted = datetime.fromisoformat(reference)
        except ValueError as exc:
            raise core_contract_error(
                "$.conversion.beijing_reference_solar_time"
            ) from exc
        if converted.tzinfo is not None:
            raise core_contract_error("$.conversion.beijing_reference_solar_time")
        try:
            expected_time = time.fromisoformat(request.get("time"))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Orchestrator sent an invalid lunar conversion time") from exc
        if converted.time() != expected_time:
            raise core_contract_error("$.conversion.beijing_reference_solar_time")
        review = validate_boundary_uncertainty(
            conversion.get("boundary_uncertainty"),
            "$.conversion.boundary_uncertainty",
        )
        nominal = validate_core_date_parts(
            review["nominal_beijing_date"],
            "$.conversion.boundary_uncertainty.nominal_beijing_date",
        )
        month_start = validate_core_date_parts(
            review["nominal_month_start_beijing_date"],
            "$.conversion.boundary_uncertainty.nominal_month_start_beijing_date",
        )
        if (
            nominal != converted.date()
            or (nominal - month_start).days + 1 != request["lunar"]["day"]
        ):
            raise core_contract_error("$.conversion.boundary_uncertainty")
        if any(
            review[field]
            for field in (
                "affects_this_nominal_date",
                "reverse_conversion_blocked",
                "unresolved_result_change_without_enumerated_variant",
            )
        ):
            raise RuntimeError(
                "Calendrical core returned a successful reverse conversion while "
                "marking that conversion as blocked"
            )
        return root

    if expected_mode != "charts":
        raise RuntimeError("Orchestrator sent an unsupported core mode")
    requested = require_core_list(request.get("cases"), "request.cases")
    requested_ids: set[str] = set()
    requested_by_id: dict[str, dict[str, Any]] = {}
    for index, raw_case in enumerate(requested):
        item = require_core_dict(raw_case, f"request.cases[{index}]")
        source_id = require_core_string(
            item.get("id"), f"request.cases[{index}].id", maximum=160
        )
        if source_id in requested_ids:
            raise RuntimeError("Orchestrator generated duplicate source case ids")
        requested_ids.add(source_id)
        requested_by_id[source_id] = item
    cases = require_core_list(root.get("cases"), "$.cases")
    if not cases or len(cases) > len(requested_ids) * MAX_CORE_VARIANTS_PER_SOURCE_CASE:
        raise core_contract_error("$.cases")
    returned_ids: set[str] = set()
    returned_sources: set[str] = set()
    returned_by_source: dict[str, list[dict[str, Any]]] = {
        source_id: [] for source_id in requested_ids
    }
    for index, raw_case in enumerate(cases):
        case_path = f"$.cases[{index}]"
        case = require_core_dict(raw_case, case_path)
        require_core_keys(
            case,
            {
                "id",
                "source_case_id",
                "label",
                "calendar_model_variant",
                "solar_term_boundary_uncertainty",
                "conventions",
                "normalized_times",
                "lunar_date_beijing_frame",
                "solar_terms",
                "chart",
                "dayun",
            },
            case_path,
        )
        variant_id = require_core_string(case.get("id"), f"{case_path}.id", maximum=200)
        source_id = require_core_string(
            case.get("source_case_id"),
            f"{case_path}.source_case_id",
            maximum=160,
        )
        if variant_id in returned_ids or source_id not in requested_ids:
            raise core_contract_error(case_path)
        returned_ids.add(variant_id)
        returned_sources.add(source_id)
        returned_by_source[source_id].append(case)
        case["calendar_model_variant"] = validate_calendar_model_variant(
            case.get("calendar_model_variant"),
            f"{case_path}.calendar_model_variant",
        )
        case["solar_term_boundary_uncertainty"] = (
            validate_solar_term_boundary_uncertainty(
                case.get("solar_term_boundary_uncertainty"),
                f"{case_path}.solar_term_boundary_uncertainty",
            )
        )
        expected_case = requested_by_id[source_id]
        if case.get("label") != expected_case.get("label"):
            raise core_contract_error(f"{case_path}.label")
        conventions = validate_conventions(
            case.get("conventions"), expected_case, f"{case_path}.conventions"
        )
        normalized_times = require_core_dict(
            case.get("normalized_times"), f"{case_path}.normalized_times"
        )
        require_core_keys(
            normalized_times,
            {"absolute_utc", "beijing_calendar_frame", "local_basis"},
            f"{case_path}.normalized_times",
        )
        for returned_field, request_field in (
            ("absolute_utc", "absolute_utc"),
            ("beijing_calendar_frame", "beijing_time"),
            ("local_basis", "local_basis_time"),
        ):
            if normalized_times.get(returned_field) != expected_case.get(request_field):
                raise core_contract_error(
                    f"{case_path}.normalized_times.{returned_field}"
                )
        absolute_time = parse_core_utc(
            normalized_times["absolute_utc"],
            f"{case_path}.normalized_times.absolute_utc",
        )
        beijing_time = parse_core_local(
            normalized_times["beijing_calendar_frame"],
            f"{case_path}.normalized_times.beijing_calendar_frame",
        )
        parse_core_local(
            normalized_times["local_basis"],
            f"{case_path}.normalized_times.local_basis",
        )
        if absolute_time.replace(tzinfo=None) + timedelta(hours=8) != beijing_time:
            raise core_contract_error(f"{case_path}.normalized_times")
        chart = validate_chart(case.get("chart"), f"{case_path}.chart")
        case["lunar_date_beijing_frame"] = validate_lunar_date(
            case.get("lunar_date_beijing_frame"),
            beijing_time,
            f"{case_path}.lunar_date_beijing_frame",
        )
        solar_terms = require_core_dict(
            case.get("solar_terms"), f"{case_path}.solar_terms"
        )
        require_core_keys(
            solar_terms,
            {"previous_or_current", "next"},
            f"{case_path}.solar_terms",
        )
        validate_term_evidence(
            solar_terms.get("previous_or_current"),
            f"{case_path}.solar_terms.previous_or_current",
        )
        validate_term_evidence(
            solar_terms.get("next"),
            f"{case_path}.solar_terms.next",
        )
        variant = case["calendar_model_variant"]
        solar_review = case["solar_term_boundary_uncertainty"]
        if (
            (variant is None and solar_review["calendar_model_variant_state"] is not None)
            or (
                variant is not None
                and solar_review["calendar_model_variant_state"] != variant["state"]
            )
        ):
            raise core_contract_error(
                f"{case_path}.solar_term_boundary_uncertainty.calendar_model_variant_state"
            )
        case["dayun"] = validate_dayun(
            case.get("dayun"),
            request,
            chart,
            normalized_times,
            variant,
            f"{case_path}.dayun",
        )
    if returned_sources != requested_ids:
        raise core_contract_error("$.cases[].source_case_id")
    for source_id, source_cases in returned_by_source.items():
        validate_source_variant_set(source_id, source_cases)
    return root


def raise_core_nonzero(process: subprocess.CompletedProcess[str]) -> None:
    errors: list[dict[str, Any]] = []
    for stream_name, stream in (("stderr", process.stderr), ("stdout", process.stdout)):
        if not stream.strip():
            continue
        try:
            parsed = strict_core_json_loads(stream, f"Calendrical core {stream_name}")
        except RuntimeError:
            continue
        if not isinstance(parsed, dict) or parsed.get("ok") is not False:
            continue
        error = parsed.get("error")
        if isinstance(error, dict):
            errors.append(error)
    if not errors:
        raise RuntimeError(
            f"Calendrical core exited {process.returncode} without a valid error envelope"
        )
    error = errors[0]
    kind = error.get("kind")
    code = error.get("code")
    message = error.get("message")
    if (
        kind == "input"
        and code in CORE_INPUT_ERROR_CODES
        and isinstance(message, str)
        and 0 < len(message) <= 4096
    ):
        raise InputContractError(message, code=code)
    safe_code = (
        code
        if isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", code)
        else "MALFORMED_CORE_ERROR"
    )
    raise RuntimeError(
        f"Calendrical core failed with non-user error {safe_code}; calculation stopped"
    )


def run_node(payload: dict[str, Any]) -> dict[str, Any]:
    calendar_data_sha256 = verify_calendar_data()
    node_core_sha256 = verify_node_core()
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is required to run the bundled calendrical core")
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(serialized.encode("utf-8")) > MAX_NODE_INPUT_BYTES:
        raise InputContractError("Normalized candidate set exceeds the safe execution limit")
    # An allowlisted environment prevents host NODE_OPTIONS/NODE_PATH settings from
    # changing the reviewed core while fixing every process-global time/locale input.
    child_env = {"TZ": "UTC", "LC_ALL": "C", "LANG": "C"}
    for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR"):
        if key in os.environ:
            child_env[key] = os.environ[key]
    try:
        process = subprocess.run(
            [node, str(NODE_CORE)],
            input=serialized,
            text=True,
            encoding="utf-8",
            errors="strict",
            capture_output=True,
            check=False,
            timeout=NODE_TIMEOUT_SECONDS,
            env=child_env,
            cwd=SCRIPT_DIR,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Calendrical core exceeded the deterministic runtime limit") from exc
    if (
        len(process.stdout.encode("utf-8")) > MAX_NODE_OUTPUT_BYTES
        or len(process.stderr.encode("utf-8")) > MAX_NODE_OUTPUT_BYTES
    ):
        raise RuntimeError("Calendrical core exceeded the safe output limit")
    if process.returncode != 0:
        raise_core_nonzero(process)
    if process.stderr.strip():
        raise RuntimeError("Calendrical core wrote unexpected stderr on success")
    response = strict_core_json_loads(process.stdout, "Calendrical core stdout")
    return validate_core_success(
        response, payload, calendar_data_sha256, node_core_sha256
    )


def normalize_calendar(birth: dict[str, Any]) -> tuple[date, dict[str, Any] | None]:
    calendar = birth.get("calendar", "gregorian")
    if calendar == "gregorian":
        return parse_date(birth.get("date")), None
    if calendar != "chinese_lunar":
        raise InputContractError("birth.calendar must be gregorian or chinese_lunar")
    lunar = birth.get("lunar")
    if not isinstance(lunar, dict):
        raise InputContractError("birth.lunar is required for chinese_lunar input")
    conversion = run_node({
        "mode": "convert_lunar",
        "lunar": lunar,
        "time": "12:00:00",
    })["conversion"]
    converted = datetime.fromisoformat(conversion["beijing_reference_solar_time"])
    parsed = parse_date(converted.date().isoformat())
    return parsed, {
        **conversion,
        "reference_zone": "fixed UTC+08:00 (modern Chinese lunisolar convention)",
    }


def generate_cases(
    birth_date: date,
    birth: dict[str, Any],
    rules: dict[str, Any],
    bundle: ZoneBundle,
    case_prefix: str = "",
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]], bool]:
    samples, time_uncertain, interval_start, interval_end = sample_datetimes(birth_date, birth)
    samples = sorted(set(samples) | set(timezone_transition_samples(interval_start, interval_end, bundle)))
    requested_fold = birth.get("fold")
    primary_basis = rules.get("time_basis", "civil_clock")
    bases = [primary_basis]
    if rules.get("compare_civil_clock") and primary_basis != "civil_clock":
        bases.append("civil_clock")
    day_rule = rules.get("day_boundary", "both")
    if day_rule == "both":
        day_boundaries = ["zi_initial_next_day", "late_zi_same_day"]
    elif day_rule in {"zi_initial_next_day", "late_zi_same_day"}:
        day_boundaries = [day_rule]
    else:
        raise InputContractError("rules.day_boundary must be both, zi_initial_next_day, or late_zi_same_day")
    longitude = birth.get("longitude")
    if longitude is not None:
        longitude = strict_number(longitude, "birth.longitude", -180, 180)
    cases: list[dict[str, Any]] = []
    metadata: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, Any]] = []
    sequence = 0
    for naive in samples:
        try:
            candidates = resolve_local_datetime(naive, bundle, requested_fold)
        except InputContractError as exc:
            if len(samples) == 1:
                raise
            skipped.append({"local_time": local_iso(naive), "reason": str(exc)})
            continue
        for aware in candidates:
            instant_utc = aware.astimezone(UTC)
            beijing_naive = (instant_utc + timedelta(hours=8)).replace(tzinfo=None)
            if not CALENDAR_FRAME_YEAR_MIN <= beijing_naive.year <= CALENDAR_FRAME_YEAR_MAX:
                raise InputContractError(
                    "The UTC+8 calendar frame crosses outside the frozen "
                    f"{CALENDAR_FRAME_YEAR_MIN}-{CALENDAR_FRAME_YEAR_MAX} data padding"
                )
            for basis in bases:
                corrected, correction = solar_basis(naive, aware, basis, longitude)
                if not CALENDAR_FRAME_YEAR_MIN <= corrected.year <= CALENDAR_FRAME_YEAR_MAX:
                    raise InputContractError(
                        "The selected local time basis crosses outside the frozen "
                        f"{CALENDAR_FRAME_YEAR_MIN}-{CALENDAR_FRAME_YEAR_MAX} data padding"
                    )
                review_offsets = [0]
                guard = rules.get("boundary_guard_seconds", 120)
                if (
                    basis == "local_apparent_solar"
                    and closest_clock_boundary_seconds(corrected) <= guard
                ):
                    review_offsets = [-guard, 0, guard]
                for review_offset in review_offsets:
                    reviewed_time = corrected + timedelta(seconds=review_offset)
                    if not (
                        CALENDAR_FRAME_YEAR_MIN
                        <= reviewed_time.year
                        <= CALENDAR_FRAME_YEAR_MAX
                    ):
                        raise InputContractError(
                            "The apparent-solar review band crosses outside the frozen "
                            f"{CALENDAR_FRAME_YEAR_MIN}-{CALENDAR_FRAME_YEAR_MAX} data padding"
                        )
                    for boundary in day_boundaries:
                        sequence += 1
                        case_id = f"{case_prefix}case-{sequence:04d}"
                        cases.append({
                            "id": case_id,
                            "label": (
                                f"{local_iso(naive)} fold={aware.fold} {basis} {boundary} "
                                f"review_offset={review_offset}s"
                            ),
                            "absolute_utc": utc_iso(instant_utc),
                            "beijing_time": local_iso(beijing_naive),
                            "local_basis_time": local_iso(reviewed_time),
                            "time_basis": basis,
                            "day_boundary": boundary,
                            "solar_review_offset_seconds": review_offset,
                            "scenario_kind": (
                                "input_candidate" if review_offset == 0 else "sensitivity_bracket"
                            ),
                        })
                        correction_with_review = {
                            **correction,
                            "boundary_review_band_seconds": guard if review_offsets != [0] else 0,
                            "review_offset_seconds": review_offset,
                        }
                        metadata[case_id] = {
                            "source_local_time": local_iso(naive),
                            "timezone": bundle.zone.key,
                            "fold": aware.fold,
                            "utc": utc_iso(instant_utc),
                            "local_basis_time": local_iso(reviewed_time),
                            "clock_boundary_distance_seconds": closest_clock_boundary_seconds(reviewed_time),
                            "correction": correction_with_review,
                        }
    if not cases:
        raise InputContractError("No valid local-time candidate remained after timezone validation")
    if len(cases) > MAX_NORMALIZED_CASES:
        raise InputContractError("Normalized candidate set exceeds the safe scenario limit")
    return cases, metadata, skipped, time_uncertain


def term_distance_seconds(case: dict[str, Any], utc_value: str) -> int:
    birth_utc = datetime.fromisoformat(utc_value.replace("Z", "+00:00"))
    terms = case["solar_terms"]
    distances = []
    for term_data in (terms["previous_or_current"], terms["next"]):
        term_utc = datetime.fromisoformat(term_data["utc"].replace("Z", "+00:00"))
        distances.append(abs(int((birth_utc - term_utc).total_seconds())))
    return min(distances)


def summarize_cases(
    core_cases: list[dict[str, Any]], metadata: dict[str, dict[str, Any]], time_uncertain: bool
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    groups: dict[str, dict[str, Any]] = {}
    scenarios: list[dict[str, Any]] = []
    for case in core_cases:
        source_case_id = case["source_case_id"]
        # Calendar variants share one normalized input candidate. Copy its
        # metadata so enriching one variant cannot mutate a sibling.
        meta = dict(metadata[source_case_id])
        meta["nearest_solar_term_distance_seconds"] = term_distance_seconds(case, meta["utc"])
        dayun_key = None
        if case.get("dayun"):
            dayun_key = {
                "selected_jie": case["dayun"]["selected_jie"],
                "direction": case["dayun"]["direction"],
                "interval": case["dayun"]["interval"],
                "symbolic_start_utc_under_provider": case["dayun"][
                    "symbolic_start_utc_under_provider"
                ],
            }
        lunar_result_key = {
            key: value
            for key, value in case["lunar_date_beijing_frame"].items()
            if key != "boundary_uncertainty"
        }
        key_payload = {
            "chart": case["chart"]["ganzhi"],
            "dayun": dayun_key,
            "lunar_date_beijing_frame": lunar_result_key,
            "solar_term_context": {
                "previous_or_current": case["solar_terms"]["previous_or_current"],
                "next": case["solar_terms"]["next"],
            },
        }
        result_key = hashlib.sha256(
            json.dumps(key_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        scenarios.append({
            "scenario_id": case["id"],
            "source_case_id": source_case_id,
            "result_id": result_key,
            "scenario_kind": case["conventions"].get("scenario_kind", "input_candidate"),
            "calendar_model_variant": case["calendar_model_variant"],
            "solar_term_boundary_uncertainty": (
                case["solar_term_boundary_uncertainty"]
            ),
            "conventions": case["conventions"],
            "normalization": meta,
        })
        if result_key not in groups:
            groups[result_key] = {
                "result_id": result_key,
                "scenario_ids": [],
                "source_case_ids": [],
                "scenario_kinds": [],
                "lunar_date_beijing_frame": case["lunar_date_beijing_frame"],
                "solar_terms": case["solar_terms"],
                "calendar_model_variant": case["calendar_model_variant"],
                "solar_term_boundary_uncertainty": (
                    case["solar_term_boundary_uncertainty"]
                ),
                "chart": case["chart"],
                "dayun": case["dayun"],
            }
        groups[result_key]["scenario_ids"].append(case["id"])
        if source_case_id not in groups[result_key]["source_case_ids"]:
            groups[result_key]["source_case_ids"].append(source_case_id)
        kind = case["conventions"].get("scenario_kind", "input_candidate")
        if kind not in groups[result_key]["scenario_kinds"]:
            groups[result_key]["scenario_kinds"].append(kind)
    unique = sorted(groups.values(), key=lambda item: item["result_id"])
    for item in unique:
        item["scenario_ids"].sort()
        item["source_case_ids"].sort()
        item["scenario_kinds"].sort()
    nominal = [item for item in unique if "input_candidate" in item["scenario_kinds"]]
    sensitivity = [item for item in unique if "sensitivity_bracket" in item["scenario_kinds"]]
    sensitivity_only = [
        item for item in sensitivity if "input_candidate" not in item["scenario_kinds"]
    ]
    stable: dict[str, Any] = {}
    variable: dict[str, list[str]] = {}
    for name in ("year", "month", "day", "hour"):
        values = sorted({item["chart"][name]["ganzhi"] for item in nominal})
        stable[name] = values[0] if len(values) == 1 else None
        if len(values) > 1:
            variable[name] = values
    sensitivity_pillars = {
        name: sorted({item["chart"][name]["ganzhi"] for item in sensitivity})
        for name in ("year", "month", "day", "hour")
        if sensitivity
    }
    summary = {
        "status": "single_result" if len(nominal) == 1 else "multiple_candidates",
        "time_input_uncertain": time_uncertain,
        "unique_result_count_including_sensitivity": len(unique),
        "valid_input_result_count": len(nominal),
        "sensitivity_result_count": len(sensitivity),
        "valid_input_result_ids": [item["result_id"] for item in nominal],
        "sensitivity_scenario_result_ids": [item["result_id"] for item in sensitivity],
        "sensitivity_only_result_ids": [item["result_id"] for item in sensitivity_only],
        "stable_pillars": stable,
        "variable_pillars": variable,
        "sensitivity_pillars": sensitivity_pillars,
        "requires_conditional_interpretation": len(nominal) > 1,
        "requires_sensitivity_disclosure": bool(sensitivity),
    }
    return unique, summary, scenarios


def collect_core_boundary_evidence(core_cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Collect source guards, authority facts, and Dayun term evidence separately."""
    lunar_events_by_key: dict[str, dict[str, Any]] = {}
    solar_boundary_events_by_key: dict[str, dict[str, Any]] = {}
    divergences_by_key: dict[str, dict[str, Any]] = {}
    solar_terms_by_key: dict[str, dict[str, Any]] = {}
    term_audits_by_key: dict[str, dict[str, Any]] = {}
    dayun_terms_by_key: dict[str, dict[str, Any]] = {}
    lunar_statuses: set[str] = set()
    lunar_codes: set[str] = set()
    solar_statuses: set[str] = set()
    solar_codes: set[str] = set()
    all_delta_t_sources: set[str] = set()
    all_model_guards: set[int] = set()
    lunar_affected_scenario_ids: set[str] = set()
    lunar_unresolved_scenario_ids: set[str] = set()
    solar_affected_scenario_ids: set[str] = set()
    for case in core_cases:
        scenario_id = case["id"]
        source_case_id = case["source_case_id"]
        lunar_review = case["lunar_date_beijing_frame"]["boundary_uncertainty"]
        lunar_statuses.add(lunar_review["status"])
        lunar_codes.update(lunar_review["codes"])
        all_delta_t_sources.add(lunar_review["start_delta_t_source_code"])
        all_model_guards.add(lunar_review["start_model_guard_seconds"])
        if lunar_review["affects_this_nominal_date"]:
            lunar_affected_scenario_ids.add(scenario_id)
        if lunar_review["unresolved_result_change_without_enumerated_variant"]:
            lunar_unresolved_scenario_ids.add(scenario_id)
        for raw_event in lunar_review["events"]:
            all_delta_t_sources.add(raw_event["delta_t_source_code"])
            all_model_guards.add(raw_event["model_guard_seconds"])
            key = json.dumps(raw_event, ensure_ascii=False, sort_keys=True)
            item = lunar_events_by_key.setdefault(key, {
                **raw_event,
                "scenario_ids": [],
                "source_case_ids": [],
            })
            if scenario_id not in item["scenario_ids"]:
                item["scenario_ids"].append(scenario_id)
            if source_case_id not in item["source_case_ids"]:
                item["source_case_ids"].append(source_case_id)
        for raw_divergence in lunar_review["hko_authority_divergences"]:
            key = json.dumps(raw_divergence, ensure_ascii=False, sort_keys=True)
            item = divergences_by_key.setdefault(key, {
                **raw_divergence,
                "scenario_ids": [],
                "source_case_ids": [],
            })
            if scenario_id not in item["scenario_ids"]:
                item["scenario_ids"].append(scenario_id)
            if source_case_id not in item["source_case_ids"]:
                item["source_case_ids"].append(source_case_id)
        solar_review = case["solar_term_boundary_uncertainty"]
        solar_statuses.add(solar_review["status"])
        solar_codes.update(solar_review["codes"])
        if solar_review["affects_year_pillar"] or solar_review["affects_month_pillar"]:
            solar_affected_scenario_ids.add(scenario_id)
        for raw_event in solar_review["events"]:
            all_delta_t_sources.add(raw_event["delta_t_source_code"])
            all_model_guards.add(raw_event["model_guard_seconds"])
            key = json.dumps(raw_event, ensure_ascii=False, sort_keys=True)
            item = solar_boundary_events_by_key.setdefault(key, {
                **raw_event,
                "scenario_ids": [],
                "source_case_ids": [],
            })
            if scenario_id not in item["scenario_ids"]:
                item["scenario_ids"].append(scenario_id)
            if source_case_id not in item["source_case_ids"]:
                item["source_case_ids"].append(source_case_id)
        for term in case["solar_terms"].values():
            all_delta_t_sources.add(term["delta_t_source_code"])
            all_model_guards.add(term["model_guard_seconds"])
            term_key = json.dumps(term, ensure_ascii=False, sort_keys=True)
            term_item = solar_terms_by_key.setdefault(term_key, {
                **term,
                "scenario_ids": [],
            })
            if scenario_id not in term_item["scenario_ids"]:
                term_item["scenario_ids"].append(scenario_id)
            historical = term.get("historical_oracle_date_divergence")
            if historical is None:
                continue
            key = json.dumps(historical, ensure_ascii=False, sort_keys=True)
            item = term_audits_by_key.setdefault(key, {
                **historical,
                "scenario_ids": [],
            })
            if scenario_id not in item["scenario_ids"]:
                item["scenario_ids"].append(scenario_id)
        if case.get("dayun") is not None:
            raw_term = case["dayun"]["selected_jie"]
            all_delta_t_sources.add(raw_term["delta_t_source_code"])
            all_model_guards.add(raw_term["model_guard_seconds"])
            key = json.dumps(raw_term, ensure_ascii=False, sort_keys=True)
            item = dayun_terms_by_key.setdefault(key, {
                **raw_term,
                "scenario_ids": [],
            })
            if scenario_id not in item["scenario_ids"]:
                item["scenario_ids"].append(scenario_id)
    lunar_events = sorted(
        lunar_events_by_key.values(), key=lambda item: (item["utc"], item["event"])
    )
    solar_boundary_events = sorted(
        solar_boundary_events_by_key.values(),
        key=lambda item: (item["utc"], item["name"]),
    )
    divergences = sorted(
        divergences_by_key.values(),
        key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True),
    )
    solar_terms = sorted(
        solar_terms_by_key.values(), key=lambda item: (item["utc"], item["name"])
    )
    term_audits = sorted(
        term_audits_by_key.values(),
        key=lambda item: (item["computed_beijing_date"], item["term"]),
    )
    dayun_terms = sorted(
        dayun_terms_by_key.values(), key=lambda item: (item["utc"], item["name"])
    )
    for item in (
        lunar_events
        + solar_boundary_events
        + divergences
        + solar_terms
        + term_audits
        + dayun_terms
    ):
        item["scenario_ids"].sort()
        if "source_case_ids" in item:
            item["source_case_ids"].sort()
    lunar_model_codes = lunar_codes - {
        "HISTORICAL_CALENDAR_AUTHORITY_DIVERGENCE"
    }
    return {
        "lunar_events": lunar_events,
        "solar_term_boundary_events": solar_boundary_events,
        "solar_term_context": solar_terms,
        "delta_t_source_codes": sorted(all_delta_t_sources),
        "model_guard_seconds_values": sorted(all_model_guards),
        "lunar": {
            "statuses": sorted(lunar_statuses),
            "codes": sorted(lunar_codes),
            "model_codes": sorted(lunar_model_codes),
            "affected_scenario_ids": sorted(lunar_affected_scenario_ids),
            "unresolved_scenario_ids": sorted(lunar_unresolved_scenario_ids),
            "review_required": bool(
                lunar_model_codes or lunar_events
            ),
        },
        "solar_term": {
            "statuses": sorted(solar_statuses),
            "codes": sorted(solar_codes),
            "affected_scenario_ids": sorted(solar_affected_scenario_ids),
            "review_required": bool(
                solar_codes or solar_affected_scenario_ids
            ),
        },
        "review_required": bool(
            lunar_model_codes
            or lunar_events
            or solar_codes
            or solar_affected_scenario_ids
        ),
        "hko_authority_divergences": divergences,
        "hko_solar_term_date_audits": term_audits,
        "dayun_selected_jie": dayun_terms,
    }


def lunar_frame_matches(case: dict[str, Any], lunar: dict[str, Any]) -> bool:
    actual = case["lunar_date_beijing_frame"]
    return (
        actual["year"] == lunar["year"]
        and actual["month"] == lunar["month"]
        and actual["day"] == lunar["day"]
        and actual["leap_month"] is lunar["leap_month"]
    )


def build_report(payload: dict[str, Any]) -> dict[str, Any]:
    birth, rules = validate_payload(payload)
    orchestrator_sha256 = sha256_file(Path(__file__).resolve())
    calendar_data_sha256 = verify_calendar_data()
    node_core_sha256 = verify_node_core()
    manifest_identity = load_manifest_identity()
    timezone_key = birth.get("timezone")
    bundle = load_frozen_zone(timezone_key)
    birth_date, lunar_conversion = normalize_calendar(birth)
    candidate_dates = [birth_date]
    if birth.get("calendar") == "chinese_lunar":
        candidate_dates = [
            item for item in (
                birth_date - timedelta(days=1), birth_date, birth_date + timedelta(days=1)
            )
            if SUPPORTED_YEAR_MIN <= item.year <= SUPPORTED_YEAR_MAX
        ]
    cases: list[dict[str, Any]] = []
    metadata: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, Any]] = []
    time_uncertain = False
    lunar_candidate_errors: list[str] = []
    for index, candidate_date in enumerate(candidate_dates):
        try:
            generated, generated_meta, generated_skipped, generated_uncertain = generate_cases(
                candidate_date, birth, rules, bundle, case_prefix=f"d{index}-"
            )
        except InputContractError as exc:
            if birth.get("calendar") != "chinese_lunar":
                raise
            lunar_candidate_errors.append(f"{candidate_date.isoformat()}: {exc}")
            continue
        cases.extend(generated)
        metadata.update(generated_meta)
        skipped.extend(generated_skipped)
        time_uncertain = time_uncertain or generated_uncertain
    if not cases:
        detail = "; ".join(lunar_candidate_errors) or "no candidate date remained"
        raise InputContractError(f"Chinese-lunar local-time resolution failed: {detail}")
    if len(cases) > MAX_NORMALIZED_CASES:
        raise InputContractError("Normalized candidate set exceeds the safe scenario limit")
    traditional_sex = payload.get("traditional_sex_for_dayun")
    dayun_blocked_for_uncertainty = traditional_sex is not None and time_uncertain
    core = run_node({
        "mode": "charts",
        "gender": None if dayun_blocked_for_uncertainty else traditional_sex,
        "child_limit_provider": rules.get("child_limit_provider", "default"),
        "decade_count": rules.get("decade_count", 8),
        "cases": cases,
    })
    core_engine = core.get("engine") if isinstance(core, dict) else None
    if (
        not isinstance(core_engine, dict)
        or core_engine.get("calendar_dataset_sha256") != calendar_data_sha256
        or core_engine.get("node_core_sha256") != node_core_sha256
    ):
        raise RuntimeError(
            "Calendrical core did not attest both release-pinned artifact digests"
        )
    if birth.get("calendar") == "chinese_lunar":
        requested_lunar = birth["lunar"]
        matched = [case for case in core["cases"] if lunar_frame_matches(case, requested_lunar)]
        if not matched:
            raise InputContractError(
                "No absolute instant satisfies the supplied local time and Chinese-lunar date"
            )
        matched_source_ids = {case["source_case_id"] for case in matched}
        core["cases"] = matched
        metadata = {
            key: value for key, value in metadata.items() if key in matched_source_ids
        }
        if lunar_conversion is not None:
            lunar_conversion["round_trip_status"] = "VERIFIED_IN_FIXED_UTC_PLUS_8_FRAME"
    unique, summary, scenarios = summarize_cases(core["cases"], metadata, time_uncertain)
    source_boundary = collect_core_boundary_evidence(core["cases"])
    guard_seconds = rules.get("boundary_guard_seconds", 120)
    term_risk = any(
        scenario["normalization"]["nearest_solar_term_distance_seconds"] <= guard_seconds
        for scenario in scenarios
    )
    clock_risk = any(
        scenario["normalization"]["clock_boundary_distance_seconds"] <= guard_seconds
        for scenario in scenarios
    )
    interval_term_crossing = time_uncertain and any(
        pillar in summary["variable_pillars"] for pillar in ("year", "month")
    )
    interval_clock_crossing = time_uncertain and any(
        pillar in summary["variable_pillars"] for pillar in ("day", "hour")
    )
    term_risk = term_risk or interval_term_crossing
    clock_risk = clock_risk or interval_clock_crossing
    apparent_solar_uncertified = any(
        scenario["conventions"]["day_hour_time_basis"] == "local_apparent_solar"
        for scenario in scenarios
    )
    lunar_boundary_indeterminate = bool(
        source_boundary["lunar"]["unresolved_scenario_ids"]
    )
    if lunar_boundary_indeterminate:
        # Gregorian charts retain the nominal fixed-UTC+8 lunar label and four
        # pillars as evidence, but they are not promoted to a unique resolved
        # calendar result. Solar-term variants cannot clear this independent
        # new-moon/HKO condition.
        summary["status"] = "indeterminate_calendar_boundary"
        summary["calendar_boundary_indeterminate"] = True
        summary["nominal_lunar_results_only"] = True
        summary["requires_conditional_interpretation"] = True
    else:
        summary["calendar_boundary_indeterminate"] = False
        summary["nominal_lunar_results_only"] = False
    dataset_review_required = source_boundary["review_required"]
    authority_review_required = bool(
        source_boundary["hko_authority_divergences"]
        or source_boundary["hko_solar_term_date_audits"]
    )
    summary["boundary_review"] = {
        # These are siblings, not substitutes. No combined "effective guard" is
        # exposed: changing the caller guard cannot erase a frozen event guard
        # or an authority divergence.
        # The five scalar aliases remain for report-v0.1 consumers; the named
        # caller_input_guard object is the authoritative structured layer.
        "guard_seconds": guard_seconds,
        "near_solar_term": term_risk,
        "near_day_or_shichen_boundary": clock_risk,
        "input_interval_crosses_term_boundary": interval_term_crossing,
        "input_interval_crosses_day_or_shichen_boundary": interval_clock_crossing,
        "caller_input_guard": {
            "boundary_guard_seconds": guard_seconds,
            "near_solar_term": term_risk,
            "near_day_or_shichen_boundary": clock_risk,
            "input_interval_crosses_term_boundary": interval_term_crossing,
            "input_interval_crosses_day_or_shichen_boundary": interval_clock_crossing,
        },
        "dataset_event_model_guards": {
            "cannot_be_overridden_by_caller": True,
            "review_required": dataset_review_required,
            "delta_t_source_codes": source_boundary["delta_t_source_codes"],
            "model_guard_seconds_values": source_boundary["model_guard_seconds_values"],
            "lunar_boundary": {
                **source_boundary["lunar"],
                "events": source_boundary["lunar_events"],
            },
            "solar_term_boundary": {
                **source_boundary["solar_term"],
                "events": source_boundary["solar_term_boundary_events"],
                "solar_term_context": source_boundary["solar_term_context"],
            },
        },
        "hko_authority_divergence": {
            "cannot_be_overridden_by_caller": True,
            "review_required": authority_review_required,
            "items": source_boundary["hko_authority_divergences"],
            "solar_term_date_audits": source_boundary["hko_solar_term_date_audits"],
        },
        # Every selected Dayun Jie retains the same source/guard fields as any
        # other term; the provider interval can therefore be audited.
        "dayun_selected_jie": source_boundary["dayun_selected_jie"],
        "apparent_solar_model_has_validated_error_bound": (
            False if apparent_solar_uncertified else None
        ),
        "manual_independent_review_required": (
            term_risk
            or dataset_review_required
            or authority_review_required
            or lunar_boundary_indeterminate
            or apparent_solar_uncertified
        ),
    }
    resolved_local_dates = sorted(
        {scenario["normalization"]["source_local_time"][:10] for scenario in scenarios}
    )
    dayun_status = (
        "BLOCKED_UNCERTAIN_BIRTH_TIME"
        if dayun_blocked_for_uncertainty
        else ("COMPUTED_UNDER_PROVIDER" if traditional_sex is not None else "NOT_REQUESTED")
    )
    ruleset_identity_sha256 = hashlib.sha256(
        json.dumps(
            {
                "ruleset": RULESET_VERSION,
                "orchestrator_sha256": orchestrator_sha256,
                "node_core_sha256": node_core_sha256,
                "calendar_dataset_sha256": calendar_data_sha256,
                "tzdata_package": EXPECTED_TZDATA_PACKAGE_VERSION,
                "tzdb": EXPECTED_TZDB_VERSION,
                "manifests": manifest_identity,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "xuanshu-four-pillars-report-v0.1",
        "validation_status": "DEVELOPMENT_VALIDATED_NOT_INDEPENDENTLY_CERTIFIED",
        "scientific_prediction_status": "NOT_EMPIRICALLY_VALIDATED",
        "engine": {
            "orchestrator": f"four_pillars_engine.py/{ENGINE_VERSION}",
            "orchestrator_sha256": orchestrator_sha256,
            "node_core_sha256": node_core_sha256,
            "calendar_core": core["engine"],
            "calendar_dataset": {
                "artifact": CALENDAR_DATA.name,
                "coverage": f"{SUPPORTED_YEAR_MIN}-{SUPPORTED_YEAR_MAX}",
                "calendar_frame_padding": (
                    f"{CALENDAR_FRAME_YEAR_MIN}-{CALENDAR_FRAME_YEAR_MAX}"
                ),
                "accepted_lunar_year_labels": (
                    f"{SUPPORTED_LUNAR_YEAR_MIN}-{SUPPORTED_LUNAR_YEAR_MAX}"
                ),
                "sha256": calendar_data_sha256,
            },
            "ruleset": RULESET_VERSION,
            "ruleset_identity_sha256": ruleset_identity_sha256,
            "ruleset_manifests": manifest_identity,
            "tzdb": {
                "source": bundle.source,
                "version": bundle.version,
                "zone": bundle.zone.key,
                "zone_file_sha256": bundle.sha256,
                "python_package_version": (
                    importlib.metadata.version("tzdata")
                    if bundle.source == "python-tzdata-frozen"
                    else None
                ),
            },
        },
        "input_contract": {
            "calendar": birth.get("calendar", "gregorian"),
            "normalized_birth_input": birth,
            "resolved_local_gregorian_dates": resolved_local_dates,
            "time_was_provided": birth.get("time") is not None,
            "time_range_was_provided": birth.get("time_range") is not None,
            "timezone": timezone_key,
            "longitude_east_deg": birth.get("longitude"),
            "lunar_conversion": lunar_conversion,
        },
        "rules": {
            "year_boundary": "computed_lichun_instant",
            "month_boundary": "computed_jie_instant",
            "term_frame": "absolute_instant",
            "time_basis": rules.get("time_basis", "civil_clock"),
            "day_boundary": rules.get("day_boundary", "both"),
            "child_limit_provider": rules.get("child_limit_provider", "default"),
            "dayun_status": dayun_status,
        },
        "summary": summary,
        "scenarios": scenarios,
        "results": unique,
        "skipped_interval_samples": skipped,
        "limitations": [
            "Traditional interpretation is not a scientifically validated prediction.",
            "Runtime solar-term and lunisolar lookup uses a frozen 1901-2033 dataset generated at build time with Skyfield from JPL DE440s; neither Skyfield nor the upstream ephemeris kernel is distributed or executed at runtime.",
            "TT-to-civil-time generation uses frozen USNO Delta T observations and predictions plus independently implemented NASA polynomial segments; the recorded model guard must be reviewed when its uncertainty band can cross a calendar or pillar boundary.",
            "Local apparent solar time uses a NOAA approximation for the equation of time; inspect boundary_review before treating a boundary result as unique.",
            "An uncertain birth time blocks the provider-specific symbolic Dayun start in v0.1; no sampled start instants are presented as a continuous candidate set.",
            "IANA historical offsets describe legal-time data, not necessarily the clock standard actually written on a historical birth record.",
            "The bundled traditional rule registry is experimental and intentionally limited; unregistered material interpretations must be omitted.",
        ],
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Path to an input JSON file")
    source.add_argument("--json", help="Inline input JSON")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.input:
            if args.input.stat().st_size > MAX_JSON_INPUT_BYTES:
                raise InputContractError("JSON input exceeds the safe 1 MiB limit")
            payload = strict_json_loads(args.input.read_text(encoding="utf-8"))
        else:
            payload = strict_json_loads(args.json)
        report = build_report(payload)
        text = json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
        print(text)
        return 0
    except (InputContractError, json.JSONDecodeError) as exc:
        error_code = exc.code if isinstance(exc, InputContractError) else "INVALID_JSON"
        print(json.dumps({
            "ok": False,
            "error": {
                "kind": "input",
                "code": error_code,
                "message": str(exc),
            },
        }, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    except (OSError, RuntimeError) as exc:
        print(json.dumps({
            "ok": False,
            "error": {
                "kind": "runtime",
                "code": exc.__class__.__name__,
                "message": str(exc),
            },
        }, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 3
    except Exception:
        print(json.dumps({
            "ok": False,
            "error": {
                "kind": "runtime",
                "code": "INTERNAL_ENGINE_ERROR",
                "message": "Unexpected internal engine failure; calculation stopped without fallback.",
            },
        }, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
