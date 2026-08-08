from __future__ import annotations

import ast
import bisect
import hashlib
import json
import os
import re
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "analyze-four-pillars-rigorously"
PLUGIN_MANIFEST = ROOT / ".codex-plugin" / "plugin.json"
MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"
SCRIPTS = SKILL / "scripts"
NODE_CORE = SCRIPTS / "four_pillars_core.js"
CALENDAR_DATA = SCRIPTS / "data" / "calendar-1901-2033.json"
GENERATOR = ROOT / "tools" / "generate_calendar_data.py"
BUILD_REQUIREMENTS = ROOT / "tools" / "calendar-build-requirements.txt"

EXPECTED_ARTIFACT_SHA256 = {
    NODE_CORE: "8b3cb09cd9468ab9bfb6c199c58fd053f1e025fca2ac059fe7ee846755773655",
    CALENDAR_DATA: "65189952013b9471e6a0e8a63109ce6305d6242588ec6e3fabdb8ddd0bdd4509",
    GENERATOR: "6f30b0579347cedfade4077e407dfaabd94f9819125c61d89bd2c014fc735405",
    BUILD_REQUIREMENTS: "6cfa326d743d96c47739eedd1acafb642ce0abdb4dc91d256d05755e8908f4d8",
}


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def run_node_core(request: object | bytes) -> tuple[subprocess.CompletedProcess[bytes], dict[str, Any]]:
    payload = request if isinstance(request, bytes) else canonical_json(request)
    completed = subprocess.run(
        ["node", str(NODE_CORE)],
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=15,
    )
    raw = completed.stdout if completed.returncode == 0 else completed.stderr
    if not raw.strip():
        raise AssertionError(
            f"Node core returned no JSON (exit {completed.returncode}); "
            f"stdout={completed.stdout!r}; stderr={completed.stderr!r}"
        )
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


def guarded_lichun_request() -> dict[str, object]:
    return {
        "mode": "charts",
        "gender": "woman",
        "child_limit_provider": "default",
        "decade_count": 2,
        "cases": [{
            "id": "near-lichun",
            "label": "near-lichun",
            "absolute_utc": "1910-02-04T16:29:02.210Z",
            "beijing_time": "1910-02-05T00:29:02.210",
            "local_basis_time": "1910-02-05T00:29:02.210000",
            "time_basis": "civil_clock",
            "day_boundary": "zi_initial_next_day",
            "scenario_kind": "input_candidate",
        }],
    }


class RepositoryTests(unittest.TestCase):
    def test_legacy_latin_alias_is_absent_from_release_tree(self) -> None:
        forbidden = bytes((98, 97, 122, 105))
        matches: list[str] = []
        for path in ROOT.rglob("*"):
            relative = path.relative_to(ROOT)
            if ".git" in relative.parts:
                continue
            encoded_path = relative.as_posix().encode("utf-8").lower()
            if forbidden in encoded_path:
                matches.append(relative.as_posix())
            if path.is_file() and forbidden in path.read_bytes().lower():
                matches.append(relative.as_posix() + ":content")
        self.assertEqual([], sorted(matches))

    def test_required_skill_and_clean_core_files_exist(self) -> None:
        required = [
            PLUGIN_MANIFEST,
            MARKETPLACE,
            SKILL / "SKILL.md",
            SKILL / "agents" / "openai.yaml",
            SCRIPTS / "four_pillars_engine.py",
            NODE_CORE,
            CALENDAR_DATA,
            SCRIPTS / "self_test.py",
            SCRIPTS / "vendor" / "LICENSE-tyme4ts",
            SKILL / "references" / "rule-registry.json",
            SKILL / "references" / "provider-manifest.json",
            SKILL / "references" / "provenance-manifest.json",
            GENERATOR,
            BUILD_REQUIREMENTS,
        ]
        for path in required:
            self.assertTrue(path.is_file(), path)

    def test_plugin_manifest_and_marketplace_contract(self) -> None:
        manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual("xuanshu-four-pillars", manifest["name"])
        self.assertEqual("0.1.0", manifest["version"])
        self.assertEqual("MIT", manifest["license"])
        self.assertEqual(
            "https://github.com/dupuisgreenlun264-jpg/xuanshu-four-pillars-skill",
            manifest["repository"],
        )
        self.assertEqual("./skills/", manifest["skills"])
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("apps", manifest)
        self.assertNotIn("hooks", manifest)

        skills_root = (ROOT / manifest["skills"]).resolve()
        self.assertTrue(skills_root.is_relative_to(ROOT.resolve()))
        self.assertTrue((skills_root / "analyze-four-pillars-rigorously" / "SKILL.md").is_file())

        interface = manifest["interface"]
        self.assertEqual("玄枢·严谨四柱", interface["displayName"])
        self.assertEqual("Productivity", interface["category"])
        self.assertRegex(interface["brandColor"], r"^#[0-9A-Fa-f]{6}$")
        self.assertGreaterEqual(len(interface["defaultPrompt"]), 3)
        self.assertIn("开发验证版", interface["longDescription"])
        self.assertIn("不提供经科学验证的人生预测", interface["longDescription"])

        marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
        self.assertEqual("xuanshu-plugins", marketplace["name"])
        self.assertEqual(1, len(marketplace["plugins"]))
        entry = marketplace["plugins"][0]
        self.assertEqual(manifest["name"], entry["name"])
        self.assertEqual(interface["category"], entry["category"])
        self.assertEqual(
            {
                "source": "url",
                "url": "https://github.com/dupuisgreenlun264-jpg/xuanshu-four-pillars-skill",
                "ref": "main",
            },
            entry["source"],
        )
        self.assertEqual(
            {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            entry["policy"],
        )

    def test_frozen_clean_core_artifact_hashes(self) -> None:
        for path, expected in EXPECTED_ARTIFACT_SHA256.items():
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertEqual(expected, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_generator_is_parseable_without_importing_build_dependencies(self) -> None:
        # Parsing rather than importing keeps the release test offline and proves
        # the generator itself does not need to be executed at runtime.
        ast.parse(GENERATOR.read_text(encoding="utf-8"), filename=str(GENERATOR))
        build_guide = (ROOT / "tools" / "README.md").read_text(encoding="utf-8")
        self.assertIn("regeneration requires Python 3.12 or newer", build_guide)
        self.assertIn("runtime, which supports Python 3.11 or newer", build_guide)

    def test_legacy_runtime_build_inputs_raw_or_cache_files_are_not_distributed(self) -> None:
        forbidden_directory_names = {
            "__pycache__",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "node_modules",
        }
        forbidden_files: list[str] = []
        for path in ROOT.rglob("*"):
            relative = path.relative_to(ROOT)
            if ".git" in relative.parts:
                continue
            if path.is_dir() and path.name in forbidden_directory_names:
                forbidden_files.append(relative.as_posix() + "/")
                continue
            if not path.is_file():
                continue
            lowered = path.name.lower()
            if (
                lowered.startswith("tyme4ts-") and lowered.endswith(".cjs")
                or path.suffix.lower() in {".bsp", ".pyc", ".pyo"}
                or lowered in {"deltat.data", "deltat.preds"}
                or re.fullmatch(r"t\d{4}e\.txt", lowered) is not None
            ):
                forbidden_files.append(relative.as_posix())
        self.assertEqual([], sorted(forbidden_files))

        for runtime_source in (NODE_CORE, SCRIPTS / "four_pillars_engine.py"):
            text = runtime_source.read_text(encoding="utf-8").lower()
            self.assertNotIn("tyme4ts", text, runtime_source)
            self.assertNotIn("sxwnl", text, runtime_source)

    def test_calendar_dataset_schema_counts_coverage_and_encoding(self) -> None:
        dataset = json.loads(CALENDAR_DATA.read_text(encoding="utf-8"))
        self.assertEqual("xuanshu-calendar-data-v0.2", dataset["schema_version"])
        self.assertEqual("jpl-de440s-skyfield-1.54-v1", dataset["calendar_core_version"])
        self.assertEqual(
            {
                "calendar_day_boundary": "fixed_UTC+08:00",
                "event_time_scale": "TT_minus_frozen_DeltaT_as_UT1_proxy_for_UTC",
                "month_rule": "month_11_contains_winter_solstice; first_no-major-term_month_is_leap",
                "term_longitude": "geocentric_apparent_ecliptic_of_date",
            },
            dataset["frame"],
        )

        coverage = dataset["coverage"]
        expected_coverage = {
            "supported_gregorian_year_min": 1901,
            "supported_gregorian_year_max": 2033,
            "public_solar_start": "1901-01-01",
            "public_solar_end": "2033-12-31",
            "lunar_label_year_envelope_min": 1900,
            "lunar_label_year_envelope_max": 2033,
            "context_events_from": "1900-01-01",
            "context_events_through": "2035-02-28",
            "first_nominal_lunar_label": {
                "year": 1900, "month": 11, "day": 11, "leap_month": False,
            },
            "last_nominal_lunar_label": {
                "year": 2033, "month": 11, "day": 10, "leap_month": True,
            },
        }
        for field, expected in expected_coverage.items():
            self.assertEqual(expected, coverage[field], field)
        self.assertIn("partial", coverage["lunar_label_edge_policy"])

        encoding = dataset["encoding"]
        self.assertEqual(
            {
                "0": "NASA_PRE1973",
                "1": "USNO_MEASURED",
                "2": "USNO_PREDICTED",
                "3": "CONTINUOUS_LINEAR_SCENARIO",
            },
            encoding["delta_t_source_codes"],
        )
        self.assertEqual(24, len(encoding["term_names_by_index"]))
        self.assertEqual(4, len(encoding["terms"]))
        self.assertEqual(10, len(encoding["lunar_months"]))
        self.assertEqual(9, len(encoding["lunar_uncertainty_events"]))

        terms = dataset["terms"]
        months = dataset["lunar_months"]
        events = dataset["lunar_uncertainty_events"]
        self.assertEqual(3244, len(terms))
        self.assertEqual(1657, len(months))
        self.assertEqual(77, len(events))
        self.assertTrue(all(len(row) == 4 for row in terms))
        self.assertTrue(all(len(row) == 10 for row in months))
        self.assertTrue(all(len(row) == 9 for row in events))
        self.assertTrue(all(left[0] < right[0] for left, right in zip(terms, terms[1:])))
        self.assertEqual(set(range(24)), {row[1] for row in terms})
        self.assertEqual({0, 1, 2, 3}, {row[3] for row in terms})
        self.assertTrue(all(row[2] >= 0 for row in terms))

        labels = [(row[1], row[2], row[3]) for row in months]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertTrue(all(row[4] in (29, 30) for row in months))
        self.assertEqual({0, 1, 2, 3}, {row[8] for row in months})
        self.assertTrue(all(
            current[0] + current[4] == following[0]
            for current, following in zip(months, months[1:])
        ))
        self.assertTrue(all(row[7] >= 0 and row[9] >= 0 for row in months))

        public_start_day = (date(1901, 1, 1) - date(1970, 1, 1)).days
        public_end_day = (date(2033, 12, 31) - date(1970, 1, 1)).days
        starts = [row[0] for row in months]
        first_row = months[bisect.bisect_right(starts, public_start_day) - 1]
        last_row = months[bisect.bisect_right(starts, public_end_day) - 1]
        self.assertEqual(
            (1900, 11, 0, 11),
            (first_row[1], first_row[2], first_row[3], public_start_day - first_row[0] + 1),
        )
        self.assertEqual(
            (2033, 11, 1, 10),
            (last_row[1], last_row[2], last_row[3], public_end_day - last_row[0] + 1),
        )

        for row in events:
            self.assertIn(row[1], range(4))
            self.assertIn(row[3], range(-1, 24))
            self.assertGreaterEqual(row[4], 0)
            self.assertGreaterEqual(row[5], 0)
            self.assertIn(row[6], range(4))
            self.assertIn(row[7], (0, 1))
            self.assertIn(row[8], (-1, 0, 1))

    def test_calendar_dataset_validation_facts_and_uncertainty_counts(self) -> None:
        dataset = json.loads(CALENDAR_DATA.read_text(encoding="utf-8"))
        facts = dataset["validation_facts"]
        self.assertEqual(48_578, facts["compared_gregorian_day_rows_1901_2033"])
        self.assertEqual(3, len(facts["historical_month_start_date_divergences"]))
        self.assertEqual(3, len({
            item["nominal_month_start_beijing_date"]
            for item in facts["historical_month_start_date_divergences"]
        }))
        self.assertEqual(3_192, facts["compared_solar_term_rows_1901_2033"])
        self.assertEqual(6, len(facts["solar_term_date_divergences"]))
        self.assertEqual(
            "local_validation_only; not a generation input; no source text redistributed",
            facts["oracle_role"].replace("a_generation", "a generation"),
        )

        uncertainty = dataset["uncertainty"]
        self.assertEqual(27, uncertainty["near_midnight_new_moon_count_1901_2033"])
        self.assertEqual(38, uncertainty["near_midnight_term_count_1901_2033"])
        self.assertFalse(uncertainty["per_event_model_guard_is_certified_error_bound"])
        self.assertEqual(
            {
                "historical_divergence": 6,
                "historical_term_date_divergence_audit": 4,
                "major_term_within_600s_review": 23,
                "model_guard_changes_calendar_date_or_membership": 26,
                "new_moon_within_600s_review": 54,
            },
            uncertainty["flagged_lunar_month_rows"],
        )

    def test_node_core_strict_errors_are_machine_readable_and_fail_closed(self) -> None:
        duplicate_id_request = guarded_lichun_request()
        duplicate_id_request["cases"] = [
            duplicate_id_request["cases"][0],
            dict(duplicate_id_request["cases"][0]),
        ]
        inconsistent = guarded_lichun_request()
        inconsistent["cases"][0]["beijing_time"] = "1910-02-05T00:29:02.211"
        unknown_field = lunar_request(2019, 12, 12, False)
        unknown_field["unrecognized"] = True

        vectors: list[tuple[object | bytes, str]] = [
            (b"{not-json", "INVALID_JSON"),
            (b"\xff", "INVALID_UTF8"),
            ([], "INVALID_CORE_REQUEST"),
            (unknown_field, "INVALID_CORE_REQUEST"),
            (duplicate_id_request, "INVALID_CORE_REQUEST"),
            (inconsistent, "INCONSISTENT_ABSOLUTE_AND_BEIJING_TIME"),
        ]
        for request, expected_code in vectors:
            with self.subTest(code=expected_code, request=repr(request)[:100]):
                completed, response = run_node_core(request)
                self.assertNotEqual(0, completed.returncode)
                self.assertEqual(b"", completed.stdout)
                self.assertEqual({"ok", "error"}, set(response))
                self.assertFalse(response["ok"])
                self.assertEqual("input", response["error"]["kind"])
                self.assertEqual(expected_code, response["error"]["code"])
                self.assertIsInstance(response["error"]["message"], str)
                self.assertTrue(response["error"]["message"])

    def test_node_core_lunar_public_edges_and_stable_guard_codes(self) -> None:
        accepted = [
            ((1900, 11, 11, False), "1901-01-01T12:34:56.123456"),
            ((2033, 11, 10, True), "2033-12-31T12:34:56.123456"),
        ]
        for lunar, expected_solar in accepted:
            with self.subTest(lunar=lunar):
                completed, response = run_node_core(lunar_request(*lunar))
                self.assertEqual(0, completed.returncode, completed.stderr.decode("utf-8"))
                self.assertEqual(b"", completed.stderr)
                self.assertTrue(response["ok"])
                self.assertEqual("xuanshu-four-pillars-core-response-v0.2", response["schema_version"])
                self.assertEqual("convert_lunar", response["mode"])
                self.assertEqual(expected_solar, response["conversion"]["beijing_reference_solar_time"])
                self.assertEqual(
                    EXPECTED_ARTIFACT_SHA256[NODE_CORE],
                    response["engine"]["node_core_sha256"],
                )
                self.assertEqual(
                    EXPECTED_ARTIFACT_SHA256[CALENDAR_DATA],
                    response["engine"]["calendar_dataset_sha256"],
                )

        rejected = [
            ((1900, 11, 10, False), "LUNAR_DATE_OUTSIDE_GREGORIAN_COVERAGE"),
            ((2033, 11, 11, True), "LUNAR_DATE_OUTSIDE_GREGORIAN_COVERAGE"),
            ((1914, 10, 1, False), "HISTORICAL_CALENDAR_AUTHORITY_DIVERGENCE"),
            ((1906, 4, 1, False), "LUNAR_BOUNDARY_MODEL_GUARD"),
        ]
        for lunar, expected_code in rejected:
            with self.subTest(lunar=lunar, code=expected_code):
                completed, response = run_node_core(lunar_request(*lunar))
                self.assertNotEqual(0, completed.returncode)
                self.assertEqual("input", response["error"]["kind"])
                self.assertEqual(expected_code, response["error"]["code"])

    def test_node_core_guarded_jie_enumerates_two_chart_and_dayun_states(self) -> None:
        completed, response = run_node_core(guarded_lichun_request())
        self.assertEqual(0, completed.returncode, completed.stderr.decode("utf-8"))
        self.assertTrue(response["ok"])
        self.assertEqual("xuanshu-four-pillars-core-response-v0.2", response["schema_version"])
        self.assertEqual("charts", response["mode"])
        self.assertEqual(2, len(response["cases"]))
        self.assertEqual(2, len({case["id"] for case in response["cases"]}))
        self.assertEqual({"near-lichun"}, {case["source_case_id"] for case in response["cases"]})

        by_state = {
            case["calendar_model_variant"]["state"]: case
            for case in response["cases"]
        }
        self.assertEqual({"birth_before_term", "birth_after_term"}, set(by_state))
        expected = {
            "birth_before_term": {
                "year": "己酉", "month": "丁丑", "direction": "forward",
                "previous": "大寒", "next": "立春", "first_decade": "戊寅",
            },
            "birth_after_term": {
                "year": "庚戌", "month": "戊寅", "direction": "backward",
                "previous": "立春", "next": "雨水", "first_decade": "丁丑",
            },
        }
        for state, case in by_state.items():
            with self.subTest(state=state):
                wanted = expected[state]
                self.assertEqual(wanted["year"], case["chart"]["year"]["ganzhi"])
                self.assertEqual(wanted["month"], case["chart"]["month"]["ganzhi"])
                self.assertEqual(wanted["direction"], case["dayun"]["direction"])
                self.assertEqual(wanted["first_decade"], case["dayun"]["decades"][0]["ganzhi"])
                self.assertEqual("立春", case["dayun"]["selected_jie"]["name"])
                self.assertEqual(wanted["previous"], case["solar_terms"]["previous_or_current"]["name"])
                self.assertEqual(wanted["next"], case["solar_terms"]["next"]["name"])

                uncertainty = case["solar_term_boundary_uncertainty"]
                self.assertEqual("ENUMERATED_CALENDAR_MODEL_VARIANTS", uncertainty["status"])
                self.assertEqual(2, uncertainty["enumerated_variant_count"])
                self.assertEqual(state, uncertainty["calendar_model_variant_state"])
                self.assertFalse(uncertainty["unresolved_result_change_without_enumerated_variant"])
                event = uncertainty["events"][0]
                self.assertEqual("立春", event["name"])
                self.assertEqual(600, event["model_guard_seconds"])
                self.assertEqual("NASA_PRE1973", event["delta_t_source_code"])
                self.assertEqual("TT_MINUS_FROZEN_DELTAT_AS_UT1_PROXY", event["time_scale"])

    def test_frontmatter_and_placeholders(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: analyze-four-pillars-rigorously\n"))
        self.assertIn("\ndescription:", text.split("---", 2)[1])
        self.assertNotIn("TODO", text)

    def test_markdown_local_links(self) -> None:
        pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
        broken: list[str] = []
        for document in ROOT.rglob("*.md"):
            text = document.read_text(encoding="utf-8")
            for raw_target in pattern.findall(text):
                target = raw_target.strip().split("#", 1)[0]
                if not target or "://" in target or target.startswith(("mailto:", "#")):
                    continue
                if not (document.parent / target).resolve().exists():
                    broken.append(f"{document.relative_to(ROOT)} -> {raw_target}")
        self.assertEqual([], broken)

    def test_release_version_consistency(self) -> None:
        version = "0.1.0"
        expected = {
            PLUGIN_MANIFEST: f'"version": "{version}"',
            ROOT / "README.md": f"当前版本：`{version}`",
            ROOT / "CHANGELOG.md": f"## {version}",
            ROOT / "NOTICE": f"Xuanshu Four Pillars Skill {version}",
            ROOT / "docs" / "VALIDATION.md": f"release: {version}",
            SCRIPTS / "four_pillars_engine.py": f'ENGINE_VERSION = "{version}"',
            NODE_CORE: f"const ENGINE_VERSION = '{version}'",
        }
        for path, marker in expected.items():
            self.assertIn(marker, path.read_text(encoding="utf-8"), path)

    def test_ci_actions_are_sha_pinned(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        references = re.findall(r"uses:\s*([^\s#]+)", workflow)
        self.assertGreaterEqual(len(references), 3)
        for reference in references:
            self.assertRegex(reference, r"^[^@]+@[0-9a-f]{40}$")

    def test_machine_readable_manifests(self) -> None:
        for name in ("rule-registry.json", "provider-manifest.json", "provenance-manifest.json"):
            value = json.loads((SKILL / "references" / name).read_text(encoding="utf-8"))
            self.assertIn("schema_version", value, name)
        registry = json.loads(
            (SKILL / "references" / "rule-registry.json").read_text(encoding="utf-8")
        )
        identifiers = [item["rule_id"] for item in registry["rules"]]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_examples_execute_without_writing_bytecode(self) -> None:
        engine = SCRIPTS / "four_pillars_engine.py"
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        for example in sorted((ROOT / "examples").glob("*.json")):
            process = subprocess.run(
                [sys.executable, "-B", str(engine), "--input", str(example)],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
                env=environment,
            )
            self.assertEqual(0, process.returncode, f"{example}: {process.stderr}")
            report = json.loads(process.stdout)
            self.assertIsInstance(report, dict, example)
            self.assertIn("engine", report, example)
            self.assertIn("results", report, example)


if __name__ == "__main__":
    unittest.main(verbosity=2)
