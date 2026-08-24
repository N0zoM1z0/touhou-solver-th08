# TH08 Lunatic Optimization Campaign

Last updated: 2026-08-24.

This ledger tracks the active sequence of general solver optimizations after
the source/runtime audit.  The semantic reference at `../th08` is used to
simplify and check the model; the shipped Japanese TH08 1.00d executable and
retained physical traces remain the authority.  Source/runtime discrepancies
continue to live in `TH08_SOURCE_AND_RUNTIME_AUDIT.md`.

## Objective And Reference

- Physical target: Sakuya/Remilia, Lunatic, Route 2, Final-B, hard no-Bomb.
- Current integrated checkpoint:
  `lunatic_route2_fullrun_unattended_20260824_034510`, 67 native hit edges,
  stage counts `0/4/5/21/10/27`, zero Bomb input, route complete. It ran the
  OPT-002 implementation at commit `f126fb2003f3142cb2b4fcbc003eba667967e270`.
- Immediate comparison reference:
  `lunatic_route2_fullrun_unattended_20260824_022909`, 61 native hit edges,
  stage counts `5/2/5/15/15/19`, zero Bomb input, route complete. It ran
  OPT-001 before the coalesced player-control-root change.
- Historical Windows reference:
  `lunatic_route2_fullrun_unattended_20260730_222529`, 68 hit edges, stage
  counts `2/3/5/20/15/23`.  It used pretarget guidance that is not accepted as
  source-authoritative under the current contract, so its lower local latency
  and useful-but-unsound guidance are diagnostic rather than promotion
  authority.
- Different natural RNG roots make route hit totals observational.  A change
  is evaluated first by its named mechanism and timing counters; hits and
  per-stage distribution determine whether the next causal investigation is
  worthwhile.

## Experiment Protocol

For every gameplay or live-runtime optimization:

1. Name one mechanism, its observable inputs, unchanged authority boundary,
   expected metric, and falsifier here before implementation.
2. Make one general change.  Do not combine it with a future-birth semantic
   expansion, planner ranking change, or stage-specific patch.
3. Require deterministic semantic parity or a focused regression, import
   smoke, affected tests, and the complete Linux suite at the checkpoint.
4. Commit the verified implementation with a clean worktree.
5. Run one isolated full Lunatic Route-2 diagnostic with the no-life-decrement
   patch, hard no-Bomb, retained native hit edges, and a nonbinding duration.
6. Record timing, activation/fallback, stage hits, first hit, cleanup, and the
   comparison here and in the source/runtime audit.  Commit compact evidence.
7. Keep, reject, or revise the change from evidence.  Start the next item only
   after that disposition is explicit.

The physical route is a global interaction check requested for this campaign;
it is not a same-root causal A/B test.  A lower hit count alone does not prove
the mechanism, and a higher hit count alone does not falsify a latency-only
change when its semantic and timing gate passes.

## Active Sequence

| ID | Track | Change | Risk | Status | Physical result |
| --- | --- | --- | --- | --- | --- |
| OPT-001 | sensing latency | Reuse one fixed 64-slot enemy-prefix RPM destination for planning and fresh issue recertification | low | VALIDATED-PHYSICAL | 61 hits; both prefix medians down about 1.2 ms; keep |
| OPT-002 | sensing latency | Coalesce input and position fields inside the existing bracketed player-control root, preserving duplicate before/after observations | low-medium | VALIDATED-MECHANISM | 67 hits; read latency down, semantic sensor evidence clean; keep, but route exposed OPT-002A |
| OPT-002A | control-delay correctness | Close the post-reset deadline-miss feedback self-lock without weakening issue freshness | medium | FIXED-OFFLINE | pending |
| OPT-003 | local/issue latency | Share immutable action-conditioned hazard projection work between planning and issue recertification where versions are exact-equal | medium | QUEUED | pending |
| FB-001 | future births | Build a source-guided, executable-validated producer inventory for the pre-spell-190 route and rank reached `UNKNOWN` causes by hit-window impact | low, shadow | QUEUED | pending |
| FB-002 | future births | Replace reached monolithic ECL special cases with smaller typed transition/emission primitives derived from source control flow and differential fixtures | medium-high | QUEUED | pending |
| FB-003 | future births | Publish complete future-birth geometry in shadow, then promote only exact versioned coverage through the existing global/issue authority gates | high | QUEUED | pending |
| BF-001 | boundary/focus | Add shadow attribution for boundary reserve, clamping, fast/focus choice, and committed-prefix collisions without changing input | low, shadow | QUEUED | pending |
| BF-002 | boundary/focus | Test a general viable-set ranking/refinement change on retained roots before any live promotion | medium | QUEUED | pending |

Only one row may be live-changing at a time.  Shadow-only instrumentation may
be prepared alongside analysis, but it must not silently influence action
selection.

## OPT-001 — Persistent Local Enemy-Prefix Destination

Status: **VALIDATED-PHYSICAL**

Global failure addressed: Wine sensing and fresh issue recertification consume
several physical frames before input, reducing useful reaction horizon.

Observed mechanism:

- `ENEMY_LOCAL_PREFIX_SIZE` is 64 and `ENEMY_STRIDE` is `0x53D0`, so each
  local prefix is 1,373,184 bytes.
- The planning capture and issue-time recertification each call
  `ProcessReader.read()` once per decision.  That path allocates and zeroes a
  ctypes destination, performs `ReadProcessMemory`, then copies the complete
  result through `buffer.raw`.
- The 58-hit reference made 55,024 decisions.  Across the two prefix reads,
  that is about 151 GB of repeatedly allocated destination storage plus about
  151 GB of redundant Python byte copies over the complete route.
- Retained decision records commonly place planning prefix capture and issue
  prefix capture near 3 ms each.  The bullet/laser pool sensor and ordinary
  future-source worker already prove the repository's persistent
  `allocate_buffer`/`read_into` pattern.

Change boundary:

- Allocate one exact-size local-prefix destination when the live controller is
  initialized and reuse it for the two sequential main-thread captures.
- Decode the memoryview completely into the existing immutable snapshot before
  the next read.  No mutable blob may escape in `EnemyPoolSnapshot`.
- Preserve addresses, pool extent, manager-frame before/after brackets, retry
  count, body/contact semantics, combat/ECL inventory decoding, and fresh issue
  comparison.
- Keep `reader.read()` compatibility for callers that do not provide a
  reusable destination.

Expected metric: lower `read_enemy_prefix_capture`,
`read_enemy_issue_prefix`, `read_pools`, and `observe_to_input` latency without
changing decoded snapshots or decisions for identical bytes.

Falsifier: any snapshot/body/inventory difference, changed read ordering or
clock bracket, mutable-buffer alias after return, test failure, new sensor
discontinuity, or no physical evidence that the persistent path was active.

Offline result: the controller owns one exact-size destination and both
planning and issue captures use it sequentially through `read_into`. The
legacy allocating path remains available to other callers. Tests cover byte
parity through decoded bodies, immutable snapshot lifetime after reuse,
destination identity, frame/read ordering, enemy-mode forwarding, and
fail-closed size/read-only validation. Affected tests pass 110/110, import
smoke passes, and complete Linux discovery passes 1,353 tests with five skips.

Physical gate: `lunatic_route2_fullrun_unattended_20260824_022909` completed
the complete route naturally with 61 native hit edges, stage counts
`5/2/5/15/15/19`, 55,915 decisions, and zero Bomb input. The controller
configuration records `read_path: persistent_read_into` and the exact shared
sequential destination. The host used the dedicated TH08 prefix/display,
reported `status=passed`, and found no exact-prefix leftovers. The 86,400
second controller duration and 86,700 second trial timeout were nonbinding;
termination was `route_complete` at frame 224868.

The retained 58-hit reference and OPT-001 trace give the following complete
route timing comparison. Values are milliseconds except action lag:

| Metric | 58-hit median / p95 | OPT-001 median / p95 | Delta median / p95 |
| --- | ---: | ---: | ---: |
| planning prefix capture | 2.764 / 3.317 | 1.543 / 1.929 | -1.221 / -1.388 |
| issue prefix capture | 2.944 / 5.499 | 1.707 / 2.967 | -1.236 / -2.532 |
| all pool reads | 10.468 / 12.168 | 9.371 / 11.358 | -1.097 / -0.810 |
| issue path to input | 3.945 / 13.489 | 2.620 / 12.242 | -1.326 / -1.247 |
| observe to input | 47.590 / 67.279 | 45.084 / 66.613 | -2.505 / -0.665 |
| action lag, frames | 2 / 3 | 2 / 3 | 0 / 0 |

Every stage's pool-read median improved, by 0.543 to 1.446 ms. Local-plan
timing moved in both directions with the different route workload, while the
named prefix-read mechanism improved globally and in every stage. Snapshot,
CSV, dossier, and rendered death evidence remain internally consistent.

Disposition: **keep**. The semantic-parity and activation gates passed, and
the direct mechanism improved materially. The hit change from 58 to 61 is
observational because the natural RNG roots differ; it is not evidence of a
strategy improvement. The candidate still has 48 modeled committed-prefix
collisions, 53 boundary-attributed hits, and 43 fast-mode-attributed hits.
OPT-001 removes avoidable host-copy latency but does not solve the dominant
future-guidance, viable-set, boundary, or focus failures. OPT-002 is therefore
the next live change; FB-001 and BF-001 remain the first source/strategy shadow
audits.

## OPT-002 — Coalesced Bracketed Player-Control Root

Status: **VALIDATED-MECHANISM; FOLLOW-UP REQUIRED**

Global failure addressed: every decision ends its hazard capture with a fresh
player/control root, and every `ReadProcessMemory` round trip contributes to
Wine sensing latency before input.

Source and executable layout evidence:

- The authoritative global map places `g_CurFrameInput` at `0x164D528`,
  `g_GuiMessageInputCurrent` at `0x164D52C`, and
  `g_GuiMessageInputPrevious` at `0x164D534`. They are three `u16` fields in
  one exact 14-byte readable slab; unrelated globals in the gaps are ignored.
- `Player.hpp` asserts `offsetof(Player, position) == 0x2B4`, and `position`
  is a `Float3`. The live controller consumes only its contiguous x/y prefix,
  exactly eight bytes.
- The existing root deliberately duplicates input and position around the
  scale read because player motion/input can advance while the enemy-manager
  clock is frozen. That duplicate observation is an authority boundary, not
  redundant work, and must remain.

Change boundary:

- Replace each group of three scalar input RPM calls with one exact 14-byte
  read and each x/y pair with one exact eight-byte read.
- Keep the exact order `frame / input-before / position-before / scale /
  position-after / input-after / frame`, the two-attempt limit, equality
  checks, scale bits, public capture fields, and fail-closed unstable-root
  behavior.
- Do not coalesce the distant manager frame, time scale, player object, or
  general `observe_state` spans. Do not change issue-time recertification or
  any planner/action ranking in this item.

One stable attempt therefore falls from 13 RPM calls to seven. At the 55,915
decisions in the OPT-001 route, that removes at least 335,490 scalar RPM calls
without removing a freshness observation.

Expected metric: exact decoded parity and read order in focused tests; lower
player-control-root/hazard-bookkeeping and pool-read latency in Wine, with no
change to identical-byte decisions.

Falsifier: any address/width mismatch, loss of a before/after observation,
changed retry/stability behavior, short-read acceptance, changed captured
values for the same bytes, test failure, or no physical latency evidence.

Offline result: the capture now performs the exact seven-call sequence and
publishes a dedicated `read_player_control_root` timing counter. Controller
config records the coalesced read path, byte widths, call count, and retained
before/after observations. Tests cover the authoritative offsets, exact call
order, stable decoding, frozen-clock position and input changes, coherent
retry, short input/position failures, and dossier metric retention. Focused
trace/dossier tests pass 17/17, Win32-compatible import smoke passes, and
complete Linux discovery passes 1,358 tests with five skips.

Physical gate: `lunatic_route2_fullrun_unattended_20260824_034510` completed
the route naturally at frame 229967 with 67 native hit edges, stage counts
`0/4/5/21/10/27`, 58,020 decisions, zero Bomb input, no foreground
interruption, and exact-prefix cleanup leftovers `[]`. The controller config
records the exact seven-call coalesced root. The host ran commit
`f126fb2003f3142cb2b4fcbc003eba667967e270` on the dedicated prefix/display
`:98`; its 86,400-second controller duration, 86,700-second trial timeout, and
86,880-second host timeout were nonbinding.

The direct physical mechanism passed:

- Stage read medians improved in all six stages, by 0.720--1.204 ms versus
  OPT-001; Stage 4A fell from 9.840 to 8.676 ms.
- Stage 4A plan median/p95 also fell from 33.368/51.953 to
  31.232/47.156 ms, while action-lag median/p95/max remained 2/3/5.
- The new Stage 4A root read itself measured 0.275/0.368 ms median/p95.
- Complete-route `player_control_root_unstable` events fell from 15 to two;
  the only Stage 4A retry was not in a pre-hit window. There is no physical
  evidence of coalesced-field corruption.

The 67 versus 61 total is observational, not a strategy win. Stage 4A rose
from 15 to 21 hits even though its focus, fast-mode, bottom, side, and corner
occupancy rates all moved in the safer direction. A frame-level audit found a
separate controller feedback defect: after the Stage 4A scene reset, low-load
samples collapsed delay support to `[1]`; frames 72949--73042 then produced
32 consecutive two-frame deadline holds without feeding the miss back into
the estimator. The player remained at `(192,384)` until the hit at 73042, and
only `register_hit()` widened support. OPT-001 had zero exact-`[1]` Stage 4A
decisions and zero Stage 4A deadline holds; OPT-002 had 331 and 32.

Disposition: **keep the coalesced read mechanism, do not promote the hit
outcome, and fix the exposed delay feedback loop next.** The faster low-load
capture legitimately exposed the estimator's unsupported assumption; it did
not falsify the source layout or read coalescing. The complete Stage 4A causal
record is in `TH08_OPT002_STAGE4_ROOT_CAUSE.md`. OPT-002A is the next live
change; no future-birth, planner-ranking, or boundary/focus behavior change
will be mixed into it.

Diagnostic follow-up AUD-023 was replayed without changing gameplay. Frame
104767's last-alive selected-action certificate already predicted a collision,
so the former sensor-gap label was a hit-row timing error. Regenerated compact
evidence contains 43 modeled collisions, 24 exact bullet overlaps, and zero
sensor gaps; all 67 hit identities and stage counts are unchanged.

## OPT-002A — Deadline-Miss Estimator Feedback

Status: **FIXED-OFFLINE; PHYSICAL GATE PENDING**

Global failure addressed: a proposal can arrive after the high end of its
modeled delay support. Holding the old input is required for safety, but the
no-write transaction cannot produce a future actuation observation. Without
direct feedback, a narrowed estimator can remain wrong indefinitely.

Change boundary:

- Preserve the current decision's fail-closed deadline hold exactly.
- Register the observed snapshot-to-issue lag only after the deadline test has
  proved it exceeds the support used for planning.
- For the next estimates, retain a temporary high-support floor equal to that
  observed lag plus the existing one-frame default pickup allowance, capped
  by the configured live maximum. Activate the existing 600-frame guard.
- Keep end-to-end samples, their quantiles, pending-command semantics,
  minimum/maximum delay bounds, hit guard, actions, planner ranking, and scene
  reset behavior otherwise unchanged.
- Expire the deadline floor independently from later hit guards, and clear it
  on a scene reset.

Expected metric: the first late issue remains a deadline hold, but the next
decision's support covers the observed issue lag and cannot repeat a no-write
self-lock. The physical config must report deadline-feedback v1, and trace
rows must expose a nonzero `deadline_misses` counter after activation.

Falsifier: an expired action is issued; the next support still excludes the
observed lag; the floor survives reset/expiry; support exceeds configured
bounds; identical non-deadline estimator sequences change; or the physical
route again contains a multi-decision deadline-hold streak at narrowed
support.

Offline result: `AdaptiveControlDelay.register_deadline_miss()` records a
separate deadline count, temporary support floor, and guard window without
fabricating a visible-input sample or incrementing actuation overruns. The
controller calls it on the exact `ActionIssueAlignment.deadline_missed` edge
before applying the unchanged hold. A regression recreates twelve one-frame
samples, support `[1]`, a two-frame no-write deadline, and verifies that the
next estimate becomes `[1,2,3]` without a hit; expiry and reset return to the
normal estimate. Focused control/trace/issue tests pass 18/18. Complete-suite
discovery passes 1,361 tests with five skips, and import smoke passes. Wine
smoke and the full-route gate remain pending.

## Future-Birth Simplification Contract

The reference source should reduce complexity by exposing native control-flow
shape, layouts, callback boundaries, and exact operand/update order.  It must
not be translated wholesale or treated as proof by name.  Future-birth work
will therefore proceed producer-first:

1. Map each physically reached hostile producer to the corresponding source
   transition and shipped executable/runtime observation.
2. Express shared timer, movement, ECL operand, callback, child-spawn, and
   emission behavior as small typed primitives with explicit `UNKNOWN` exits.
3. Differential those primitives on retained runtime roots before deleting or
   replacing older special-case code.
4. Compose versioned birth/body geometry, then measure complete coverage and
   publication lead in the actual pre-hit windows.
5. Keep coverage shadow-only until the existing active/held/pending prefix,
   global corridor, deadline, and fresh issue certificates all consume the
   exact same projection version.

This is expected to simplify reached semantics substantially, but complete
route-wide future births remain research-hard because action-conditioned aim,
RNG, callbacks, child VMs, phase changes, and unsupported opcodes must still
fail closed.

## Boundary And Focus Contract

Boundary/focus work begins with shadow attribution, not a new score.  It must
separate unavoidable committed-prefix collisions from avoidable selection,
record whether clamping destroyed lateral options, and compare focused and
fast alternatives only inside the same independently certified viable set.
No boundary reserve, focus heuristic, or recovery distance may widen hard
action authority.
