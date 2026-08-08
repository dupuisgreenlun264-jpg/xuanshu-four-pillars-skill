#!/usr/bin/env python3
"""Validate and build the deterministic skills-only Plugin upload archive."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / ".codex-plugin" / "plugin.json"
SKILLS_ROOT = ROOT / "skills"
DEFAULT_DIST = ROOT / "dist"
FIXED_ZIP_TIME = (2026, 8, 8, 0, 0, 0)
MAX_COMPRESSED_BYTES = 100 * 1024 * 1024
MAX_EXTRACTED_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 5000
MAX_ICON_BYTES = 5 * 1024 * 1024
MAX_MEMBER_BYTES = 100 * 1024 * 1024
MAX_PATH_DEPTH = 20

SUPPORTED_CATEGORIES = {
    "Productivity",
    "Creativity",
    "Developer Tools",
    "Business & Operations",
    "Data & Analytics",
    "Communication",
    "Education & Research",
    "Security",
    "Finance",
    "Healthcare",
    "Travel",
    "Entertainment",
    "Other",
}

PACKAGE_ROOT_FILES = (
    Path(".codex-plugin/plugin.json"),
    Path("LICENSE"),
    Path("NOTICE"),
)

FORBIDDEN_PACKAGE_COMPONENTS = {
    ".git",
    ".github",
    ".agents",
    "__pycache__",
    "apps",
    "mcp",
    "node_modules",
    "screenshots",
    "tests",
}


class PreflightError(RuntimeError):
    """Raised when the Plugin cannot be submitted safely."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PreflightError(message)


def validate_visible_text(value: str, field: str) -> None:
    for character in value:
        category = unicodedata.category(character)
        require(not category.startswith("C"), f"{field} contains a control or invisible character")


def load_manifest() -> dict[str, object]:
    try:
        value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError(f"Cannot read Plugin manifest: {exc}") from exc
    require(isinstance(value, dict), "Plugin manifest must be a JSON object")
    return value


def text_field(
    container: dict[str, object],
    name: str,
    *,
    maximum: int,
    one_line: bool = False,
) -> str:
    value = container.get(name)
    require(isinstance(value, str), f"{name} must be a string")
    require(value == value.strip() and bool(value), f"{name} must be nonempty and trimmed")
    validate_visible_text(value, name)
    require(len(value) <= maximum, f"{name} exceeds {maximum} characters")
    if one_line:
        require("\n" not in value and "\r" not in value, f"{name} must be one line")
    return value


def validate_https_url(value: object, field: str, *, maximum: int) -> None:
    require(isinstance(value, str), f"{field} must be a string")
    validate_visible_text(value, field)
    require(value == value.strip(), f"{field} must be trimmed")
    require(len(value) <= maximum, f"{field} exceeds {maximum} characters")
    parsed = urlparse(value)
    require(parsed.scheme == "https" and bool(parsed.netloc), f"{field} must be a public HTTPS URL")
    require(parsed.username is None and parsed.password is None, f"{field} must not contain credentials")


def relative_asset(value: object, field: str) -> Path:
    require(isinstance(value, str) and value.startswith("./"), f"{field} must be a ./ relative path")
    pure = PurePosixPath(value[2:])
    require(not pure.is_absolute() and ".." not in pure.parts, f"{field} escapes the Plugin root")
    path = (ROOT / Path(*pure.parts)).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise PreflightError(f"{field} escapes the Plugin root") from exc
    require(path.is_file(), f"{field} does not resolve to a file: {value}")
    return path


def parse_svg_number(value: str | None, field: str) -> float:
    require(value is not None, f"SVG is missing {field}")
    match = re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value)
    require(match is not None, f"SVG {field} must use a unitless number")
    number = float(match.group(0))
    require(math.isfinite(number) and number > 0, f"SVG {field} must be positive")
    return number


def validate_square_svg(path: Path, field: str) -> None:
    require(path.stat().st_size <= MAX_ICON_BYTES, f"{field} exceeds 5 MiB")
    require(path.suffix.lower() == ".svg", f"{field} must be the reviewed SVG asset")
    try:
        root = ElementTree.fromstring(path.read_bytes())
    except ElementTree.ParseError as exc:
        raise PreflightError(f"{field} is not valid SVG XML: {exc}") from exc
    require(
        root.tag in {"svg", "{http://www.w3.org/2000/svg}svg"},
        f"{field} root element must be svg",
    )
    width = parse_svg_number(root.get("width"), "width")
    height = parse_svg_number(root.get("height"), "height")
    require(width >= 48 and height >= 48, f"{field} must be at least 48 by 48")
    require(abs(width - height) < 1e-9, f"{field} must be square")
    view_box = root.get("viewBox")
    require(view_box is not None, f"{field} must declare a viewBox")
    parts = view_box.replace(",", " ").split()
    require(len(parts) == 4, f"{field} viewBox must contain four numbers")
    try:
        values = [float(item) for item in parts]
    except ValueError as exc:
        raise PreflightError(f"{field} viewBox contains a non-number") from exc
    require(values[2] >= 48 and values[3] >= 48, f"{field} viewBox must be at least 48 by 48")
    require(abs(values[2] - values[3]) < 1e-9, f"{field} viewBox must be square")


def rgb(color: str) -> tuple[int, int, int]:
    require(re.fullmatch(r"#[0-9A-Fa-f]{6}", color) is not None, f"Invalid color: {color}")
    return tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def relative_luminance(color: str) -> float:
    channels: list[float] = []
    for value in rgb(color):
        normalized = value / 255
        channels.append(
            normalized / 12.92
            if normalized <= 0.04045
            else ((normalized + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(left: str, right: str) -> float:
    lighter, darker = sorted((relative_luminance(left), relative_luminance(right)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def validate_skill_agent_metadata(skill_dir: Path, skill_name: str) -> None:
    path = skill_dir / "agents" / "openai.yaml"
    require(path.is_file(), f"Missing agents/openai.yaml for skill: {skill_name}")
    text = path.read_text(encoding="utf-8")
    require("\t" not in text and "\r" not in text, f"Invalid whitespace in {path.relative_to(ROOT)}")
    lines = text.splitlines()
    require(bool(lines) and lines[0] == "interface:", f"{path.relative_to(ROOT)} must start with interface:")
    values: dict[str, str] = {}
    for line in lines[1:]:
        match = re.fullmatch(r"  ([a-z_]+): (.+)", line)
        require(match is not None, f"Unsupported YAML structure in {path.relative_to(ROOT)}")
        key, raw = match.groups()
        require(key not in values, f"Duplicate interface key in {path.relative_to(ROOT)}: {key}")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PreflightError(f"All strings must be quoted in {path.relative_to(ROOT)}: {key}") from exc
        require(isinstance(value, str), f"{path.relative_to(ROOT)} {key} must be a string")
        validate_visible_text(value, f"{path.relative_to(ROOT)} {key}")
        values[key] = value

    required = {"display_name", "short_description", "default_prompt", "icon_small", "icon_large"}
    allowed = required | {"brand_color"}
    require(required <= set(values), f"{path.relative_to(ROOT)} is missing required interface fields")
    require(set(values) <= allowed, f"{path.relative_to(ROOT)} contains unsupported interface fields")
    require(0 < len(values["display_name"]) <= 64, "Skill display_name must contain 1 to 64 characters")
    require(25 <= len(values["short_description"]) <= 64, "Skill short_description must contain 25 to 64 characters")
    require(
        f"${skill_name}" in values["default_prompt"],
        f"Skill default_prompt must explicitly mention ${skill_name}",
    )
    require(0 < len(values["default_prompt"]) <= 256, "Skill default_prompt exceeds 256 characters")
    if "brand_color" in values:
        rgb(values["brand_color"])

    for field in ("icon_small", "icon_large"):
        value = values[field]
        require(value.startswith("./assets/"), f"Skill {field} must use a ./assets/ path")
        pure = PurePosixPath(value[2:])
        require(not pure.is_absolute() and ".." not in pure.parts, f"Skill {field} escapes its root")
        asset = (skill_dir / Path(*pure.parts)).resolve()
        try:
            asset.relative_to(skill_dir.resolve())
        except ValueError as exc:
            raise PreflightError(f"Skill {field} escapes its root") from exc
        require(asset.is_file() and not asset.is_symlink(), f"Skill {field} is missing or unsafe")
        validate_square_svg(asset, f"Skill {field}")


def skill_names() -> list[str]:
    names: list[str] = []
    for path in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        match = re.match(r"\A---\n(?P<header>.*?)\n---(?:\n|\Z)", text, flags=re.DOTALL)
        require(match is not None, f"Missing YAML frontmatter: {path.relative_to(ROOT)}")
        header = match.group("header")
        require("\t" not in header and "\r" not in header, f"Invalid frontmatter whitespace: {path.relative_to(ROOT)}")
        fields: dict[str, str] = {}
        for line in header.splitlines():
            field_match = re.fullmatch(r"([a-z][a-z-]*): (.+)", line)
            require(field_match is not None, f"Unsupported frontmatter YAML: {path.relative_to(ROOT)}")
            key, value = field_match.groups()
            require(key in {"name", "description"}, f"Unexpected frontmatter field in {path.relative_to(ROOT)}: {key}")
            require(key not in fields, f"Duplicate frontmatter field in {path.relative_to(ROOT)}: {key}")
            require(value == value.strip(), f"Untrimmed frontmatter field in {path.relative_to(ROOT)}: {key}")
            require(": " not in value and " #" not in value, f"Ambiguous plain YAML scalar in {path.relative_to(ROOT)}: {key}")
            require(
                value[0].isalpha()
                and value[0] not in "-?:,[]{}#&*!|>'\"%@`~"
                and not value.endswith(":")
                and "#" not in value
                and value.casefold() not in {"null", "true", "false", "yes", "no", "on", "off"},
                f"Unsafe plain YAML scalar in {path.relative_to(ROOT)}: {key}",
            )
            validate_visible_text(value, f"{path.relative_to(ROOT)} {key}")
            fields[key] = value
        require(set(fields) == {"name", "description"}, f"Skill frontmatter must contain name and description: {path.relative_to(ROOT)}")
        name = fields["name"]
        require(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is not None, f"Invalid skill name: {name}")
        require(len(name) <= 64, f"Skill name exceeds 64 characters: {name}")
        require(name == path.parent.name, f"Skill name and directory differ: {name}")
        description = fields["description"]
        require(0 < len(description) <= 1024, f"Skill description must contain 1 to 1024 characters: {name}")
        require("<" not in description and ">" not in description, f"Skill description contains an angle bracket: {name}")
        require(bool(text[match.end():].strip()), f"Skill body is empty: {name}")
        validate_skill_agent_metadata(path.parent, name)
        names.append(name)
    require(bool(names), "At least one skills/<name>/SKILL.md is required")
    require(len(names) == len(set(names)), "Duplicate skill identities are not permitted")
    return names


def validate_manifest(manifest: dict[str, object]) -> tuple[str, str]:
    name = text_field(manifest, "name", maximum=64, one_line=True)
    require(re.fullmatch(r"[A-Za-z0-9_-]+", name) is not None, "name must use ASCII letters, digits, underscore, or hyphen")
    version = text_field(manifest, "version", maximum=64, one_line=True)
    require(
        re.fullmatch(
            r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
            r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
            r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?",
            version,
        ) is not None,
        "version must be semantic versioning",
    )
    text_field(manifest, "description", maximum=1024, one_line=True)
    require(manifest.get("skills") == "./skills/", "skills must be ./skills/")
    require("mcpServers" not in manifest and "apps" not in manifest, "Skills-only manifest cannot declare MCP or apps")

    author = manifest.get("author")
    require(isinstance(author, dict), "author must be an object")
    author_name = text_field(author, "name", maximum=80, one_line=True)
    validate_https_url(author.get("url"), "author.url", maximum=2048)
    for field in ("homepage", "repository"):
        validate_https_url(manifest.get(field), field, maximum=2048)

    interface = manifest.get("interface")
    require(isinstance(interface, dict), "interface must be an object")
    require("screenshots" not in interface, "Skills-only interface cannot declare screenshots")
    text_field(interface, "displayName", maximum=30, one_line=True)
    text_field(interface, "shortDescription", maximum=30, one_line=True)
    text_field(interface, "longDescription", maximum=4000)
    developer_name = text_field(interface, "developerName", maximum=80, one_line=True)
    require(author_name == developer_name, "author.name and interface.developerName must match exactly")
    require(interface.get("category") in SUPPORTED_CATEGORIES, "Unsupported interface.category")
    for field in ("websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL"):
        validate_https_url(interface.get(field), f"interface.{field}", maximum=1024)

    capabilities = interface.get("capabilities")
    require(isinstance(capabilities, list) and len(capabilities) <= 20, "capabilities must be a list of at most 20 items")
    require(bool(capabilities), "At least one capability is required for this submission")
    for index, value in enumerate(capabilities):
        require(isinstance(value, str) and value == value.strip(), f"capabilities[{index}] must be trimmed text")
        validate_visible_text(value, f"capabilities[{index}]")
        require(0 < len(value) <= 120, f"capabilities[{index}] exceeds 120 characters")
        require("\n" not in value and "\r" not in value, f"capabilities[{index}] must be one line")

    prompts = interface.get("defaultPrompt")
    require(isinstance(prompts, list) and 1 <= len(prompts) <= 3, "defaultPrompt must contain one to three prompts")
    seen: set[str] = set()
    for index, value in enumerate(prompts):
        require(isinstance(value, str) and value == value.strip(), f"defaultPrompt[{index}] must be trimmed text")
        validate_visible_text(value, f"defaultPrompt[{index}]")
        require(0 < len(value) <= 128, f"defaultPrompt[{index}] exceeds 128 characters")
        require("\n" not in value and "\r" not in value, f"defaultPrompt[{index}] must be one line")
        require("@" not in value, f"defaultPrompt[{index}] must not contain an @ mention")
        normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().casefold()
        require(normalized not in seen, f"defaultPrompt[{index}] is duplicated after normalization")
        seen.add(normalized)

    brand = interface.get("brandColor")
    dark_brand = interface.get("brandColorDark")
    require(isinstance(brand, str), "brandColor must be a string")
    require(isinstance(dark_brand, str), "brandColorDark must be a string")
    rgb(brand)
    rgb(dark_brand)
    require(contrast(brand, "#FFFFFF") >= 2.0, "brandColor contrast against white is below 2:1")
    require(contrast(dark_brand, "#212121") >= 2.0, "brandColorDark contrast against #212121 is below 2:1")

    for field in ("logo", "composerIcon"):
        asset = relative_asset(interface.get(field), f"interface.{field}")
        validate_square_svg(asset, f"interface.{field}")

    for skill_name in skill_names():
        require(len(f"{name}:{skill_name}") <= 64, f"Combined Plugin and skill identity exceeds 64: {skill_name}")
    return name, version


def package_files() -> list[Path]:
    relative_files = list(PACKAGE_ROOT_FILES)
    relative_files.extend(
        path.relative_to(ROOT)
        for path in SKILLS_ROOT.rglob("*")
        if path.is_file()
    )
    unique = sorted(set(relative_files), key=lambda path: path.as_posix())
    require(bool(unique), "Package file list is empty")
    require(len(unique) <= MAX_ENTRIES, f"Package exceeds {MAX_ENTRIES} entries")

    total = 0
    normalized_names: set[str] = set()
    for relative in unique:
        require(not relative.is_absolute() and ".." not in relative.parts, f"Unsafe package path: {relative}")
        relative_name = relative.as_posix()
        require("\\" not in relative_name, f"Package path contains a backslash: {relative}")
        components = relative_name.split("/")
        require(all(part and part == part.strip() for part in components), f"Package path has an empty or padded component: {relative}")
        require(len(components) <= MAX_PATH_DEPTH, f"Package path exceeds depth {MAX_PATH_DEPTH}: {relative}")
        normalized = unicodedata.normalize("NFKC", relative_name).casefold()
        require(normalized not in normalized_names, f"Package path collides after Unicode/case normalization: {relative}")
        normalized_names.add(normalized)
        lowered_parts = {part.lower() for part in relative.parts}
        require(not (lowered_parts & FORBIDDEN_PACKAGE_COMPONENTS), f"Forbidden skills-only package path: {relative}")
        absolute = ROOT / relative
        require(absolute.is_file(), f"Required package file is missing: {relative}")
        require(not absolute.is_symlink(), f"Symlinks are not permitted in the upload archive: {relative}")
        size = absolute.stat().st_size
        require(size <= MAX_MEMBER_BYTES, f"Package member exceeds 100 MiB: {relative}")
        total += size
    require(total <= MAX_EXTRACTED_BYTES, "Package exceeds 512 MiB extracted")
    return unique


def validate_archive(path: Path) -> None:
    require(path.is_file(), f"Archive was not created: {path}")
    require(path.stat().st_size <= MAX_COMPRESSED_BYTES, "Archive exceeds 100 MiB compressed")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            require(1 <= len(infos) <= MAX_ENTRIES, "Archive entry count is invalid")
            require(sum(item.file_size for item in infos) <= MAX_EXTRACTED_BYTES, "Archive exceeds 512 MiB extracted")
            names = [item.filename for item in infos]
            require(len(names) == len(set(names)), "Archive contains duplicate entry names")
            require(names.count(".codex-plugin/plugin.json") == 1, "Archive must contain exactly one root Plugin manifest")
            require(any(re.fullmatch(r"skills/[^/]+/SKILL\.md", name) for name in names), "Archive has no root Skill")
            normalized_names: set[str] = set()
            for info in infos:
                name = info.filename
                pure = PurePosixPath(name)
                require(not pure.is_absolute() and ".." not in pure.parts, f"Archive contains unsafe path: {name}")
                require("\\" not in name, f"Archive path contains a backslash: {name}")
                components = name.split("/")
                require(all(part and part == part.strip() for part in components), f"Archive path has an empty or padded component: {name}")
                require(len(components) <= MAX_PATH_DEPTH, f"Archive path exceeds depth {MAX_PATH_DEPTH}: {name}")
                normalized = unicodedata.normalize("NFKC", name).casefold()
                require(normalized not in normalized_names, f"Archive path collides after Unicode/case normalization: {name}")
                normalized_names.add(normalized)
                require(not info.is_dir(), f"Archive must not contain directory-only entries: {name}")
                require(info.file_size <= MAX_MEMBER_BYTES, f"Archive member exceeds 100 MiB: {name}")
                require(info.flag_bits & 0x1 == 0, f"Archive member must not be encrypted: {name}")
                require(info.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}, f"Unsupported ZIP compression: {name}")
                lowered_parts = {part.lower() for part in pure.parts}
                require(not (lowered_parts & FORBIDDEN_PACKAGE_COMPONENTS), f"Archive contains forbidden path: {name}")
    except zipfile.BadZipFile as exc:
        raise PreflightError(f"Invalid ZIP archive: {exc}") from exc


def build_archive(output: Path, files: list[Path]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for relative in files:
            info = zipfile.ZipInfo(relative.as_posix(), date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (ROOT / relative).read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    validate_archive(output)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="validate without writing a ZIP")
    parser.add_argument("--output", type=Path, help="override the deterministic ZIP output path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        manifest = load_manifest()
        name, version = validate_manifest(manifest)
        files = package_files()
        extracted = sum((ROOT / item).stat().st_size for item in files)
        if args.check_only:
            print(f"PASS: {name} {version}; {len(files)} files; {extracted} bytes extracted")
            return 0
        output = args.output or DEFAULT_DIST / f"{name}-plugin-{version}.zip"
        build_archive(output.resolve(), files)
        print(f"PASS: {output.resolve()} ({output.stat().st_size} bytes, {len(files)} files)")
        return 0
    except PreflightError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
