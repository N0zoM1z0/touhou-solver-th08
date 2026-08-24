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
  `lunatic_route2_fullrun_unattended_20260824_051944`, 60 native hit edges,
  stage counts `1/4/8/15/14/18`, zero Bomb input, route complete. It ran the
  OPT-002A implementation at commit
  `6b5d2d9bc26cfe0cbdea6dff4fd2566be6967c6e`.
- Immediate comparison reference:
  `lunatic_route2_fullrun_unattended_20260824_034510`, 67 native hit edges,
  stage counts `0/4/5/21/10/27`, zero Bomb input, route complete. It ran
  OPT-002 before deadline feedback. OPT-001 run `...022909` remains the
  61-hit latency reference.
- Historical Windows reference:
  `lunatic_route2_fullrun_unattended_20260730_222529`, 68 hit edges, stage
  counts `2/3/5/20/15/23`.  It used pretarget guidance that is not accepted as
  source-authoritative under the current contract, so its lower local latency
  and useful-but-unsound guidance are diagnostic rather than promotion
  authority.
- Latest source-AABB physical route:
  `lunatic_route2_fullrun_unattended_20260824_094658`, 93 hit edges, stage
  counts `4/7/5/20/31/26`, zero Bomb input, route complete.  It retains the
  correct physical AABB but rejects geometry-only promotion as a survival
  candidate: Stage-5 hit-row delay escaped the model and exposed a latency
  feedback loop.
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

Practice mode may replace a full route for fast localization after the focused
offline gates.  Its full-power root is never promotion evidence by itself:
the candidate must also pass retained low-power roots and the next complete
route.  The solver remains generic-first.  A stage/spell adapter requires a
repeated residual after shared source-kernel coverage, latency, and global
delivery gates pass.

The physical route is a global interaction check requested for this campaign;
it is not a same-root causal A/B test.  A lower hit count alone does not prove
the mechanism, and a higher hit count alone does not falsify a latency-only
change when its semantic and timing gate passes.

## Active Sequence

| ID | Track | Change | Risk | Status | Physical result |
| --- | --- | --- | --- | --- | --- |
| OPT-001 | sensing latency | Reuse one fixed 64-slot enemy-prefix RPM destination for planning and fresh issue recertification | low | VALIDATED-PHYSICAL | 61 hits; both prefix medians down about 1.2 ms; keep |
| OPT-002 | sensing latency | Coalesce input and position fields inside the existing bracketed player-control root, preserving duplicate before/after observations | low-medium | VALIDATED-MECHANISM | 67 hits; read latency down, semantic sensor evidence clean; keep, but route exposed OPT-002A |
| OPT-002A | control-delay correctness | Close the post-reset deadline-miss feedback self-lock without weakening issue freshness | medium | VALIDATED-PHYSICAL | 60 hits; ten misses recovered, no causal-hit miss or self-lock; keep |
| GEO-001 | source-exact geometry shadow | Retain runtime player half-extents and bullet lifecycle fields; compare legacy/exact hazards and action sets without changing input | low, shadow | COMPLETE | 57-hit route; 21.39M lifecycle observations retained |
| GEO-002A | conservative source geometry promotion | Exact bullet/body player AABB plus irreversible state-5 removal; retain activatable states and approximate laser | medium | VALIDATED-SEMANTICS; REJECTED-AS-STANDALONE-POLICY | 93 hits; Stage 5 31; keep physical truth, repair exposed timing |
| TIME-001 | capture/control timing | Exact lazy fresh-enemy recertification; then separate bulk-pool epoch and realized issue-delay uncertainty from physical hitboxes | medium | MECHANISM VALIDATED PHYSICALLY; ROUTE PENDING | Stage-5: 88.28% lazy; lazy `3.97/6.99ms`, fallback `62.45/76.42ms`; 28 observational hits |
| TIME-001B | local/control timing | Bound exact full-fallback and initial-beam work; benchmark process-isolated background services before changing ownership | medium | ROOT LOCATED | Spell 107 owns 300/351 fallbacks and cadence p95 13; background services are threads |
| MOT-001 | exact current entities | Replace heuristic transformed-bullet projection with the matching native update/transform semantics | medium-high | QUEUED | pending |
| GD-001 | global delivery shadow | Establish per-stage hard scale roots, submit jobs in shadow, and add complete future-coverage plus solution-version authority gates | medium, shadow | ROOT CAUSE CONFIRMED | one Final-B/Stage-1 mismatch; 50,669/50,669 due jobs blocked |
| FB-001 | future births | Capture a coherent VM/emitter/RNG root and implement one generic exact ECL/timeline/emitter kernel, starting with reached direct-fire producers | high | QUEUED | pending |
| FB-002 | future births | Extend the same kernel through periodic/deferred fire, aim/RNG, transforms, lasers, child VMs, callbacks, and timeline births | high | QUEUED | pending |
| FB-003 | global authority | Publish exact versioned hazard futures, promote adaptive viability only with complete coverage, then use VPS parallelism | high | QUEUED | pending |
| BF-001 | boundary/focus | Rank focus/fast and boundary escape only inside the same exact viable set | medium | BLOCKED ON GEO/FB | pending |
| OPT-003 | local/issue latency | Share immutable action-conditioned hazard projection work where versions are exact-equal | medium | DEFERRED | global queries and false hazards dominate first |

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
record is in `TH08_OPT002_STAGE4_ROOT_CAUSE.md`. OPT-002A was subsequently
validated by the 60-hit route below. No future-birth, planner-ranking, or
boundary/focus behavior was mixed into it.

Diagnostic follow-up AUD-023 was replayed without changing gameplay. Frame
104767's last-alive selected-action certificate already predicted a collision,
so the former sensor-gap label was a hit-row timing error. Regenerated compact
evidence contains 43 modeled collisions, 24 exact bullet overlaps, and zero
sensor gaps; all 67 hit identities and stage counts are unchanged.

## OPT-002A — Deadline-Miss Estimator Feedback

Status: **VALIDATED-PHYSICAL**

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
discovery passes 1,361 tests with five skips, and import smoke passes. The
subsequent Wine/full-route result is recorded below.

Physical result: run
`lunatic_route2_fullrun_unattended_20260824_051944` completed the full route at
frame 230561 with 60 hits, zero Bomb input, and exact isolated-prefix cleanup.
Ten issue-deadline misses were recorded and recovered; none occurred on a
hit's causal row, and the former 32-decision post-reset self-lock did not
recur. The intended mechanism is therefore validated. The stage counts
`1/4/8/15/14/18` and near-equality to OPT-001's 61-hit route do not establish
a hit-rate gain. They instead leave source-exact hazard geometry, future
births, and global viability as the dominant work.

## GEO-001 — Source-Exact Collision Shadow

Status: **IN-PROGRESS-SHADOW; RETENTION COMPLETE, DIFFERENTIAL PENDING**

The first checkpoint, GEO-001A, changes observation and trace data only:

- Each of the two existing player-position reads now retains the contiguous
  `player+0x2B4..0x3DB` window. The 296-byte window includes position, the
  cached lethal AABB at `+0x38C`, and the SHT-derived lethal half-extents at
  `+0x3D4`. The transaction remains seven RPM calls.
- The pre-existing action-facing `PlayerControlRootCapture.stable` predicate
  is unchanged: it still compares frame, position, and input only. New AABB
  and half-extent agreement is reported separately as
  `collision_geometry_stable`, so telemetry cannot reject or admit an issue.
- Decision rows now include `th08-source-collision-shadow-v1`: native player
  geometry validity/cache coherence and vectorized bullet native-state,
  callback-suppression, source-lethal, and legacy-only candidate counts. Its
  declared role is `shadow_no_action_ranking_or_hard_authority`.
- Nearby-bullet trace records preserve native state/timer/callback aux for
  exceptional records through `th08-bullet-lifecycle-v1`. State-1/aux-0 is
  the explicitly declared default and retains the old compact record shape;
  old trace replay remains accepted.
- Laser trace retention is marked, but no capsule-versus-native-rectangle
  action differential or authority change is included in GEO-001A.

Focused capture/trace/decoder/replay tests pass 28/28. Complete discovery
passes 1,365 tests with five skips. Controller import smoke passes, and a
10,000-iteration microbenchmark of the vectorized lifecycle summary at 2,000
bullets measured about 0.022 ms per call on this VPS. This is a latency sanity
check, not a gameplay-performance claim.

The isolated Wine smoke at exact commit `4cd5777` passed on private display
`:98`: exact executable/patch identity, Win32 Python/NumPy, native DLL, title
state, termination, and exact-prefix cleanup all passed with no leftovers.
The concurrently running TH105 Wine tree on `:121` and its separate prefix was
untouched. This is an import/launch gate; it does not claim that title-screen
state exercised gameplay collision telemetry.

A pure `th08-source-collision-v1` shadow kernel now implements separate player
half-extents, the state-1/aux-0 bullet lethal gate, inclusive bullet/body
AABBs, and the finite rotated laser rectangle. It preserves the existing
robust-uncertainty/risk weights so the differential isolates collision
semantics. The packed laser timeline now retains the already-modeled exact
rectangle width/orientation while its seven-field legacy/native capsule ABI
is unchanged. Current bullet frames retain projected native state and
callback aux for the shadow callback; live action still consumes the first
five legacy arrays only. Future native snapshot ledgers now retain callback
phase/aux as well as both timers.

The tracked root-2129 report
`artifacts/benchmarks/th08_source_collision_root2129_geo001_20260824.json`
compares all 153,873 integer-pixel playfield positions on the same retained
696-bullet root:

- legacy 2px geometry marks 32,893 positions colliding;
- exact 1px player geometry marks 19,853, removing 13,040 legacy-only points
  (39.6% of the legacy collision field) with zero geometry-only-legacy
  reversals;
- filtering the 28 known state-2 bullets removes another 351 positions,
  leaving 19,502; source-only-legacy remains zero;
- collision instances fall from 40,114 to 21,648, although overlapping boxes
  mean instance counts are not independent spatial cells.

On the H=1 root-active cohort, all 18 actions are safe under both models, but
source minimum clearance improves by about 1.0 to 1.414 pixels. This is useful
mechanism evidence and also explains why a geometry correction need not
immediately change every Boolean action set. It is not a complete action
certificate: native H=1 contains seven births and four removals, only 692
common slots have the retained exact-motion comparison, the old v2 root lacks
callback aux, and it contains no lasers or enemy bodies. State-1 bullets are
therefore conservatively kept lethal and the report explicitly refuses live
authority or hit-count claims.

That gate is now complete.  GEO-001B retained 21.39 million lifecycle
observations, and the conservative GEO-002A promotion passed the exact-kernel
differential.  Its physical route nevertheless regressed from 57 to 93 hits,
with Stage-5 hit-row lag outside the model.  The source predicate is retained,
but the next live change is TIME-001 rather than a wider lifecycle/laser
promotion.  AUD-036 through AUD-040 contain the disposition.

## TIME-001A — Exact Lazy Fresh-Enemy Recertification

Status: **MECHANISM VALIDATED PHYSICALLY; COMPLETE ROUTE PENDING**

Mechanism: a changed issue-time enemy prefix previously forced a complete
17-action robust certificate even when the already selected action remained
fresh-safe.  The retained 93-hit route contains 12,499 changed-prefix
transactions; 11,957 (95.66%) preserve a freshly safe planned action, while
all changed transactions consume 166.499 seconds of controller-thread
recertification.

Change: certify the planned action first and include the optional preference
in the same bounded probe.  Terminate only when the historical selection order
is already decided by a freshly safe eligible action.  Otherwise certify all
actions again in the historical batch context and run the complete selection.
Partial certificates are
versioned as `lazy_safe_selection`, expose only proven-safe actions, and carry
an explicit incomplete-action-set bit.  No hitbox, horizon, delay support,
ranking key, Bomb rule, stage condition, or global-authority rule changes.

Offline gate: the deterministic dense-safe 1,200-bullet differential produces
an identical selected certificate while reducing the median from 30.339ms to
2.306ms over 30 repeats.  Focused transaction, fresh-issue, trace, and audit
tests pass.  Falsifiers are any selected-certificate mismatch, incomplete-set
telemetry presented as complete, full-fallback selection mismatch, Stage-5
issue p95 not improving, or a full-route latency/hit regression without an
independent root explanation.

Physical gate: Stage-5 diagnostic `20260824_115819` completed with hard
no-Bomb. The exact lazy mode handled 2,644/2,995 changed transactions at
`3.970/6.992ms` median/p95. Exact fallback handled 351 at
`62.454/76.416ms`; 300 of them occurred in spell 107. Consequently the
mechanism passes while the aggregate p95 and 28-hit observational outcome do
not establish a survival win. Initial local planning is now the larger
generic cost (`39.657/103.971ms` overall, `94.653/122.495ms` in spell 107),
and the complete-route gate remains mandatory.

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

The post-route source audit sharpens this contract. The current generic birth
analyzer has no controller caller, the ordinary-source closure is disabled and
rejects spells, and every one of 57,553 global submissions was blocked before
worker execution. A configuration-only unblock is forbidden: active-spell
submission can currently omit future hazards while checking only hard
time-scale authority. Future work must converge on one generic source-exact
ECL/timeline/emitter kernel and require complete reached-producer coverage in
the same hard action certificate as geometry, scale, delay, and issue version.
See `TH08_SOURCE_AUTHORITATIVE_SOLVER_AUDIT.md`.

## GLOBAL-001A — Offline Exact Stage Identity And Scale Root

Status: **STAGE-5 PREREQUISITE CLOSED OFFLINE; GLOBAL ACTION AUTHORITY STILL
WITHHELD**

The first global-planner gate is now evaluated without Wine. A pinned catalog
maps every original Practice stage to its decoded ECL filename, native route
index, immutable SHA-256, and scale model. Source callback audits prove that
Stages 1--5, including both Stage-4 branches, cannot select the shipped scale
callbacks; Final A/B are explicitly dynamic. Stage 5 no longer inherits the
old `range(5)` omission.

The controller observes runtime ECL identity at the stable pre-plan root,
before scale resolution. Decision-frame and enemy-manager-frame identities
are carried separately through the no-writer inventory gate. The retained
offline integration proves that exact Stage-5 identity plus a coherent
complete active-VM inventory publishes the required 269-frame unit schedule
on the first transaction. The next offline gate is not another scale test: it
is a versioned global-job contract that keeps every current-entity-only or
incomplete future-birth solution shadow-only.

Intermediate changes in GLOBAL-001 use deterministic source/retained-root
differentials. Wine is reserved for the final Stage-5 delivery/survival gate
after shadow submissions, completions, freshness checks, and complete producer
coverage are all nonzero offline.

## GLOBAL-001B — Immutable Global Authority Join

Status: **VERSION/CONSUMPTION GATE CLOSED OFFLINE; STAGE-5 FUTURE PRODUCERS
OPEN**

The first post-scale audit found that active spells inherited action authority
from the time-scale gate alone. Future-hazard coverage was checked only on the
optional ordinary-nonspell lane, so a current-entity-only spell solve could
constrain live input. The correction does not stop useful shadow computation.
Instead, each job publishes one immutable join over the exact solver root,
runtime ECL, schedule, future hazards, geometry, and policy. The consumer must
match every member and require complete source coverage through the policy
horizon before exposing a global target or action set.

Five dedicated deterministic cases establish the positive join and the
missing-future, legacy-artifact, stale ECL/context/scale, projection, geometry,
and policy falsifiers. Re-rooting a proven constant Stage-5 unit schedule is
accepted semantically rather than rejected merely because its observation
frame changed. Together with the affected runtime/scale/pipeline tests, 40
focused tests pass. This is an authority-integrity improvement, not a survival
claim. GLOBAL-001C now measures reached Stage-5 producer coverage and shadow
delivery on retained roots; physical Practice remains withheld until those
metrics are nonzero and the candidate changes a same-root viability outcome.

## GLOBAL-001C — Mode-Correct Practice Image And Producer Census

Status: **MODE IDENTITY AND STATIC PRODUCER CONTRACT CLOSED OFFLINE; RUNTIME
PREFIX COVERAGE IN PROGRESS**

The first retained-trace census exposed an infrastructure blocker before any
producer extension: Practice Start loads the source-authoritative
`ecldata*sp.ecl` family, while the new catalog and Wine command pinned route
`ecldata*.ecl`. The catalogs are now mode-specific and the Stage-5 offline
identity/scale transaction uses `ecldata5sp.ecl`. This prevents an exact
identity service from correctly rejecting every Practice root before the VPS
workers receive useful work.

Across the retained 28-hit Stage-5 trace, callback-12 lookahead already covers
all 1,986 decisions in spells 103/107/111. Spell 115 has 721/732 incomplete
rows at its unsupported callback-14 path. The next generic checkpoint is
therefore not a wider callback-12 horizon: compile and test route/Practice
spell producer topology, admit active-spell direct-fire prefixes into the
existing fail-closed future-source kernel, and then lower child sources and
callback 14. Wine remains a final acceptance gate after offline projection
coverage and same-root global viability changes are nonzero.

The machine-readable producer contract now pins both Stage-5 images and proves
normalized program equivalence for route spells 103/107/111/115/118. It also
provides the exact direct-fire/transform/child/callback site denominator and
fails if a literal target becomes dynamic. This closes the static census but
does not promote a lexical branch to a reached future. The next implementation
step reuses the captured VM-root executor to consume this topology, beginning
with prefixes that stay within already-supported direct-fire semantics and
truncating before every unlowered child or callback effect.

## Boundary And Focus Contract

Boundary/focus work begins with shadow attribution, not a new score.  It must
separate unavoidable committed-prefix collisions from avoidable selection,
record whether clamping destroyed lateral options, and compare focused and
fast alternatives only inside the same independently certified viable set.
No boundary reserve, focus heuristic, or recovery distance may widen hard
action authority.

The OPT-002A route reinforces that ordering: 48/60 hits were boundary-labeled
and 43/60 fast-labeled, but source audit found correct native center bounds,
an inflated player lethal box, nonlethal bullet states admitted as hazards,
and zero global queries. Boundary/fast labels are therefore correlates of
local trap entry, not sufficient evidence for a new scalar penalty. Compare
focus and fast only after the exact hazard kernel defines the same viable set,
then rank by future viable volume/escape width.
