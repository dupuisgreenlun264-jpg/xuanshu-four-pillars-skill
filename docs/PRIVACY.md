# Privacy policy

Effective date: 2026-08-08

This policy covers the Xuanshu Four Pillars skills-only Plugin distributed from this repository.

## Data categories

The Plugin may use the birth date, local birth time or time range, IANA timezone, optional longitude, and calculation conventions that a user supplies in the current ChatGPT conversation. A name, address, identity document, relationship history, or other life history is not required for its calculation workflow.

The packaged calculation engine runs locally in the Plugin execution environment. This project does not operate an MCP server or other project-owned backend for the Plugin, and the packaged engine does not transmit inputs to a project-owned service, add telemetry, or persist a report unless the host or user explicitly saves its output.

## Recipients

There is no project-owned service and therefore no project-side recipient of birth inputs or generated reports. OpenAI and the ChatGPT or Codex host may process conversation content, files, execution logs, and saved output as necessary to provide the user's service. If a user voluntarily opens a GitHub issue or pull request, GitHub and repository participants receive the submitted content. The project does not sell personal data or provide birth inputs to advertising or data-broker recipients.

## ChatGPT and hosting-platform processing

The user's ChatGPT or Codex account, conversation, uploaded material, host logs, and platform retention are handled by OpenAI under the policies and controls that apply to the user's service. This open-source project does not control that platform processing. Users should consult their platform data controls before entering personal data.

GitHub separately processes visits and contributions made on the public repository. Do not post real birth records, reports, identity documents, secrets, or vulnerability details in a public issue or pull request.

## Retention and deletion

When a temporary input file is needed, the Skill instructs the host to use a private temporary path and a `finally`-equivalent cleanup path after ordinary success, error, or a cleanup-capable interruption. It must not reuse that file across users or conversations. An abrupt host or operating-system termination can prevent application cleanup; any remaining temporary storage is then governed by the host environment's isolation and lifecycle. The project-owned Plugin runtime has no account database and no project-side retention store, so the project has no separate user profile to delete.

## User controls

Users control whether to invoke the Plugin and what optional longitude or birth-time detail to provide. They may use a time range or state that time is unknown instead of inventing a value. They can stop a calculation, avoid saving its output, uninstall the Plugin, and use ChatGPT or Codex controls to delete platform conversations or account data. To request removal of material posted to GitHub, contact the maintainers through the support channel below and identify only the public URL; do not repeat the sensitive content.

## Security and contact

Security reporting instructions are in [SECURITY.md](../SECURITY.md). General support is available through the repository's [GitHub Issues](https://github.com/dupuisgreenlun264-jpg/xuanshu-four-pillars-skill/issues). Submit only synthetic reproduction data in public.

Material policy changes will be recorded in this repository's version history.
