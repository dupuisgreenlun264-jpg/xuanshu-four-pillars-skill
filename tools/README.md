# Rebuilding the frozen calendar data

This directory contains the project-authored, build-only regeneration workflow for `calendar-1901-2033.json`. The shipped runtime does not import these Python packages or read the JPL/USNO source files.

Calendar-data regeneration requires Python 3.12 or newer because the frozen build environment pins NumPy 2.5.1. This is separate from the shipped runtime, which supports Python 3.11 or newer.

## Frozen build identities

| Artifact | SHA-256 |
| --- | --- |
| `generate_calendar_data.py` | `6f30b0579347cedfade4077e407dfaabd94f9819125c61d89bd2c014fc735405` |
| `calendar-build-requirements.txt` | `6cfa326d743d96c47739eedd1acafb642ce0abdb4dc91d256d05755e8908f4d8` |
| Release `calendar-1901-2033.json` | `65189952013b9471e6a0e8a63109ce6305d6242588ec6e3fabdb8ddd0bdd4509` |
| `generate_tzdata_manifest.py` | `3d25f365817e054f0cc10fe9ea2d2467dfd58c723424268e30185a741df76cd8` |
| Bundled timezone `MANIFEST.json` | `623879126f592375003fac137d7940dbd41b55b2e2972e1586f7680ba03efa1f` |

The pinned build-only Python environment is:

- Skyfield 1.54;
- jplephem 2.24;
- numpy 2.5.1;
- sgp4 2.27.

Install it in an isolated environment. Do not add that environment to the runtime package.

```bash
python3 -m venv /tmp/xuanshu-calendar-venv
/tmp/xuanshu-calendar-venv/bin/python -m pip install \
  -r tools/calendar-build-requirements.txt
```

Before installation or generation, verify the checked-in build files:

```bash
sha256sum tools/generate_calendar_data.py \
  tools/calendar-build-requirements.txt
```

## Download and verify the three source inputs

Download these files locally. They are not committed or redistributed.

| Input | Source | Required SHA-256 |
| --- | --- | --- |
| JPL DE440s | `https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de440s.bsp` | `c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2` |
| USNO `deltat.data` | `https://maia.usno.navy.mil/ser7/deltat.data` | `9f88e53593495a09219fe956eeadea0fa9f8e3e02c310b2aa2b70852383cdf6f` |
| USNO `deltat.preds` | `https://maia.usno.navy.mil/ser7/deltat.preds` | `5d864fddd30b2c64d2a86d3debbb25604eb5de44370c96bccf2abd5463f3db08` |

Example:

```bash
xuanshu_build_dir="$(mktemp -d)"
curl -fL -o "$xuanshu_build_dir/de440s.bsp" \
  https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de440s.bsp
curl -fL -o "$xuanshu_build_dir/deltat.data" \
  https://maia.usno.navy.mil/ser7/deltat.data
curl -fL -o "$xuanshu_build_dir/deltat.preds" \
  https://maia.usno.navy.mil/ser7/deltat.preds
sha256sum "$xuanshu_build_dir/de440s.bsp" \
  "$xuanshu_build_dir/deltat.data" \
  "$xuanshu_build_dir/deltat.preds"
```

Stop if any digest differs. A newer upstream snapshot is a new build input and must not silently replace the frozen source.

## Refreshing the bundled timezone tree

Runtime timezone data is vendored under `skills/analyze-four-pillars-rigorously/scripts/vendor/tzdata-2026.3/`. It is separate from the astronomical build environment. The current tree is byte-identical, for all 625 `tzdata/zoneinfo/` files, to the PyPI wheel `tzdata-2026.3-py2.py3-none-any.whl` with SHA-256 `dc096730c87af6cab1b171c9d532be840741ff5d459015e7f6947bd7d7e54931`. Its exact `files.pythonhosted.org` URL is pinned in the generated manifest and provenance manifest.

A refresh must verify an exact upstream wheel digest, retain the package's Apache 2.0 notices, remove cache/compiled Python files, and use a new versioned directory rather than replacing the current tree in place.

After copying the reviewed `zoneinfo` tree, regenerate its complete size/hash manifest:

```bash
PYTHONDONTWRITEBYTECODE=1 python tools/generate_tzdata_manifest.py
sha256sum tools/generate_tzdata_manifest.py \
  skills/analyze-four-pillars-rigorously/scripts/vendor/tzdata-2026.3/MANIFEST.json
```

The current manifest covers 625 files. Review the generated diff, update the pinned manifest digest in the engine and provenance records, then run the complete suite. The runtime verifies the pinned manifest plus the selected TZif file and refuses a system-zoneinfo fallback.

## Generate twice and compare

Run the generator twice from the same verified inputs, writing outside the repository:

```bash
/tmp/xuanshu-calendar-venv/bin/python tools/generate_calendar_data.py \
  --kernel "$xuanshu_build_dir/de440s.bsp" \
  --delta-data "$xuanshu_build_dir/deltat.data" \
  --delta-preds "$xuanshu_build_dir/deltat.preds" \
  --output "$xuanshu_build_dir/calendar-run-1.json"

/tmp/xuanshu-calendar-venv/bin/python tools/generate_calendar_data.py \
  --kernel "$xuanshu_build_dir/de440s.bsp" \
  --delta-data "$xuanshu_build_dir/deltat.data" \
  --delta-preds "$xuanshu_build_dir/deltat.preds" \
  --output "$xuanshu_build_dir/calendar-run-2.json"

cmp "$xuanshu_build_dir/calendar-run-1.json" \
  "$xuanshu_build_dir/calendar-run-2.json"
sha256sum "$xuanshu_build_dir/calendar-run-1.json" \
  "$xuanshu_build_dir/calendar-run-2.json"
```

Both files must be byte-identical and both digests must equal:

```text
65189952013b9471e6a0e8a63109ce6305d6242588ec6e3fabdb8ddd0bdd4509
```

The generator also fails closed if the Cartesian product of a new moon's and a major solar term's guarded alternative Beijing dates could change principal-term month membership. Such a failure requires encoding explicit alternate month sequences; never bypass that gate. The frozen release passes this combined-guard gate and contains 3,244 term rows, 1,657 lunar-month rows, and 77 lunar uncertainty-event rows, including context outside the public input range.

## Local HKO oracle validation

HKO tables are a validation oracle, not a generation input. Do not commit or redistribute their files, row text, or a complete derived dataset. The repository intentionally ships neither the HKO source files nor an automated HKO downloader/comparator.

For a local audit, retrieve the English text table for each year 1901–2033 from the HKO conversion-table locator into a temporary directory. The per-year file pattern currently used by the release audit is:

```text
https://www.hko.gov.hk/en/gts/time/calendar/text/files/T{YEAR}e.txt
```

Using a local parser, compare every exposed Gregorian day row and every solar-term date against each freshly generated file. The final release audit result is:

- 48,578 Gregorian day rows compared;
- 90 lunar daily-row divergences, grouped into exactly three 30-day runs:
  - 1914-11-17 through 1914-12-16;
  - 1916-02-03 through 1916-03-03;
  - 1920-11-10 through 1920-12-09;
- 3,192 solar-term rows compared;
- six solar-term Beijing-date divergences: 1912 小雪, 1913 秋分, 1917 大雪, 1927 白露, 1928 夏至, and 1979 大寒;
- zero additional divergences.

Record only the nine non-expressive discrepancy facts required for audit—the two dates, a stable discrepancy code, and a source locator. Do not copy HKO prose or table rows into the release artifact.

## Accepting a regenerated artifact

A changed output digest is not a routine refresh. Before replacing the release data:

1. inspect every source and dependency change;
2. repeat the two-run byte comparison;
3. rerun the local HKO oracle audit;
4. run the complete engine and repository test suites;
5. update the data/core versions, `NOTICE`, changelog, provider/provenance manifests, and every pinned digest;
6. review the combined-guard gate and all boundary behavior.

See the [calculation contract](../skills/analyze-four-pillars-rigorously/references/calculation-contract.md) and [provenance manifest](../skills/analyze-four-pillars-rigorously/references/provenance-manifest.json) for runtime interpretation and source roles.
