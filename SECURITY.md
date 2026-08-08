# Security and privacy policy

## Reporting a vulnerability

Use GitHub private vulnerability reporting when enabled. Do not publish an exploit, private birth record, exact personal profile, or signed artifact URL in a public issue.

If private reporting is not enabled, use the dedicated **Security contact request** issue form. Submit only the request for a private channel—never vulnerability details or personal data. Maintainers must provide a private channel before reproduction material is shared.

Include the smallest reproducible input, expected behavior, affected version, and whether the problem can silently change a pillar or discard an ambiguity candidate. Replace real birth information with synthetic data.

## Sensitive-data rules

- Never commit real names, former names, addresses, birth certificates, event histories, or unredacted reports.
- Do not put birth data in filenames, CI logs, telemetry, analytics, crash reports, or issue titles.
- Examples and tests must use synthetic or already-public calendar fixtures.
- The engine operates offline and does not need network access at runtime.
- The CLI does not persist inputs or results unless the caller redirects output.

## Integrity controls

The runtime verifies the SHA-256 of the frozen `calendar-1901-2033.json` data file, requires the pinned tzdata/tzdb version without a system fallback, confines timezone keys to the package root, and hashes the selected TZif file. No ephemeris kernel, Skyfield package, HKO table, or third-party calendrical binary is required or loaded at runtime.

Calendar-data regeneration must verify the recorded JPL DE440s, USNO `deltat.data`, and USNO `deltat.preds` hashes; record the generator and build-tool versions; rerun the complete validation suite; review distribution rights; update the provenance manifest and changelog; and produce a new dataset/version identity. Dependency, frozen-data, provider-formula, provider-manifest, provenance-manifest, or rule-registry upgrades require the same review discipline. Never replace a source snapshot or generated dataset in place while retaining its old hash or version.

## Safety boundary

Treat traditional interpretations as culturally framed, non-empirical material. Reports must not provide medical diagnosis, legal advice, financial instructions, death/disaster predictions, or coercive life decisions.
