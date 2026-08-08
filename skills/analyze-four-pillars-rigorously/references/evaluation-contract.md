# Evaluation and accuracy contract

## Contents

1. Current status
2. FourPillarsBench-v1
3. 100x claim rule
4. Release gates
5. Historical-event research

## Current status

V0.1 status is `DEVELOPMENT_VALIDATED_NOT_INDEPENDENTLY_CERTIFIED`. Its frozen calendar data uses `xuanshu-calendar-data-v0.2`, and the Node response uses `xuanshu-four-pillars-core-response-v0.2`. The exact regression-gate count is reported by the current CI run rather than frozen into this contract. Passing those gates is not enough for a comparative 100x claim or empirical life-prediction claim.

The runtime uses project-owned code and a frozen JPL-derived calendar file, not a third-party calendrical binary. That architecture improves reproducibility and source auditability; it does not by itself establish independent accuracy.

## FourPillarsBench-v1

Freeze the reference repository commit, model, full prompt, and sampling settings. Use at least 2,000 cases:

- ordinary dates/times: 40%
- solar-term, day, and Shichen boundaries: 35%
- historical timezone and DST: 15%
- missing/interval inputs: 10%

Freeze the dataset and ground-truth manifest by SHA-256 before either system runs. Two independent calendar reviewers label each case; disagreements go to a third reviewer, with the adjudication log retained. Keep at least 20% sealed from prompt, code, and rule development.

Run each system three times. Score one row per benchmark case: if any run has a critical error, or the three L1 results are not byte-identical, the case is an error. A critical error is any wrong pillar, wrong timezone/term/rollover, failure to preserve required candidates, invented missing input, nondeterministic L1 result, or traditional interpretation presented as calculation fact.

Define critical error rate:

\[
CER=\frac{\text{cases containing at least one critical error}}{\text{all cases}}
\]

## 100x claim rule

Permit only this wording after the gate passes:

> On FourPillarsBench-v1's chart critical-error-rate metric, the new system reduced errors by at least 100x relative to the frozen reference configuration.

Use two-sided 95% Clopper–Pearson intervals for each binomial CER. This definition handles zero observed errors with a nonzero upper bound. Require both:

\[
CER_{reference}/CER_{new}\ge100
\]

and the ratio of the reference 95% lower confidence bound to the new 95% upper confidence bound to remain at least 100.

Never shorten this to “fortune-telling accuracy is 100x higher” or “life predictions are 100x more accurate.”

## Release gates

- **Passed:** final frozen-data rerun across all 48,578 Gregorian dates from 1901–2033 and all 3,192 solar-term dates against the local HKO publication-table oracle. It retained 90 lunar daily-row differences in three 30-day runs and six solar-term date differences, with zero additional differences.
- Every frozen new moon and solar-term instant compared against a pinned high-precision implementation independent of the Skyfield/JPL generation path, with maximum UTC/UT1 error published by Delta T segment.
- DST gaps/folds, half-hour/45-minute zones, Chinese historical DST, and LMT cases covered.
- Every Lichun, Jie, 23:00, 00:00, and timezone transition tested at -1 second, computed boundary point, +1 second.
- Day pillar increments exactly one step per day and repeats after 60 days.
- Dayun direction and sequence adjacency match the frozen provider oracle; provider-specific symbolic start is preserved without integer-year rounding.
- Canonical JSON byte-identical over repeated runs.
- Expanding an input interval never removes an existing candidate; shrinking it never adds one.
- Interpretation methods cannot modify L1 chart data.
- Offline execution, frozen-data hash verification, source-snapshot hash verification, and proof that build-only ephemeris/oracle files are absent from the runtime distribution.
- A caller guard of 1 second cannot suppress a larger dataset event guard; dataset guards that cross a result boundary expand valid model candidates, while input/apparent-solar counterfactuals remain sensitivity-only.
- One guarded Jie produces exactly the before/after model variants; more than one guarded Jie without an exhaustive encoding fails closed. Lunar reverse conversion blocks applicable model/historical uncertainty, while a review-only event remains convertible.

The final HKO comparison identified 90 lunar daily-row disagreements in three 30-day runs and six solar-term Beijing-date disagreements. They are mandatory disclosed authority/convention differences in the frozen artifact. Certification does not require pretending that a publication table and a retrospective astronomical model are identical; it requires explicit convention selection, reproducible adjudication, bounded uncertainty, and no unexplained or hidden mismatch. Every regenerated artifact must repeat the full HKO comparison.

Score three review mechanisms separately: the caller's input `boundary_guard_seconds`, each frozen event's Delta T/time-scale `model_guard_seconds`, and HKO authority divergence. Do not award or deduct correctness by treating one as a substitute for another. In particular, the conservative 600-second pre-1973 model guard is not a universal modern-event error bound, while a modern event within 600 seconds of Beijing midnight can still be a declared date-sensitivity review case.

## Historical-event research

Do not use same-session feedback as validation. For birth-time research:

1. Freeze candidate charts and timestamped predictions before seeing events.
2. Collect events independently with domain, direction, time window, severity, and observable criterion.
3. Split calibration and sealed holdout sets.
4. Add random-date, wrong-time, and Barnum controls.
5. Score only preregistered, falsifiable claims.
6. Treat subjective “feels accurate” as satisfaction, not predictive accuracy.
7. Create a new ruleset version for any rule change and rerun the sealed evaluation.

Until a preregistered prospective controlled study exists, keep prediction status `NOT_EMPIRICALLY_VALIDATED`.
