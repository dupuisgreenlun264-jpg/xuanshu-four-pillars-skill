#!/usr/bin/env python3
"""Regenerate the hash manifest for the vendored IANA timezone tree."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = (
    ROOT
    / "skills"
    / "analyze-four-pillars-rigorously"
    / "scripts"
    / "vendor"
    / "tzdata-2026.3"
)
ZONEINFO_ROOT = BUNDLE_ROOT / "zoneinfo"
OUTPUT = BUNDLE_ROOT / "MANIFEST.json"
UPSTREAM_FILENAME = "tzdata-2026.3-py2.py3-none-any.whl"
UPSTREAM_URL = (
    "https://files.pythonhosted.org/packages/e5/6d/"
    "b53b99a9f2766d095985947a5782f1702cabb129a34f7a802d7197af832f/"
    "tzdata-2026.3-py2.py3-none-any.whl"
)
UPSTREAM_SHA256 = "dc096730c87af6cab1b171c9d532be840741ff5d459015e7f6947bd7d7e54931"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if not ZONEINFO_ROOT.is_dir():
        raise SystemExit(f"Missing timezone tree: {ZONEINFO_ROOT}")
    files: dict[str, dict[str, int | str]] = {}
    for path in sorted(ZONEINFO_ROOT.rglob("*")):
        if path.is_symlink():
            raise SystemExit(f"Symlink is not permitted: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(ZONEINFO_ROOT).as_posix()
        files[relative] = {"sha256": sha256(path), "size": path.stat().st_size}
    if not files:
        raise SystemExit("Timezone tree is empty")
    manifest = {
        "schema_version": "xuanshu-tzdata-bundle-v0.1",
        "python_distribution_version": "2026.3",
        "iana_database_version": "2026c",
        "source": "https://github.com/python/tzdata",
        "upstream_artifact": {
            "filename": UPSTREAM_FILENAME,
            "url": UPSTREAM_URL,
            "sha256": UPSTREAM_SHA256,
        },
        "files": files,
    }
    OUTPUT.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {OUTPUT} with {len(files)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
