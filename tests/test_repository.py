from __future__ import annotations

import ast
import bisect
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from typing import Any
from unittest import mock

import tools.build_plugin_archive as plugin_builder


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "analyze-four-pillars-rigorously"
PLUGIN_MANIFEST = ROOT / ".codex-plugin" / "plugin.json"
MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"
SCRIPTS = SKILL / "scripts"
NODE_CORE = SCRIPTS / "four_pillars_core.js"
CALENDAR_DATA = SCRIPTS / "data" / "calendar-1901-2033.json"
GENERATOR = ROOT / "tools" / "generate_calendar_data.py"
BUILD_REQUIREMENTS = ROOT / "tools" / "calendar-build-requirements.txt"
ARCHIVE_BUILDER = ROOT / "tools" / "build_plugin_archive.py"
TZDATA_MANIFEST_GENERATOR = ROOT / "tools" / "generate_tzdata_manifest.py"
TZDATA_BUNDLE = SCRIPTS / "vendor" / "tzdata-2026.3"
TZDATA_ROOT = TZDATA_BUNDLE / "zoneinfo"
TZDATA_MANIFEST = TZDATA_BUNDLE / "MANIFEST.json"

EXPECTED_ARTIFACT_SHA256 = {
    NODE_CORE: "8b3cb09cd9468ab9bfb6c199c58fd053f1e025fca2ac059fe7ee846755773655",
    CALENDAR_DATA: "65189952013b9471e6a0e8a63109ce6305d6242588ec6e3fabdb8ddd0bdd4509",
    GENERATOR: "6f30b0579347cedfade4077e407dfaabd94f9819125c61d89bd2c014fc735405",
    BUILD_REQUIREMENTS: "6cfa326d743d96c47739eedd1acafb642ce0abdb4dc91d256d05755e8908f4d8",
    TZDATA_MANIFEST_GENERATOR: "3d25f365817e054f0cc10fe9ea2d2467dfd58c723424268e30185a741df76cd8",
    TZDATA_MANIFEST: "623879126f592375003fac137d7940dbd41b55b2e2972e1586f7680ba03efa1f",
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
            if relative.parts and relative.parts[0] in {"build", "dist", "reports"}:
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
            ARCHIVE_BUILDER,
            TZDATA_MANIFEST_GENERATOR,
            TZDATA_MANIFEST,
            TZDATA_BUNDLE / "LICENSE",
            TZDATA_BUNDLE / "LICENSE_APACHE",
        ]
        for path in required:
            self.assertTrue(path.is_file(), path)

    def test_plugin_manifest_and_marketplace_contract(self) -> None:
        manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual("xuanshu-four-pillars", manifest["name"])
        self.assertEqual("0.1.1", manifest["version"])
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
        self.assertEqual("Education & Research", interface["category"])
        self.assertRegex(interface["brandColor"], r"^#[0-9A-Fa-f]{6}$")
        self.assertRegex(interface["brandColorDark"], r"^#[0-9A-Fa-f]{6}$")
        self.assertEqual(3, len(interface["defaultPrompt"]))
        self.assertEqual(4, len(interface["capabilities"]))
        self.assertEqual(manifest["author"]["name"], interface["developerName"])
        self.assertIn("尚未独立认证", interface["longDescription"])
        self.assertIn("人生预测未获实证验证", interface["longDescription"])
        for field in ("websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL"):
            self.assertTrue(interface[field].startswith("https://"), field)
        for field in ("logo", "composerIcon"):
            asset = (ROOT / interface[field]).resolve()
            self.assertTrue(asset.is_relative_to(ROOT.resolve()))
            self.assertTrue(asset.is_file(), field)

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

    def test_public_directory_archive_is_deterministic_and_skills_only(self) -> None:
        check = subprocess.run(
            [sys.executable, str(ARCHIVE_BUILDER), "--check-only"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(0, check.returncode, check.stderr)
        self.assertTrue(check.stdout.startswith("PASS:"), check.stdout)

        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.zip"
            second = Path(directory) / "second.zip"
            for output in (first, second):
                process = subprocess.run(
                    [sys.executable, str(ARCHIVE_BUILDER), "--output", str(output)],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30,
                )
                self.assertEqual(0, process.returncode, process.stderr)
            self.assertEqual(first.read_bytes(), second.read_bytes())

            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
                extracted_bytes = sum(item.file_size for item in archive.infolist())
            self.assertEqual(1, names.count(".codex-plugin/plugin.json"))
            self.assertIn("skills/analyze-four-pillars-rigorously/SKILL.md", names)
            self.assertNotIn("requirements.txt", names)
            self.assertNotIn(".agents/plugins/marketplace.json", names)
            self.assertFalse(any(name.startswith(("docs/", "tests/", ".github/")) for name in names))

            validation = (ROOT / "docs" / "VALIDATION.md").read_text(encoding="utf-8")
            expected: dict[str, str] = {}
            for field in (
                "candidate_archive_sha256",
                "candidate_archive_compressed_bytes",
                "candidate_archive_extracted_bytes",
                "candidate_archive_entries",
            ):
                match = re.search(rf"^{field}: (\S+)$", validation, flags=re.MULTILINE)
                self.assertIsNotNone(match, field)
                expected[field] = match.group(1)

            archive_sha256 = hashlib.sha256(first.read_bytes()).hexdigest()
            compressed_bytes = first.stat().st_size
            self.assertEqual(expected["candidate_archive_sha256"], archive_sha256)
            self.assertEqual(int(expected["candidate_archive_compressed_bytes"]), compressed_bytes)
            self.assertEqual(int(expected["candidate_archive_extracted_bytes"]), extracted_bytes)
            self.assertEqual(int(expected["candidate_archive_entries"]), len(names))

            submission = (ROOT / "docs" / "PLUGIN-SUBMISSION.md").read_text(encoding="utf-8")
            self.assertIn(f"`{archive_sha256}`", submission)
            self.assertIn(f"{compressed_bytes:,} bytes", submission)
            self.assertIn(f"{extracted_bytes:,} bytes", submission)
            self.assertIn(f"| Entries | {len(names)} |", submission)

            candidate = ROOT / "dist" / "xuanshu-four-pillars-plugin-0.1.1.zip"
            if candidate.is_file():
                self.assertEqual(first.read_bytes(), candidate.read_bytes())

    def test_public_directory_preflight_rejects_mutated_skill_metadata(self) -> None:
        skill_source = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        agent_source = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        icon_source = (SKILL / "assets" / "icon.svg").read_bytes()

        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            temporary_skill = temporary_root / "skills" / SKILL.name
            (temporary_skill / "agents").mkdir(parents=True)
            (temporary_skill / "assets").mkdir()
            skill_path = temporary_skill / "SKILL.md"
            agent_path = temporary_skill / "agents" / "openai.yaml"
            skill_path.write_text(skill_source, encoding="utf-8")
            agent_path.write_text(agent_source, encoding="utf-8")
            (temporary_skill / "assets" / "icon.svg").write_bytes(icon_source)

            with (
                mock.patch.object(plugin_builder, "ROOT", temporary_root),
                mock.patch.object(plugin_builder, "SKILLS_ROOT", temporary_root / "skills"),
            ):
                self.assertEqual([SKILL.name], plugin_builder.skill_names())

                without_description = re.sub(
                    r"^description: .*\n",
                    "",
                    skill_source,
                    count=1,
                    flags=re.MULTILINE,
                )
                skill_path.write_text(without_description, encoding="utf-8")
                with self.assertRaisesRegex(plugin_builder.PreflightError, "name and description"):
                    plugin_builder.skill_names()

                invalid_yaml = re.sub(
                    r"^description: .*\n",
                    "description: [unterminated\n",
                    skill_source,
                    count=1,
                    flags=re.MULTILINE,
                )
                skill_path.write_text(invalid_yaml, encoding="utf-8")
                with self.assertRaisesRegex(plugin_builder.PreflightError, "Unsafe plain YAML scalar"):
                    plugin_builder.skill_names()

                null_description = re.sub(
                    r"^description: .*\n",
                    "description: null\n",
                    skill_source,
                    count=1,
                    flags=re.MULTILINE,
                )
                skill_path.write_text(null_description, encoding="utf-8")
                with self.assertRaisesRegex(plugin_builder.PreflightError, "Unsafe plain YAML scalar"):
                    plugin_builder.skill_names()

                skill_path.write_text(skill_source, encoding="utf-8")
                without_skill_reference = re.sub(
                    r'^  default_prompt: .+$',
                    '  default_prompt: "请生成可审计四柱报告。"',
                    agent_source,
                    count=1,
                    flags=re.MULTILINE,
                )
                agent_path.write_text(without_skill_reference, encoding="utf-8")
                with self.assertRaisesRegex(plugin_builder.PreflightError, "explicitly mention"):
                    plugin_builder.skill_names()

                agent_path.write_text(agent_source, encoding="utf-8")
                (temporary_skill / "assets" / "icon.svg").write_text(
                    '<notsvg width="64" height="64" viewBox="0 0 64 64"/>\n',
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(plugin_builder.PreflightError, "root element must be svg"):
                    plugin_builder.skill_names()

    def test_public_directory_submission_materials_have_exact_review_case_shape(self) -> None:
        submission = (ROOT / "docs" / "PLUGIN-SUBMISSION.md").read_text(encoding="utf-8")
        positives = re.findall(r"^### P[1-5] — .*?(?=^### P|^## Negative)", submission, flags=re.MULTILINE | re.DOTALL)
        negatives = re.findall(r"^### N[1-3] — .*?(?=^### N|^## Build)", submission, flags=re.MULTILINE | re.DOTALL)
        self.assertEqual(5, len(positives))
        self.assertEqual(3, len(negatives))
        for case in positives:
            self.assertIn("Prompt:", case)
            self.assertIn("Expected behavior:", case)
            self.assertIn("Expected result shape:", case)
            self.assertIn("Fixture/account:", case)
        for case in negatives:
            self.assertIn("Prompt:", case)
            self.assertIn("Expected refusal/clarification/safe fallback:", case)
            self.assertIn("Why the Plugin should not complete it:", case)
            self.assertIn("Fixture/account:", case)

        privacy = (ROOT / "docs" / "PRIVACY.md").read_text(encoding="utf-8")
        for heading in ("## Data categories", "## Recipients", "## Retention and deletion", "## User controls"):
            self.assertIn(heading, privacy)
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("finally`-equivalent cleanup", skill_text)

    def test_bundled_tzdata_manifest_covers_every_distributed_file(self) -> None:
        manifest = json.loads(TZDATA_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual("xuanshu-tzdata-bundle-v0.1", manifest["schema_version"])
        self.assertEqual("2026.3", manifest["python_distribution_version"])
        self.assertEqual("2026c", manifest["iana_database_version"])
        self.assertEqual(
            {
                "filename": "tzdata-2026.3-py2.py3-none-any.whl",
                "url": (
                    "https://files.pythonhosted.org/packages/e5/6d/"
                    "b53b99a9f2766d095985947a5782f1702cabb129a34f7a802d7197af832f/"
                    "tzdata-2026.3-py2.py3-none-any.whl"
                ),
                "sha256": "dc096730c87af6cab1b171c9d532be840741ff5d459015e7f6947bd7d7e54931",
            },
            manifest["upstream_artifact"],
        )
        entries = manifest["files"]
        actual = {
            path.relative_to(TZDATA_ROOT).as_posix()
            for path in TZDATA_ROOT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(set(entries), actual)
        self.assertGreaterEqual(len(entries), 600)
        for relative, metadata in entries.items():
            path = TZDATA_ROOT / relative
            self.assertFalse(path.is_symlink(), relative)
            self.assertEqual(metadata["size"], path.stat().st_size, relative)
            self.assertEqual(metadata["sha256"], hashlib.sha256(path.read_bytes()).hexdigest(), relative)
        self.assertTrue((TZDATA_ROOT / "tzdata.zi").read_text(encoding="utf-8").startswith("# version 2026c\n"))

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
        orchestrator_version = "0.1.1"
        plugin_version = "0.1.1"
        core_version = "0.1.0"
        expected = [
            (PLUGIN_MANIFEST, f'"version": "{plugin_version}"'),
            (ROOT / "README.md", f"编排器 / Plugin 版本：`{plugin_version}`"),
            (ROOT / "CHANGELOG.md", f"## {plugin_version}"),
            (ROOT / "docs" / "VALIDATION.md", f"plugin_distribution: {plugin_version}"),
            (ROOT / "NOTICE", f"Xuanshu Four Pillars Skill {orchestrator_version}"),
            (ROOT / "docs" / "VALIDATION.md", f"release: {orchestrator_version}"),
            (SCRIPTS / "four_pillars_engine.py", f'ENGINE_VERSION = "{orchestrator_version}"'),
            (ROOT / "README.md", f"Node 日历核心版本：`{core_version}`"),
            (NODE_CORE, f"const ENGINE_VERSION = '{core_version}'"),
        ]
        for path, marker in expected:
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
