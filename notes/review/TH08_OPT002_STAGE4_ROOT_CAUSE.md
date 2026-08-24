# TH08 OPT-002 Stage 4A Root-Cause Audit

Last updated: 2026-08-24.

## Scope And Verdict

This audit explains the abnormal Stage 4A result in the first physical
OPT-002 route.  It compares:

- OPT-001: `lunatic_route2_fullrun_unattended_20260824_022909`, commit
  `6305dabae9ee6f6b29f5ad1588e2dfab8a079bae`, 61 total hits and stage counts
  `5/2/5/15/15/19`;
- OPT-002: `lunatic_route2_fullrun_unattended_20260824_034510`, commit
  `f126fb2003f3142cb2b4fcbc003eba667967e270`, 67 total hits and stage counts
  `0/4/5/21/10/27`.

The routes have different natural RNG roots, so unmatched hit totals are not
a same-seed A/B test.  The retained trace still establishes three concrete
findings:

1. **A real controller feedback bug caused the first Stage 4A hit.**  After
   the scene reset, low-load samples collapsed the modeled end-to-end delay to
   `[1]`.  When bullet planning later advanced the game by two frames, the
   deadline guard held the old `stay` command for 32 consecutive decisions,
   but the rejected writes could not update the estimator or activate its
   guard.  The player remained at `(192, 384)` until the hit at frame 73042.
2. **The originally reported Stage 4A `sensor_gap_or_unmodeled_hazard` is a diagnostic
   time-alignment error.**  At frame 104764 the selected action already had
   `worst_collisions=1` and robust minimum clearance `-1.662`; the hit was
   detected at 104767 only after that collision interval, when the current
   bullet snapshot had moved clear.  This was a modeled local-set exhaustion,
   not evidence of an unknown hazard.
3. **The remaining misses expose the known short-horizon architecture, not
   corrupt coalesced reads.**  Every one of the other 20 Stage 4A hits follows
   a locally exhausted robust action set, while the route made zero global
   viability queries.  The solver detects traps only 3--21 frames before
   impact and has no source-authoritative future-birth/global policy with
   which to avoid entering them.

OPT-002's coalesced read mechanism should be retained: it improved latency,
reduced unstable-root events, and has no observed value-decoding failure.  It
made the pre-existing estimator bug easier to trigger by producing legitimate
one-frame samples in the empty, low-load part of a new scene.  The controller
feedback bug must be fixed before interpreting another full route.

## Stage-Level Evidence

| Metric | OPT-001 | OPT-002 | Change |
| --- | ---: | ---: | ---: |
| Stage 4A hits | 15 | 21 | +6 |
| Stage 4A decisions | 11,370 | 11,796 | +426 |
| Stage 4A frame span | 45,631 | 45,858 | +227 |
| Power at stage start/end | 31/2 | 11/0 | different incoming state |
| Read median/p95, ms | 9.840/11.913 | 8.676/11.154 | -1.164/-0.759 |
| Plan median/p95, ms | 33.368/51.953 | 31.232/47.156 | -2.136/-4.797 |
| Action-lag median/p95/max | 2/3/5 | 2/3/5 | unchanged |
| Focused decisions | 70.82% | 73.07% | +2.25 pp |
| Fast decisions | 29.18% | 26.93% | -2.25 pp |
| Bottom occupancy | 13.47% | 12.36% | -1.11 pp |
| Side occupancy | 10.10% | 9.05% | -1.05 pp |
| Corner occupancy | 2.65% | 1.71% | -0.94 pp |
| Stage deadline holds | 0 | 32 | +32 |
| Exact `[1]` delay-support decisions | 0 | 331 | +331 |

The boundary and fast-mode factors at the hit edges changed only from 13 to
14 and from 12 to 13, respectively.  Five of the six additional hits occurred
away from the report's boundary threshold.  The anomaly therefore is not an
increase in routine edge occupancy or fast movement.

The complete-route `player_control_root_unstable` count fell from 15 to two.
OPT-001 had no such event in Stage 4A; OPT-002 had one retry at source frame
108337, 143 frames after the nearest hit and 836 frames before the next one.
It cannot explain a pre-hit state corruption.  The new root-read counter has a
Stage 4A median/p95 of 0.275/0.368 ms.

Historical retained full routes also show that Stage 4A is high variance:

| Run | Total hits | Stage hit counts | Stage 4A |
| --- | ---: | --- | ---: |
| 20260730_222529 | 68 | `2/3/5/20/15/23` | 20 |
| 20260823_170206 | 85 | `1/8/14/14/18/30` | 14 |
| 20260823_183138 | 58 | `4/6/5/13/9/21` | 13 |
| 20260824_022909 | 61 | `5/2/5/15/15/19` | 15 |
| 20260824_034510 | 67 | `0/4/5/21/10/27` | 21 |

The value 21 is bad, but not unprecedented.  This history does not erase the
frame-exact controller failure below; it limits attribution of the remaining
different-root delta.

## Root Cause 1: Post-Reset Deadline Self-Lock

The exact Stage 3 to Stage 4A transition is:

- frame 72546, last old-epoch decision: support `[3,4,5,6]`, guard active;
- frame 72546, scene resumes and `AdaptiveControlDelay.reset()` clears all
  samples, pending state, counters, and `guard_until`;
- frame 72546, first new-epoch decision: default support `[2,3]`;
- frame 72547: one sample reduces support to `[1,2]`;
- frame 72648: 12 low-load end-to-end samples reduce support to `[1]`;
- frame 72949: `post_capture_advance=2`, action lag 2, but support is `[1]`;
  the deadline guard suppresses the new action and holds `stay`;
- frames 72949--73042: 32 consecutive decisions repeat the same deadline
  hold.  The player remains exactly at `(192,384)`, guard remains false,
  `overruns=0`, `censored=0`, and the 49 end-to-end samples do not change;
- frame 73042: the held position is hit, with action lag 2 outside `[1]` and
  pipeline clearance `-3.298`;
- frame 73047: only `register_hit()` has now activated the guard and widened
  support to `[1,2]`; frame 73050 widens it to `[1,2,3,4]` after the first
  observed overrun.

This is a feedback-loop defect in `AdaptiveControlDelay` plus the issue guard:

1. once any end-to-end samples exist, `estimate()` derives its support from
   those samples and does not include the more recent computation-lag tail;
2. `ActionIssueAlignment.deadline_missed` correctly detects that the current
   action lag already exceeds the support;
3. `apply_deadline_hold()` correctly refuses an action that was not planned
   for that late issue epoch;
4. however, the miss is not fed back as an estimator overrun or guard event;
5. because the held mask requires no new write, no later visible actuation can
   generate the sample needed to escape the underestimated support.

This condition is route-general.  OPT-002 also produced 361 exact-`[1]`
decisions in Stage 2 and 80 in Stage 3, versus zero in every stage of OPT-001.
Only Stage 4A combined the collapsed support with a sustained two-frame dense
planning load and a lethal wave, so only there did it lock through a hit.

## Source-Authoritative Cascade After The First Hit

The reference source makes the first hit a route-state divergence, not an
isolated `+1` that can simply be subtracted:

- `GameManager.cpp` defines difficulty index 3 (Lunatic) with initial/min/max
  rank `8/8/12`.
- `Player.cpp` sends the death path through `DecreaseSubrank(1600)`.  It sets
  Power to zero when current Power is at most 16, otherwise subtracts 16, and
  then spawns recovery Power items.
- `Player::FUN_00450f60` chooses the player shot table by current Power, so
  the drop changes damage delivery and phase timing.
- `EclDependencies.cpp` applies rank-scaled bullet count and speed only when
  `!g_Spellcard.IsActive()`.  Rank can therefore explain nonspell divergence,
  but it is not a direct spell-pattern explanation.

OPT-002 entered Stage 4A at Power 11 and the erroneous first hit reset it to
zero.  OPT-001 entered at Power 31 and did not take its first Stage 4A hit
until frame 74051.  Neither retained trace records `rank/subRank`, so the exact
native rank trajectory cannot be reconstructed after the process exited.
Future trials must retain these fields before rank is used as a causal
covariate.

Stage 4A's hit delta splits evenly: nonspell hits rose from 7 to 10 and
spell-attributed hits from 8 to 11.  It is not one broken card:

| Spell | OPT-001 hits / frame span | OPT-002 hits / frame span |
| --- | ---: | ---: |
| 57 | 3 / 3,085 | 3 / 3,082 |
| 61 | 0 / 2,789 | 1 / 2,817 |
| 65 | 2 / 2,754 | 1 / 2,725 |
| 69 | 2 / 3,054 | 3 / 3,081 |
| 73 | 1 / 3,086 | 3 / 3,145 |

All five spells remain near their fixed long exposure.  Their small span
differences do not support a large damage-duration explanation for the three
additional spell hits.  The first erroneous death, changed action trajectory,
native RNG, and absent global guidance leave subsequent per-hit matching
underdetermined.

## Root Cause 2: Hit-Row Attribution Is One Epoch Too Late

The original run dossier labeled frame 104767 as
`sensor_gap_or_unmodeled_hazard` because the hit-detection row has positive
pipeline clearance and no same-row bullet overlap.  The causal window says
otherwise:

| Decision frame | State |
| ---: | --- |
| 104761 | robust minimum clearance `+0.489`, zero predicted collisions |
| 104764 | issued `right`; robust minimum `-1.662`, `worst_collisions=1` |
| 104767 | native phase-2 edge observed; current pipeline clearance `+1.355` |
| 104768 | stable post-detection contact capture, after the lethal interval |

The bullet pool used by the hit row was bracketed at frames 104765--104766,
while player phase was read at issue frame 104767 and the extra stable contact
capture occurred at 104768.  A bullet can legitimately collide and move clear
before the hit row is assembled.  The classifier currently gives the positive
hit-row clearance precedence over the last alive decision's explicit selected
action collision.  That makes a known local collision look like a future-
birth/sensor gap.

The diagnostic-only fix preserves exact same-epoch observed overlaps as
the strongest witness, but classify a no-overlap hit as a modeled selected-
action collision when the last alive robust certificate already reports a
collision.  A genuinely positive last-alive certificate with no exact contact
witness remains explicitly unresolved. Replaying the untouched raw trace
reclassified this one hit and no others: the final route taxonomy is 43
modeled committed/selected-prefix collisions, 24 exact bullet overlaps, and
zero sensor gaps.

## Structural Cause: Local Traps Without Global Guidance

After excluding the first deadline-lock hit, all remaining 20 Stage 4A hits
have `robust_action_set_exhausted_before_hit`.  Their usable robust warning
lead is 3--21 frames, median six; OPT-001's median was seven.  This is not a
decoder that believes the path is safe.  It is a local controller that finds
all actions unsafe only after it has entered the trap.

The physical config confirms why:

- local planner horizon: 10 frames;
- global viability query count in Stage 4A: zero;
- robustly constrained global-policy decisions: zero;
- ordinary pre-exhaustion/future-birth authority: disabled;
- future hostile-birth coverage beyond current observed entities: `UNKNOWN`.

The authoritative source can simplify the missing producer model, especially
for Stage 4A's reached spell inventory (spell 65 has 27 transforms and spell
69 has 17).  Until those future emissions/transforms are versioned and fed to
a nonzero global policy, more CPU only makes the same short-horizon policy run
faster.  It does not create the information needed to avoid a future trap.

## Disposition And Ordered Follow-Up

1. Retain OPT-002's coalesced read implementation and physical latency
   evidence; do not claim a hit-rate improvement from the 67-hit route.
2. Correct the causal hit attribution and regenerate this run's compact
   dossier from the same raw trace. **Completed under AUD-023.**
3. Close the deadline feedback loop: a current issue deadline miss must
   immediately widen/guard the next estimate even when the write is held, and
   scene reset must not allow low-load samples to erase plausible computation
   tail support.  Add a regression reproducing the 32-hold self-lock.
   **Implemented offline as OPT-002A; physical route gate pending.**
4. Run the complete route again under the same isolated Wine and nonbinding
   duration contract before beginning another behavior optimization.
5. Add exact `rank`, `subRank`, min/max rank, and preferably graze/damage
   telemetry as shadow state so future cross-route analysis can condition on
   native difficulty feedback.
6. Then resume source-authoritative future-birth/global guidance.  Boundary
   and focus remain important overall, but this Stage 4A delta is not evidence
   for changing their scoring first.
