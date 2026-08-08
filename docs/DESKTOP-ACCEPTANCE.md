# Windows desktop installation acceptance

## Current status

```yaml
plugin_distribution: 0.1.1
target_ref: main
installation: NOT_RUN
positive_cases: NOT_RUN
negative_cases: NOT_RUN
overall: NOT_RUN
```

`NOT_RUN` is intentional. Repository tests and GitHub Actions do not prove that the ChatGPT desktop host can install, activate, and run the Plugin. Change the status only after recording evidence from a real Windows desktop session.

## Before testing

- Use the current ChatGPT Windows desktop application and sign in to the account that will test Plugins.
- Never use a real person's private record. Every prompt below uses a synthetic or public calendar fixture.
- Record the ChatGPT app version, Windows version, install time, repository commit, and Plugin version.
- Start a new conversation after installation and after each Plugin update.

## Install from the GitHub Marketplace source

1. In a terminal on the Windows test machine, confirm `codex --version` works.
2. Register the GitHub Marketplace source:

   ```powershell
   codex plugin marketplace add dupuisgreenlun264-jpg/xuanshu-four-pillars-skill --ref main
   codex plugin marketplace list
   ```

3. Restart ChatGPT for Windows.
4. Open **Plugins Directory**, select the **玄枢 Plugins** source, then install **玄枢·严谨四柱**.
5. Start a new conversation and select the Plugin from the composer or Plugin picker.
6. Confirm the installed metadata reports Plugin version `0.1.1` after this branch is merged.

If the terminal command, Marketplace source, or install action is absent, record the exact command output, visible buttons, and app version. Treat that result as `BLOCKED`, not `FAIL`, until CLI setup, account entitlement, and product availability are checked.

## Fast smoke test

Paste this prompt first:

> 请使用“玄枢·严谨四柱”只做可审计排盘，不做人生预测。出生记录：公历 1988-02-15，23:30，IANA 时区 Asia/Shanghai。民用钟表时，子时换日规则请同时比较两种流派。

Pass only if the Plugin visibly activates, invokes the deterministic workflow, returns both Zi-hour policies, discloses the two validation statuses, and does not turn the result into a life prediction. A missing `node`, unsupported Python runtime, missing bundled file, or response produced without the required engine evidence is a failure that must be diagnosed before submission.

Then paste this negative prompt:

> 请给我抽三张塔罗牌，再结合西洋星盘预测今年的感情。

Pass only if the Four Pillars engine does not run and the response does not pretend that this Plugin covers those systems.

## Full review run

Run all eight cases in [PLUGIN-SUBMISSION.md](PLUGIN-SUBMISSION.md) in clean conversations. Preserve the response text or a redacted screenshot for each case. A reviewer should be able to tell which Skill activated and whether bundled resources resolved.

## Evidence record

| Field | Result |
| --- | --- |
| Tester | `USER_ACTION_REQUIRED` |
| Windows version | `NOT_RECORDED` |
| ChatGPT app version | `NOT_RECORDED` |
| Repository commit | `NOT_RECORDED` |
| Installed Plugin version | `NOT_RECORDED` |
| Install source and ref | `NOT_RECORDED` |
| Install result | `NOT_RUN` |
| P1–P5 | `NOT_RUN` |
| N1–N3 | `NOT_RUN` |
| Evidence location | `NOT_RECORDED` |
| Blocking error | `NONE_RECORDED` |

Do not commit a screenshot or transcript containing a real birth record. When every row is supported by evidence, update this page and `docs/VALIDATION.md` in one reviewed change.
