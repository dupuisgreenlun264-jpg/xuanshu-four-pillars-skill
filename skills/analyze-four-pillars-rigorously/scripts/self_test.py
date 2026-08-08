#!/usr/bin/env python3
"""Fast offline regression checks for the bundled Four Pillars engine."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
NODE_CORE = SCRIPT_DIR / "four_pillars_core.js"
CALENDAR_DATA = SCRIPT_DIR / "data" / "calendar-1901-2033.json"
sys.path.insert(0, str(SCRIPT_DIR))

import four_pillars_engine as engine  # noqa: E402


def run_node_core(
    payload: dict[str, object],
) -> tuple[subprocess.CompletedProcess[bytes], dict]:
    """Invoke the bundled Node core without passing through Python hash pins."""
    completed = subprocess.run(
        ["node", str(NODE_CORE)],
        input=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
    )
    raw = completed.stdout if completed.stdout.strip() else completed.stderr
    if not raw:
        raise AssertionError(f"Node core returned no JSON (exit {completed.returncode})")
    return completed, json.loads(raw.decode("utf-8"))


def lunar_request(year: int, month: int, day: int, leap_month: bool) -> dict[str, object]:
    return {
        "mode": "convert_lunar",
        "lunar": {
            "year": year,
            "month": month,
            "day": day,
            "leap_month": leap_month,
        },
        "time": "12:34:56.123456",
    }


def chart_request(
    *,
    case_id: str = "fixture",
    absolute_utc: str = "1990-05-15T06:35:00Z",
    beijing_time: str = "1990-05-15T14:35:00",
    local_basis_time: str = "1990-05-15T14:35:00",
    time_basis: str = "civil_clock",
    gender: str | None = None,
    provider: str = "default",
    decade_count: int = 3,
) -> dict[str, object]:
    return {
        "mode": "charts",
        "gender": gender,
        "child_limit_provider": provider,
        "decade_count": decade_count,
        "cases": [{
            "id": case_id,
            "label": case_id,
            "absolute_utc": absolute_utc,
            "beijing_time": beijing_time,
            "local_basis_time": local_basis_time,
            "time_basis": time_basis,
            "day_boundary": "zi_initial_next_day",
            "scenario_kind": "input_candidate",
        }],
    }


class FourPillarsEngineTests(unittest.TestCase):
    def assert_core_mutation_rejected(
        self,
        response: dict,
        request: dict[str, object],
        mutate,
    ) -> None:
        candidate = copy.deepcopy(response)
        mutate(candidate)
        with self.assertRaises((RuntimeError, engine.InputContractError)):
            engine.validate_core_success(
                candidate,
                request,
                engine.verify_calendar_data(),
                engine.verify_node_core(),
            )

    def test_upstream_four_pillars_golden(self) -> None:
        report = engine.build_report({
            "birth": {
                "calendar": "gregorian",
                "date": "2005-12-23",
                "time": "08:37:00",
                "timezone": "Asia/Shanghai",
            },
            "rules": {"time_basis": "civil_clock", "day_boundary": "zi_initial_next_day"},
        })
        self.assertEqual("乙酉 戊子 辛巳 壬辰", report["results"][0]["chart"]["ganzhi"])
        self.assertEqual(
            {"rule_registry", "provider_manifest", "provenance_manifest"},
            set(report["engine"]["ruleset_manifests"]),
        )
        self.assertEqual(64, len(report["engine"]["ruleset_identity_sha256"]))

    def test_zi_hour_school_variants_are_not_merged(self) -> None:
        report = engine.build_report({
            "birth": {
                "calendar": "gregorian",
                "date": "1988-02-15",
                "time": "23:30:00",
                "timezone": "Asia/Shanghai",
            },
            "rules": {"time_basis": "civil_clock", "day_boundary": "both"},
        })
        charts = {item["chart"]["ganzhi"] for item in report["results"]}
        self.assertEqual({"戊辰 甲寅 庚子 戊子", "戊辰 甲寅 辛丑 戊子"}, charts)
        self.assertIsNone(report["summary"]["stable_pillars"]["day"])

    def test_lunar_to_solar_conversion_golden(self) -> None:
        report = engine.build_report({
            "birth": {
                "calendar": "chinese_lunar",
                "lunar": {"year": 2019, "month": 12, "day": 12, "leap_month": False},
                "time": "11:22",
                "timezone": "Asia/Shanghai",
            },
            "rules": {"time_basis": "civil_clock", "day_boundary": "zi_initial_next_day"},
        })
        self.assertEqual(["2020-01-06"], report["input_contract"]["resolved_local_gregorian_dates"])
        self.assertEqual(
            "VERIFIED_IN_FIXED_UTC_PLUS_8_FRAME",
            report["input_contract"]["lunar_conversion"]["round_trip_status"],
        )
        self.assertEqual("己亥 丁丑 戊申 戊午", report["results"][0]["chart"]["ganzhi"])

    def test_lunar_input_round_trips_outside_utc_plus_8(self) -> None:
        requested = {"year": 2019, "month": 12, "day": 12, "leap_month": False}
        report = engine.build_report({
            "birth": {
                "calendar": "chinese_lunar",
                "lunar": requested,
                "time": "11:22",
                "timezone": "America/New_York",
            },
            "rules": {"time_basis": "civil_clock", "day_boundary": "zi_initial_next_day"},
        })
        for result in report["results"]:
            actual = result["lunar_date_beijing_frame"]
            self.assertEqual(requested, {
                "year": actual["year"], "month": actual["month"], "day": actual["day"],
                "leap_month": actual["leap_month"],
            })

    def test_lunar_leap_flag_is_strict_boolean(self) -> None:
        with self.assertRaises(engine.InputContractError):
            engine.build_report({
                "birth": {
                    "calendar": "chinese_lunar",
                    "lunar": {"year": 2020, "month": 4, "day": 1, "leap_month": "false"},
                    "time": "12:00", "timezone": "Asia/Shanghai",
                }
            })

    def test_lunar_date_with_explicit_fold_selects_matching_local_date(self) -> None:
        report = engine.build_report({
            "birth": {
                "calendar": "chinese_lunar",
                "lunar": {"year": 2024, "month": 10, "day": 3, "leap_month": False},
                "time": "01:30", "timezone": "America/New_York", "fold": 0,
            },
            "rules": {"time_basis": "civil_clock", "day_boundary": "zi_initial_next_day"},
        })
        self.assertEqual(["2024-11-03"], report["input_contract"]["resolved_local_gregorian_dates"])
        self.assertEqual(
            {0}, {item["normalization"]["fold"] for item in report["scenarios"]}
        )

    def test_dst_fold_produces_two_utc_candidates(self) -> None:
        report = engine.build_report({
            "birth": {
                "calendar": "gregorian",
                "date": "2024-11-03",
                "time": "01:30",
                "timezone": "America/New_York",
            },
            "rules": {"time_basis": "civil_clock", "day_boundary": "zi_initial_next_day"},
        })
        utc_values = {item["normalization"]["utc"] for item in report["scenarios"]}
        folds = {item["normalization"]["fold"] for item in report["scenarios"]}
        self.assertEqual(2, len(utc_values))
        self.assertEqual({0, 1}, folds)

    def test_dst_gap_fails_closed(self) -> None:
        with self.assertRaises(engine.InputContractError):
            engine.build_report({
                "birth": {
                    "calendar": "gregorian",
                    "date": "2024-03-10",
                    "time": "02:30",
                    "timezone": "America/New_York",
                },
                "rules": {"time_basis": "civil_clock"},
            })

    def test_historical_short_fold_is_preserved_in_interval(self) -> None:
        report = engine.build_report({
            "birth": {
                "calendar": "gregorian", "date": "1933-04-01",
                "time_range": {"start": "11:30", "end": "12:10"},
                "timezone": "America/Santo_Domingo", "longitude": -69.9312,
            },
            "rules": {"time_basis": "civil_clock", "day_boundary": "zi_initial_next_day"},
        })
        folds = {item["normalization"]["fold"] for item in report["scenarios"]}
        utc_at_1150 = {
            item["normalization"]["utc"] for item in report["scenarios"]
            if item["normalization"]["source_local_time"] == "1933-04-01T11:50:00"
        }
        self.assertEqual({0, 1}, folds)
        self.assertEqual(2, len(utc_at_1150))

    def test_longitude_delta_changes_mean_solar_time_by_four_minutes(self) -> None:
        bundle = engine.load_frozen_zone("Asia/Shanghai")
        naive = datetime.fromisoformat("2024-06-01T12:00:00")
        aware = engine.resolve_local_datetime(naive, bundle, None)[0]
        _, first = engine.solar_basis(naive, aware, "local_mean_solar", 120.0)
        _, second = engine.solar_basis(naive, aware, "local_mean_solar", 121.0)
        self.assertAlmostEqual(
            4.0,
            second["total_correction_minutes"] - first["total_correction_minutes"],
            places=6,
        )

    def test_apparent_solar_time_is_invariant_to_display_timezone(self) -> None:
        instant_cases = [
            ("Pacific/Kiritimati", "2024-12-24", "00:58:45"),
            ("Pacific/Pago_Pago", "2024-12-22", "23:58:45"),
        ]
        reports = []
        for timezone, day, wall_time in instant_cases:
            reports.append(engine.build_report({
                "birth": {
                    "calendar": "gregorian", "date": day, "time": wall_time,
                    "timezone": timezone, "longitude": 0.0,
                },
                "rules": {
                    "time_basis": "local_apparent_solar",
                    "day_boundary": "zi_initial_next_day",
                },
            }))
        self.assertEqual(
            {item["chart"]["ganzhi"] for item in reports[0]["results"]},
            {item["chart"]["ganzhi"] for item in reports[1]["results"]},
        )
        self.assertEqual(
            {item["normalization"]["local_basis_time"] for item in reports[0]["scenarios"]},
            {item["normalization"]["local_basis_time"] for item in reports[1]["scenarios"]},
        )
        for report in reports:
            self.assertEqual(1, report["summary"]["valid_input_result_count"])
            self.assertTrue(report["summary"]["requires_sensitivity_disclosure"])
            self.assertTrue(report["summary"]["sensitivity_only_result_ids"])
            self.assertEqual(
                {"input_candidate", "sensitivity_bracket"},
                {item["scenario_kind"] for item in report["scenarios"]},
            )

    def test_absolute_term_frame_is_timezone_invariant(self) -> None:
        shanghai = engine.build_report({
            "birth": {
                "calendar": "gregorian", "date": "2024-02-04", "time": "17:00",
                "timezone": "Asia/Shanghai",
            },
            "rules": {"time_basis": "civil_clock", "day_boundary": "zi_initial_next_day"},
        })
        new_york = engine.build_report({
            "birth": {
                "calendar": "gregorian", "date": "2024-02-04", "time": "04:00",
                "timezone": "America/New_York",
            },
            "rules": {"time_basis": "civil_clock", "day_boundary": "zi_initial_next_day"},
        })
        for pillar in ("year", "month"):
            self.assertEqual(
                shanghai["results"][0]["chart"][pillar]["ganzhi"],
                new_york["results"][0]["chart"][pillar]["ganzhi"],
            )

    def test_timezone_data_is_explicitly_versioned(self) -> None:
        bundle = engine.load_frozen_zone("Asia/Shanghai")
        self.assertEqual(engine.EXPECTED_TZDB_VERSION, bundle.version)
        self.assertEqual("bundled-tzdata-frozen", bundle.source)
        self.assertEqual("2026.3", engine.EXPECTED_TZDATA_BUNDLE_VERSION)
        self.assertEqual(64, len(bundle.sha256))

    def test_timezone_key_cannot_escape_frozen_root(self) -> None:
        with self.assertRaises(engine.InputContractError):
            engine.load_frozen_zone(
                "../../../../../../../../../../../usr/share/zoneinfo/Asia/Shanghai"
            )
        self.assertEqual("UTC", engine.load_frozen_zone("UTC").zone.key)

    def test_timezone_manifest_missing_or_tampered_fails_closed(self) -> None:
        missing = Path("/definitely-missing-xuanshu-tzdata-manifest.json")
        with mock.patch.object(engine, "TZDATA_BUNDLE_MANIFEST", missing):
            with self.assertRaisesRegex(RuntimeError, "manifest is missing"):
                engine.load_frozen_zone("UTC")

        with tempfile.TemporaryDirectory() as directory:
            tampered = Path(directory) / "MANIFEST.json"
            tampered.write_text("{}\n", encoding="utf-8")
            with mock.patch.object(engine, "TZDATA_BUNDLE_MANIFEST", tampered):
                with self.assertRaisesRegex(RuntimeError, "manifest integrity check failed"):
                    engine.load_frozen_zone("UTC")

    def test_tampered_selected_tzif_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "zoneinfo"
            target = root / "Asia" / "Shanghai"
            target.parent.mkdir(parents=True)
            source = engine.VENDORED_TZDATA_ROOT / "Asia" / "Shanghai"
            payload = bytearray(source.read_bytes())
            payload[-1] ^= 1
            target.write_bytes(payload)
            (root / "tzdata.zi").write_bytes(
                (engine.VENDORED_TZDATA_ROOT / "tzdata.zi").read_bytes()
            )
            with mock.patch.object(engine, "VENDORED_TZDATA_ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "file integrity check failed"):
                    engine.load_frozen_zone("Asia/Shanghai")

    def test_tampered_tzdata_version_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "zoneinfo"
            target = root / "Asia" / "Shanghai"
            target.parent.mkdir(parents=True)
            target.write_bytes(
                (engine.VENDORED_TZDATA_ROOT / "Asia" / "Shanghai").read_bytes()
            )
            payload = bytearray((engine.VENDORED_TZDATA_ROOT / "tzdata.zi").read_bytes())
            payload[-1] ^= 1
            (root / "tzdata.zi").write_bytes(payload)
            with mock.patch.object(engine, "VENDORED_TZDATA_ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "file integrity check failed"):
                    engine.load_frozen_zone("Asia/Shanghai")

    def test_input_conflicts_and_unsupported_rules_fail_closed(self) -> None:
        base = {
            "calendar": "gregorian", "date": "2024-06-01", "time": "12:00",
            "timezone": "Asia/Shanghai",
        }
        with self.assertRaises(engine.InputContractError):
            engine.build_report({
                "birth": {**base, "time_range": {"start": "10:00", "end": "11:00"}}
            })
        with self.assertRaises(engine.InputContractError):
            engine.build_report({"birth": base, "rules": {"year_boundary": "lunar_new_year"}})
        with self.assertRaises(engine.InputContractError):
            engine.build_report({"birth": base, "rules": {"boundary_guard_seconds": -1}})
        with self.assertRaises(engine.InputContractError):
            engine.build_report({"birth": {**base, "fold": True}})
        with self.assertRaises(engine.InputContractError):
            engine.build_report({"birth": {**base, "fold": 0}})
        for invalid_rules in (None, [], False, "", 0):
            with self.subTest(rules=invalid_rules), self.assertRaises(engine.InputContractError):
                engine.build_report({"birth": base, "rules": invalid_rules})

    def test_uncertain_time_blocks_provider_dayun_start(self) -> None:
        report = engine.build_report({
            "birth": {
                "calendar": "gregorian", "date": "1990-05-15",
                "time_range": {"start": "12:00", "end": "18:59"},
                "timezone": "Asia/Shanghai",
            },
            "traditional_sex_for_dayun": "woman",
            "rules": {"time_basis": "civil_clock", "day_boundary": "both"},
        })
        self.assertEqual("BLOCKED_UNCERTAIN_BIRTH_TIME", report["rules"]["dayun_status"])
        self.assertTrue(all(item["dayun"] is None for item in report["results"]))

    def test_interval_crossing_shichen_sets_boundary_review(self) -> None:
        report = engine.build_report({
            "birth": {
                "calendar": "gregorian", "date": "2024-06-01",
                "time_range": {"start": "10:30", "end": "11:30"},
                "timezone": "Asia/Shanghai", "longitude": 116.25,
            },
            "rules": {"time_basis": "local_mean_solar", "day_boundary": "zi_initial_next_day"},
        })
        review = report["summary"]["boundary_review"]
        self.assertTrue(review["near_day_or_shichen_boundary"])
        self.assertTrue(review["input_interval_crosses_day_or_shichen_boundary"])

    def test_interval_grid_rounds_to_next_half_hour(self) -> None:
        samples, _, _, _ = engine.sample_datetimes(
            datetime.fromisoformat("2024-06-01T00:00:00").date(),
            {"time_range": {"start": "10:01:30", "end": "11:10"}},
        )
        rendered = {item.time().isoformat() for item in samples}
        self.assertIn("10:30:00", rendered)
        self.assertIn("11:00:00", rendered)

    def test_identical_input_is_canonical(self) -> None:
        payload = {
            "birth": {
                "calendar": "gregorian", "date": "1999-06-07", "time": "09:11",
                "timezone": "Asia/Shanghai",
            },
            "rules": {"time_basis": "civil_clock", "day_boundary": "zi_initial_next_day"},
        }
        first = json.dumps(engine.build_report(payload), ensure_ascii=False, sort_keys=True)
        second = json.dumps(engine.build_report(payload), ensure_ascii=False, sort_keys=True)
        self.assertEqual(first, second)

    def test_node_v02_schema_and_actual_artifact_attestation(self) -> None:
        completed, response = run_node_core(lunar_request(2019, 12, 12, False))
        self.assertEqual(0, completed.returncode, completed.stderr.decode("utf-8"))
        self.assertTrue(response["ok"])
        self.assertEqual("xuanshu-four-pillars-core-response-v0.2", response["schema_version"])
        self.assertEqual("convert_lunar", response["mode"])
        self.assertEqual(
            hashlib.sha256(NODE_CORE.read_bytes()).hexdigest(),
            response["engine"]["node_core_sha256"],
        )
        self.assertEqual(
            hashlib.sha256(CALENDAR_DATA.read_bytes()).hexdigest(),
            response["engine"]["calendar_dataset_sha256"],
        )

    def test_core_success_contract_rejects_shape_chart_convention_and_term_mutations(
        self,
    ) -> None:
        request = chart_request(gender="woman", decade_count=2)
        response = engine.run_node(request)

        mutations = {
            "unknown root field": lambda item: item.update({"unexpected": True}),
            "aggregate chart mismatch": lambda item: item["cases"][0]["chart"].update(
                {"ganzhi": "甲子 甲子 甲子 甲子"}
            ),
            "invalid pillar ganzhi": lambda item: item["cases"][0]["chart"][
                "year"
            ].update({"ganzhi": "坏坏"}),
            "valid-enum Ten God mismatch": lambda item: item["cases"][0]["chart"][
                "year"
            ]["stem"].update({
                "ten_god": (
                    "正官"
                    if item["cases"][0]["chart"]["year"]["stem"]["ten_god"]
                    != "正官"
                    else "偏财"
                )
            }),
            "convention not echoed": lambda item: item["cases"][0][
                "conventions"
            ].update({"day_boundary": "late_zi_same_day"}),
            "invalid solar-term kind": lambda item: item["cases"][0]["solar_terms"][
                "next"
            ].update({"kind": "nonsense"}),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                self.assert_core_mutation_rejected(response, request, mutate)

    def test_core_success_contract_rejects_dayun_mutations_and_presence_mismatch(
        self,
    ) -> None:
        request = chart_request(gender="woman", decade_count=2)
        response = engine.run_node(request)
        mutations = {
            "direction": lambda item: item["cases"][0]["dayun"].update(
                {"direction": "sideways"}
            ),
            "provider echo": lambda item: item["cases"][0]["dayun"].update(
                {"provider": "china95"}
            ),
            "interval shape": lambda item: item["cases"][0]["dayun"].update(
                {"interval": {"years": 999999}}
            ),
            "interval no longer reaches symbolic time": lambda item: item["cases"][0][
                "dayun"
            ]["interval"].update({
                "years": item["cases"][0]["dayun"]["interval"]["years"] + 1
            }),
            "symbolic UTC": lambda item: item["cases"][0]["dayun"].update(
                {"symbolic_start_utc_under_provider": "not-a-time"}
            ),
            "missing requested Dayun": lambda item: item["cases"][0].update(
                {"dayun": None}
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                self.assert_core_mutation_rejected(response, request, mutate)

        no_dayun_request = chart_request(gender=None, decade_count=2)
        no_dayun_response = engine.run_node(no_dayun_request)
        copied_dayun = response["cases"][0]["dayun"]
        self.assert_core_mutation_rejected(
            no_dayun_response,
            no_dayun_request,
            lambda item: item["cases"][0].update(
                {"dayun": copy.deepcopy(copied_dayun)}
            ),
        )

    def test_lunar_boundary_contract_is_derived_and_conversion_success_is_unblocked(
        self,
    ) -> None:
        request = lunar_request(1978, 8, 1, False)
        response = engine.run_node(request)
        review_path = lambda item: item["conversion"]["boundary_uncertainty"]
        mutations = {
            "affected flag contradicts event": lambda item: review_path(item).update(
                {"affects_this_nominal_date": True}
            ),
            "changing event remains review-only": lambda item: review_path(item)[
                "events"
            ][0].update({"changes_calendar_assignment": True}),
            "clear status retains evidence": lambda item: review_path(item).update(
                {"status": "CLEAR"}
            ),
            "unknown status": lambda item: review_path(item).update(
                {"status": "TURTLE"}
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                self.assert_core_mutation_rejected(response, request, mutate)

        def make_semantically_blocked_success(item: dict) -> None:
            review = review_path(item)
            review.update({
                "status": "MODEL_GUARD_CROSSES_BEIJING_MIDNIGHT",
                "codes": ["LUNAR_BOUNDARY_MODEL_GUARD"],
                "affects_this_nominal_date": True,
                "reverse_conversion_blocked": True,
                "unresolved_result_change_without_enumerated_variant": True,
            })
            review["events"][0]["changes_calendar_assignment"] = True

        self.assert_core_mutation_rejected(
            response, request, make_semantically_blocked_success
        )

    def test_solar_variants_cannot_change_lunar_evidence_or_swap_term_states(self) -> None:
        request = chart_request(
            case_id="near-lichun",
            absolute_utc="1910-02-04T16:29:02.210Z",
            beijing_time="1910-02-05T00:29:02.210",
            local_basis_time="1910-02-05T00:29:02.210000",
            gender="woman",
            decade_count=2,
        )
        response = engine.run_node(request)

        self.assert_core_mutation_rejected(
            response,
            request,
            lambda item: item["cases"][1]["lunar_date_beijing_frame"].update(
                {"year": item["cases"][1]["lunar_date_beijing_frame"]["year"] + 1}
            ),
        )

        def swap_states(item: dict) -> None:
            for case in item["cases"]:
                old = case["calendar_model_variant"]["state"]
                new = (
                    "birth_after_term"
                    if old == "birth_before_term"
                    else "birth_before_term"
                )
                case["calendar_model_variant"]["state"] = new
                case["calendar_model_variant"]["classification_rule"] = (
                    "year_and_month_classified_immediately_before_the_guarded_Jie"
                    if new == "birth_before_term"
                    else "year_and_month_classified_immediately_after_the_guarded_Jie"
                )
                case["solar_term_boundary_uncertainty"][
                    "calendar_model_variant_state"
                ] = new

        self.assert_core_mutation_rejected(response, request, swap_states)

        def diverge_guard_events(item: dict) -> None:
            event = item["cases"][1]["solar_term_boundary_uncertainty"]["events"][0]
            event["absolute_distance_seconds"] += 0.1

        self.assert_core_mutation_rejected(response, request, diverge_guard_events)

        before = next(
            case for case in response["cases"]
            if case["calendar_model_variant"]["state"] == "birth_before_term"
        )

        def erase_dayun_direction_change(item: dict) -> None:
            for case in item["cases"]:
                if case["calendar_model_variant"]["state"] == "birth_after_term":
                    case["dayun"]["direction"] = before["dayun"]["direction"]

        self.assert_core_mutation_rejected(
            response, request, erase_dayun_direction_change
        )

        coincident_request = chart_request(
            case_id="coincident",
            absolute_utc="1906-05-06T11:08:27.594Z",
            beijing_time="1906-05-06T19:08:27.594",
            local_basis_time="1906-05-06T19:08:27.594",
            gender=None,
            decade_count=1,
        )
        coincident = engine.run_node(coincident_request)

        def clear_only_one_lunar_guard(item: dict) -> None:
            review = item["cases"][1]["lunar_date_beijing_frame"][
                "boundary_uncertainty"
            ]
            review.update({
                "status": "CLEAR",
                "codes": [],
                "affects_this_nominal_date": False,
                "reverse_conversion_blocked": False,
                "unresolved_result_change_without_enumerated_variant": False,
                "events": [],
                "hko_authority_divergences": [],
            })

        self.assert_core_mutation_rejected(
            coincident, coincident_request, clear_only_one_lunar_guard
        )

    def test_extreme_numeric_input_is_an_input_error_and_result_ids_are_full_hashes(
        self,
    ) -> None:
        with self.assertRaises(engine.InputContractError):
            engine.strict_number(10**400, "birth.longitude", -180, 180)
        with self.assertRaises(engine.InputContractError):
            engine.strict_json_loads("{" + '"value":' + "9" * 5000 + "}")

        payload = {
            "birth": {
                "calendar": "gregorian",
                "date": "1988-02-15",
                "time": "23:30:00",
                "timezone": "Asia/Shanghai",
            },
            "rules": {"time_basis": "civil_clock", "day_boundary": "both"},
        }
        report = engine.build_report(payload)
        identifiers = [item["result_id"] for item in report["results"]]
        self.assertTrue(all(len(identifier) == 64 for identifier in identifiers))
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_node_lunar_public_edges_and_outside_rejections(self) -> None:
        edge_cases = [
            ((1900, 11, 11, False), "1901-01-01T12:34:56.123456"),
            ((2033, 11, 10, True), "2033-12-31T12:34:56.123456"),
        ]
        for lunar, expected_solar in edge_cases:
            with self.subTest(lunar=lunar):
                completed, response = run_node_core(lunar_request(*lunar))
                self.assertEqual(0, completed.returncode)
                self.assertTrue(response["ok"])
                self.assertEqual(
                    expected_solar,
                    response["conversion"]["beijing_reference_solar_time"],
                )
                self.assertFalse(
                    response["conversion"]["boundary_uncertainty"]["reverse_conversion_blocked"]
                )

        for lunar in ((1900, 11, 10, False), (2033, 11, 11, True)):
            with self.subTest(outside_lunar=lunar):
                completed, response = run_node_core(lunar_request(*lunar))
                self.assertNotEqual(0, completed.returncode)
                self.assertFalse(response["ok"])
                self.assertEqual("input", response["error"]["kind"])
                self.assertEqual(
                    "LUNAR_DATE_OUTSIDE_GREGORIAN_COVERAGE",
                    response["error"]["code"],
                )

    def test_node_lunar_fail_closed_codes_and_review_only_case(self) -> None:
        blocked = [
            ((1914, 10, 1, False), "HISTORICAL_CALENDAR_AUTHORITY_DIVERGENCE"),
            ((1906, 4, 1, False), "LUNAR_BOUNDARY_MODEL_GUARD"),
            # The nominal month has 29 days, but its guarded end new moon can
            # move one day later; day 30 must fail closed, not be called invalid.
            ((1924, 1, 30, False), "LUNAR_BOUNDARY_MODEL_GUARD"),
        ]
        for lunar, expected_code in blocked:
            with self.subTest(lunar=lunar):
                completed, response = run_node_core(lunar_request(*lunar))
                self.assertNotEqual(0, completed.returncode)
                self.assertEqual({"ok", "error"}, set(response))
                self.assertFalse(response["ok"])
                self.assertEqual("input", response["error"]["kind"])
                self.assertEqual(expected_code, response["error"]["code"])

        completed, response = run_node_core(lunar_request(1978, 8, 1, False))
        self.assertEqual(0, completed.returncode)
        self.assertEqual(
            "1978-09-03T12:34:56.123456",
            response["conversion"]["beijing_reference_solar_time"],
        )
        uncertainty = response["conversion"]["boundary_uncertainty"]
        self.assertEqual("REVIEW_ONLY", uncertainty["status"])
        self.assertEqual(["NEAR_MIDNIGHT_REVIEW"], uncertainty["codes"])
        self.assertFalse(uncertainty["affects_this_nominal_date"])
        self.assertFalse(uncertainty["reverse_conversion_blocked"])
        self.assertFalse(
            uncertainty["unresolved_result_change_without_enumerated_variant"]
        )
        self.assertEqual(2, uncertainty["start_model_guard_seconds"])
        self.assertEqual("USNO_MEASURED", uncertainty["start_delta_t_source_code"])
        self.assertEqual(
            "TT_MINUS_FROZEN_DELTAT_AS_UT1_PROXY",
            uncertainty["start_time_scale"],
        )
        self.assertFalse(uncertainty["events"][0]["changes_calendar_assignment"])

    def test_node_dayun_provider_fixtures(self) -> None:
        expected = {
            "default": (
                {"years": 3, "months": 1, "days": 29, "hours": 23, "minutes": 8},
                "1993-07-15T13:43:00",
            ),
            "china95": (
                {"years": 3, "months": 1, "days": 29, "hours": 0, "minutes": 0},
                "1993-07-14T14:35:00",
            ),
            "lunar_sect1": (
                {"years": 3, "months": 2, "days": 0, "hours": 0, "minutes": 0},
                "1993-07-15T14:35:00",
            ),
            "lunar_sect2": (
                {"years": 3, "months": 1, "days": 29, "hours": 22, "minutes": 0},
                "1993-07-15T12:35:00",
            ),
        }
        for provider, (interval, symbolic_start) in expected.items():
            with self.subTest(provider=provider):
                completed, response = run_node_core(chart_request(
                    gender="woman", provider=provider
                ))
                self.assertEqual(0, completed.returncode)
                dayun = response["cases"][0]["dayun"]
                self.assertEqual(provider, dayun["provider"])
                self.assertEqual("backward", dayun["direction"])
                self.assertEqual(interval, dayun["interval"])
                self.assertEqual(
                    symbolic_start,
                    dayun["symbolic_start_beijing_time_under_provider"],
                )
                self.assertEqual(
                    ["庚辰", "己卯", "戊寅"],
                    [d["ganzhi"] for d in dayun["decades"]],
                )
                self.assertEqual("立夏", dayun["selected_jie"]["name"])
                self.assertEqual(2, dayun["selected_jie"]["model_guard_seconds"])
                self.assertEqual(
                    "USNO_MEASURED",
                    dayun["selected_jie"]["delta_t_source_code"],
                )
                self.assertEqual(
                    "TT_MINUS_FROZEN_DELTAT_AS_UT1_PROXY",
                    dayun["selected_jie"]["time_scale"],
                )

    def test_node_fractional_basis_and_absolute_beijing_consistency(self) -> None:
        payload = chart_request(
            case_id="fractional",
            absolute_utc="2024-06-01T04:00:00.123456Z",
            beijing_time="2024-06-01T12:00:00.123456",
            local_basis_time="2024-06-01T11:59:59.654321",
            time_basis="local_apparent_solar",
            decade_count=1,
        )
        completed, response = run_node_core(payload)
        self.assertEqual(0, completed.returncode)
        self.assertEqual("xuanshu-four-pillars-core-response-v0.2", response["schema_version"])
        self.assertEqual("charts", response["mode"])
        case = response["cases"][0]
        self.assertEqual("fractional", case["id"])
        self.assertEqual("fractional", case["source_case_id"])
        self.assertEqual(
            {
                "absolute_utc": "2024-06-01T04:00:00.123456Z",
                "beijing_calendar_frame": "2024-06-01T12:00:00.123456",
                "local_basis": "2024-06-01T11:59:59.654321",
            },
            case["normalized_times"],
        )

        payload["cases"][0]["beijing_time"] = "2024-06-01T12:00:00.123455"
        completed, response = run_node_core(payload)
        self.assertNotEqual(0, completed.returncode)
        self.assertEqual("input", response["error"]["kind"])
        self.assertEqual(
            "INCONSISTENT_ABSOLUTE_AND_BEIJING_TIME",
            response["error"]["code"],
        )

    def test_node_term_model_guard_enumerates_calendar_variants(self) -> None:
        payload = chart_request(
            case_id="near-lichun",
            absolute_utc="1910-02-04T16:29:02.210Z",
            beijing_time="1910-02-05T00:29:02.210",
            local_basis_time="1910-02-05T00:29:02.210000",
            gender="woman",
            decade_count=2,
        )
        completed, response = run_node_core(payload)
        self.assertEqual(0, completed.returncode, completed.stderr.decode("utf-8"))
        self.assertEqual(2, len(response["cases"]))
        self.assertEqual(2, len({case["id"] for case in response["cases"]}))
        self.assertEqual({"near-lichun"}, {
            case["source_case_id"] for case in response["cases"]
        })
        by_state = {
            case["calendar_model_variant"]["state"]: case
            for case in response["cases"]
        }
        self.assertEqual({"birth_before_term", "birth_after_term"}, set(by_state))
        self.assertEqual(
            ("己酉", "丁丑", "forward"),
            (
                by_state["birth_before_term"]["chart"]["year"]["ganzhi"],
                by_state["birth_before_term"]["chart"]["month"]["ganzhi"],
                by_state["birth_before_term"]["dayun"]["direction"],
            ),
        )
        self.assertEqual(
            ("庚戌", "戊寅", "backward"),
            (
                by_state["birth_after_term"]["chart"]["year"]["ganzhi"],
                by_state["birth_after_term"]["chart"]["month"]["ganzhi"],
                by_state["birth_after_term"]["dayun"]["direction"],
            ),
        )
        self.assertEqual(
            ("大寒", "立春"),
            (
                by_state["birth_before_term"]["solar_terms"]["previous_or_current"]["name"],
                by_state["birth_before_term"]["solar_terms"]["next"]["name"],
            ),
        )
        self.assertEqual(
            ("立春", "雨水"),
            (
                by_state["birth_after_term"]["solar_terms"]["previous_or_current"]["name"],
                by_state["birth_after_term"]["solar_terms"]["next"]["name"],
            ),
        )
        for state, case in by_state.items():
            uncertainty = case["solar_term_boundary_uncertainty"]
            self.assertEqual("ENUMERATED_CALENDAR_MODEL_VARIANTS", uncertainty["status"])
            self.assertFalse(
                uncertainty["unresolved_result_change_without_enumerated_variant"]
            )
            self.assertEqual(2, uncertainty["enumerated_variant_count"])
            self.assertEqual(state, uncertainty["calendar_model_variant_state"])
            event = uncertainty["events"][0]
            self.assertEqual("立春", event["name"])
            self.assertEqual(600, event["model_guard_seconds"])
            self.assertEqual("NASA_PRE1973", event["delta_t_source_code"])
            self.assertEqual(
                "TT_MINUS_FROZEN_DELTAT_AS_UT1_PROXY", event["time_scale"]
            )
            self.assertEqual("立春", case["dayun"]["selected_jie"]["name"])

    def test_node_accepts_public_date_edge_calendar_frames(self) -> None:
        edge_frames = [
            (
                "left-frame", "1900-12-31T10:00:00Z",
                "1900-12-31T18:00:00", "1900-12-31T23:59:59.123456",
            ),
            (
                "right-frame", "2034-01-01T11:00:00Z",
                "2034-01-01T19:00:00", "2034-01-01T00:00:00.123456",
            ),
        ]
        for case_id, absolute, beijing, basis in edge_frames:
            with self.subTest(case_id=case_id):
                completed, response = run_node_core(chart_request(
                    case_id=case_id,
                    absolute_utc=absolute,
                    beijing_time=beijing,
                    local_basis_time=basis,
                    time_basis="local_apparent_solar",
                    decade_count=1,
                ))
                self.assertEqual(0, completed.returncode, completed.stderr.decode("utf-8"))
                self.assertTrue(response["ok"])
                self.assertEqual(case_id, response["cases"][0]["source_case_id"])

    def test_calendar_dataset_v02_shape_sources_and_segment_diagnostics(self) -> None:
        dataset = json.loads(CALENDAR_DATA.read_text(encoding="utf-8"))
        self.assertEqual("xuanshu-calendar-data-v0.2", dataset["schema_version"])
        self.assertEqual("jpl-de440s-skyfield-1.54-v1", dataset["calendar_core_version"])
        self.assertEqual(3244, len(dataset["terms"]))
        self.assertEqual(1657, len(dataset["lunar_months"]))
        self.assertTrue(all(len(row) == 4 for row in dataset["terms"]))
        self.assertTrue(all(len(row) == 10 for row in dataset["lunar_months"]))
        self.assertEqual(
            {
                "0": "NASA_PRE1973",
                "1": "USNO_MEASURED",
                "2": "USNO_PREDICTED",
                "3": "CONTINUOUS_LINEAR_SCENARIO",
            },
            dataset["encoding"]["delta_t_source_codes"],
        )
        used_source_codes = {row[3] for row in dataset["terms"]} | {
            row[8] for row in dataset["lunar_months"]
        }
        self.assertEqual({0, 1, 2, 3}, used_source_codes)

        diagnostics = dataset["uncertainty"]["delta_t_segment_boundary_diagnostics"]
        expected_jumps = {
            "nasa_to_usno_measured": (41714, 0.07010179, 0.2),
            "usno_measured_to_predicted": (61131, -0.043439559, 0.1),
            "usno_predicted_to_linear_scenario": (63871, 0.000000002, 0.00001),
        }
        for name, (boundary_mjd, signed_jump, maximum) in expected_jumps.items():
            with self.subTest(segment=name):
                actual = diagnostics[name]
                self.assertEqual(boundary_mjd, actual["boundary_mjd"])
                self.assertAlmostEqual(signed_jump, actual["signed_jump_seconds"], places=12)
                self.assertEqual(maximum, actual["asserted_max_abs_jump_seconds"])
                self.assertAlmostEqual(
                    actual["right_seconds"] - actual["left_seconds"],
                    actual["signed_jump_seconds"],
                    places=9,
                )
                self.assertLessEqual(abs(actual["signed_jump_seconds"]), maximum)
        scenario = dataset["sources"]["delta_t_context_scenario"]
        self.assertEqual("SCENARIO_NOT_PREDICTION", scenario["status"])
        self.assertEqual(0.364, scenario["start"]["slope_seconds_per_year"])

    def test_traditional_rule_registry_is_fixed_and_unique(self) -> None:
        identity = engine.load_manifest_identity()
        self.assertEqual(
            {"rule_registry", "provider_manifest", "provenance_manifest"}, set(identity)
        )
        registry = json.loads(
            (SCRIPT_DIR.parent / "references" / "rule-registry.json").read_text(encoding="utf-8")
        )
        identifiers = [item["rule_id"] for item in registry["rules"]]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertGreater(len(identifiers), 0)
        self.assertFalse(registry["policy"]["runtime_rule_ids_may_be_invented"])
        self.assertTrue(all(item["source"].get("revision_id") for item in registry["rules"]))

    def test_day_pillar_repeats_after_sixty_days(self) -> None:
        def day_pillar(day: str) -> str:
            report = engine.build_report({
                "birth": {
                    "calendar": "gregorian", "date": day, "time": "12:00",
                    "timezone": "Asia/Shanghai",
                },
                "rules": {"time_basis": "civil_clock", "day_boundary": "zi_initial_next_day"},
            })
            return report["results"][0]["chart"]["day"]["ganzhi"]

        self.assertEqual("甲子", day_pillar("2000-01-07"))
        self.assertEqual("乙丑", day_pillar("2000-01-08"))
        self.assertEqual(day_pillar("2000-01-07"), day_pillar("2000-03-07"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
