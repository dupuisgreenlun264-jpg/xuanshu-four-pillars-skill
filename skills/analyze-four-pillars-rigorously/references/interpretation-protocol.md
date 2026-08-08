# Traditional interpretation protocol

## Contents

1. Evidence layers
2. Analysis order
3. Rule record
4. Conflict handling
5. Prohibited inference

## Evidence layers

| Label | Meaning | Example |
| --- | --- | --- |
| `L1A TIME` | Input and frozen-tzdb time normalization | “The two folds correspond to distinct UTC instants.” |
| `L1B CALENDAR` | Versioned calendrical mapping | “Month pillar is 甲寅 under the computed-Jie contract.” |
| `L1C TRAD-MAP` | Versioned school-dependent lookup/provider | “Under the named provider, the branch has these hidden stems.” |
| `L2 INTERPRET` | Registered traditional rule-dependent reading | “Under registered rule GE-JU-METHOD-001…” |
| `L3 REFLECT` | Low-risk reflection | “Compare this theme with current workload evidence.” |
| `U UNKNOWN` | Missing, conditional, or uncertified | “Hour pillar has two candidates.” |

Never use words such as proven, probability, confidence, causal, diagnosis, or inevitable for L2 unless an actual empirical study supports the exact claim.

## Analysis order

1. Freeze the candidate chart set. Analyze stable facts before variants.
2. State day master, month command, season, exposed stems, roots, and hidden stems from L1.
3. Describe combinations, clashes, punishments, harms, and seasonal flow as structural observations; do not assign automatic good/bad outcomes.
4. Evaluate ordinary pattern gates and special-pattern gates separately. A special pattern requires explicit necessary conditions and a disqualifier check.
5. Run these methods in parallel when relevant:
   - `T-HOU`: seasonal climate/调候.
   - `F-YI`: support-and-control/扶抑.
   - `GE-JU`: month-command pattern and supporting deity/格局相神.
   - `B-YAO`: structural defect/remedy/病药.
6. State when methods agree, disagree, or are underdetermined. Do not manufacture one composite “用神 score.”
7. Analyze Dayun or annual cycles only after naming the exact provider, candidate chart, and activation interval.
8. Convert themes into non-fatalistic possibilities and reality checks.

## Rule record

Attach this schema to every material L2 conclusion. `rule_id` must already exist in `rule-registry.json`; never mint one during a response:

```yaml
rule_id: GE-JU-001
claim: concise paraphrase
premises:
  - exact L1 facts
source:
  title: classical title
  chapter_or_topic: inspected location
  edition_or_url: inspected source
method: tiaohou | fuyi | geju | bingyao | shensha
applies_to: stable chart or named candidate
conflicts: alternative rule IDs or none
status: traditional_interpretation
```

If the source text has not been inspected and registered, omit the rule rather than cite from memory. If only a modern commentary is available, identify it as commentary. The v0.1 registry is deliberately small; lack of coverage is `U UNKNOWN`, not permission to improvise.

## Conflict handling

- Keep variant Tianyi, hidden-stem, month-command, Dayun, and Zi-hour tables under separate source IDs.
- Do not splice two mnemonic variants into one list.
- Do not use “all classics agree” unless the inspected passages actually agree.
- Do not treat 神煞 as independently decisive; default it to off.
- Do not use fixed hidden-stem weights such as 60/30/10 unless a named modern model defines them; label that model heuristic.

## Prohibited inference

- No death year, disaster, severe disease, criminality, infidelity, fertility, or unavoidable divorce claims.
- No medical, legal, investment, hiring, marriage, or reproductive instruction.
- No personality double-bind that is true in both directions.
- No “historical hit” claimed after showing a vague event and soliciting agreement.
- No retroactive adjustment of pattern, useful deity, or ruleset to fit feedback.
- No use of name changes, living status, or private history when those fields are outside the chart calculation.
