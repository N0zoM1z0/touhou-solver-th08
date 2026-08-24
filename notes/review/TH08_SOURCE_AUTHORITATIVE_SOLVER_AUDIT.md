# TH08 Source-Authoritative Solver Audit

Last updated: 2026-08-24.

Status: **AUDIT COMPLETE; BEHAVIOR CHANGE NOT YET PROMOTED**

## Scope And Verdict

This audit explains why the current Sakuya/Remilia Lunatic Route-2 solver
still records about 60 hits despite the VPS, the reconstructed source, and the
recent sensing/issue fixes. It uses the complete OPT-002A physical route, its
retained raw trace, the live solver implementation, and only functions marked
100% matching in `../th08/config/matches.csv` for source-authoritative claims.

The central verdict is:

1. The VPS has not yet been allowed to improve strategy. Across all 57,553
   decisions, the global corridor submission was due and authority-blocked;
   zero jobs were submitted and zero global viability queries existed.
2. The 60 hits are therefore mostly the expected failure mode of a 10-frame
   local controller. Fifty-seven of 60 deaths are preceded by robust action-set
   exhaustion; the controller sees the trap, but usually only after every
   short-prefix action has become losing.
3. The local hazard set is not source-exact. It inflates the player lethal
   half-extents from the observed `(1,1)` to `(2,2)`, treats nonlethal bullet
   lifecycle states as lethal, and lowers the native finite rotated laser
   rectangle to a capsule. These are confirmed implementation divergences,
   not speculative tuning complaints.
4. The current future-birth work is not connected to spell planning. The only
   generic ECL birth analyzer is trace-only, stops before most interesting VM
   behavior, and has no controller caller. The large ordinary-source model is
   disabled and intentionally rejects active spells.
5. The matching source makes a much simpler end state feasible: one exact
   runtime-root capture, one generic ECL/timeline/emitter forward kernel, one
   exact hazard geometry kernel, one time-expanded viability planner, and the
   already-validated robust issue layer. Per-spell caches and policies should
   be compiled from that kernel, not implemented as independent handwritten
   simulators.

The immediate next behavioral candidate is the source-exact collision and
lifecycle kernel, but only after a shadow differential records which legacy
hazards are false-positive or false-negative. Simply enabling the existing
global worker is unsafe because its active-spell requests omit future births
while the authority gate checks only time-scale provenance.

## Evidence Base

### Physical route

Run `lunatic_route2_fullrun_unattended_20260824_051944`, exact commit
`6b5d2d9bc26cfe0cbdea6dff4fd2566be6967c6e`, naturally reached
`route_complete` at manager frame 230561. It issued 57,553 decisions, recorded
60 native hit edges, passed the hard no-Bomb gate, and left no process in its
isolated Wine prefix.

| Stage | Decisions | Hits |
| --- | ---: | ---: |
| Stage 1 | 5,389 | 1 |
| Stage 2 | 7,217 | 4 |
| Stage 3 | 7,621 | 8 |
| Stage 4A | 11,487 | 15 |
| Stage 5 | 10,046 | 14 |
| Final B | 15,793 | 18 |

The immediate OPT-002 route recorded 67 hits with stage counts
`0/4/5/21/10/27`; OPT-002A changed those counts by
`+1/0/+3/-6/+4/-9`. OPT-001 recorded 61 hits with counts
`5/2/5/15/15/19`. These runs have different native RNG and post-hit state
roots, so neither the `67 -> 60` total nor any stage delta is a controlled
policy effect.

The subsequent clean GEO-001B shadow route
`lunatic_route2_fullrun_unattended_20260824_074407`, exact commit
`8b1c3de4de4f5c776644aaebab68e18d649eba2b`, naturally completed at frame
226632 with 56,539 decisions and 57 hits.  Its stage counts were
`3/7/4/15/10/18`.  Stage 4A therefore did not regress from the 60-hit route:
it remained at 15, while Final B also remained at 18.  Because GEO-001B was
shadow-only and changed no action, the total and stage redistribution are not
a controlled geometry-policy effect.  Stage-4A read and plan median/p95
improved from `9.450/11.543` and `32.465/50.844 ms` to `8.619/10.370` and
`31.410/49.044 ms`; action-lag median/p95 stayed `2/3` frames.

OPT-002A did close its intended mechanism. Only ten decisions missed the
modeled issue deadline, all recovered, no miss is on a hit's causal row, and
the former 32-decision Stage-4A self-lock did not recur. Action-lag median and
p95 remained about two and three frames. The route validates the estimator
fix, but its near-equality to OPT-001 shows that deadline feedback was not the
dominant residual hit mechanism.

### Exact reconstructed functions used by this audit

| Native function | Matched size | Source role |
| --- | ---: | --- |
| `EclManager::RunEcl` | 26,638 bytes | Main and four child VMs, timers, dispatch, callbacks, interpolators, post-dispatch motion |
| `DispatchShotInstruction` | 1,110 bytes | Dynamic operands, aim mode, rank, filters, origin, descriptor, spawn |
| `Bullet::FUN_0042ffc0` | 2,075 bytes | Bullet transform program execution |
| `BulletManager::OnUpdate` | 3,862 bytes | Bullet/laser lifecycle, movement, collision, timers |
| `Player::FUN_0044a230` | 302 bytes | Inclusive lethal bullet AABB collision |
| `Player::CalcLaserHitbox` | 651 bytes | Rotated-player versus finite laser rectangle collision |
| `Enemy::FUN_0042c290` | 284 bytes | Enemy/player body contact geometry |

Every row is marked `matching,100.00` in the source match ledger. The source
therefore establishes engine semantics for these paths. It does not by itself
supply a future runtime root: RNG state, VM locals/stacks, callbacks, player
path, enemy health, and phase timing must still be captured or branched.

## Why The Remaining Hits Occur

### Residual failure signature

The causal dossiers classify 41 hits as modeled committed-prefix collisions,
16 as observed bullet contacts, two as observed laser contacts, and one as an
enemy-body contact. The stronger planner classification is more revealing:

- 57/60: `robust_action_set_exhausted_before_hit`;
- 3/60: `late_collision_after_positive_causal_margin`.

The first usable robust warning lead is distributed as follows:

| Lead before hit | Hits |
| --- | ---: |
| 0 frames | 3 |
| 1–5 frames | 9 |
| 6–9 frames | 26 |
| 10–19 frames | 17 |
| 20+ frames | 5 |

This is not primarily a sensor that says a colliding action is safe. It is a
local solver that has already entered a region from which its 10-frame action
prefixes all collide. Stage-5 spell 107, for example, has exhaustion warnings
100 and 46 frames before two hits; one Final-B spell-170 warning is 49 frames
early. The local layer can report loss well before impact but has no long
horizon policy with which to recover.

### Boundary and fast-mode labels are correlates

Forty-eight hits carry the boundary factor and 43 carry the fast-mode factor.
The native playfield clamp and the solver bounds `x=8..376`, `y=16..432`
agree. The labels therefore do not prove that the bounds or movement speeds
are wrong.

They instead fit a combined mechanism:

- inflated and nonlethal hazards remove narrow interior actions;
- the 10-frame beam prefers a fast action that reaches a locally clearer
  endpoint;
- no long-horizon viability value penalizes entering a later dead end;
- once near a wall, clamping removes lateral successors and the local action
  set collapses.

Focus versus fast must be chosen inside an independently certified viable set.
The source does not justify a blanket focus penalty or an arbitrary boundary
reserve. A useful strategic value is future viable volume/escape width, not
distance from the nearest wall by itself.

## The VPS Global Planner Was Never Used

The physical controller was configured with four native corridor workers, a
16px grid, eight frames per layer, and an 80-frame horizon. It also set
`authority_only_corridor=true`. An exhaustive scan of the retained 2.05GB
trace found the same delivery state on every decision:

| Stage | Due | Scale horizon supported | Hard scale authority | Authority-blocked | Submitted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Stage 1 | 5,389 | 5,389 | 0 | 5,389 | 0 |
| Stage 2 | 7,217 | 7,217 | 0 | 7,217 | 0 |
| Stage 3 | 7,621 | 7,621 | 0 | 7,621 | 0 |
| Stage 4A | 11,487 | 11,487 | 0 | 11,487 | 0 |
| Stage 5 | 10,046 | 10,046 | 0 | 10,046 | 0 |
| Final B | 15,793 | 15,793 | 0 | 15,793 | 0 |

All schedules used provenance
`experimental_pretarget_unit_transport_unknown_direction`. The schedule
covered the numerical horizon, but `_time_scale_schedule_hard_authority()`
explicitly rejects that provenance. The route supplied only the Final-B
static ECL image, `no_scale_writer_schedule_authority` was false, and the
controller's submission condition consequently rejected every due job. The
compact dossier independently records query/available/viable/policy counts of
zero.

Thus more cores and memory had exactly zero opportunity to improve strategic
search. They only reduced or stabilized sensing and local computation.

### Hidden authority defect behind the gate

Removing the time-scale gate is not a valid fix. In ordinary nonspells, the
submission path requires an `ordinary_future_projection` when that optional
authority is enabled. In active spells, the normal corridor submission can
pass `future_hazard_projection=None`; its action authority is gated by hard
time-scale provenance, not by source-complete future hostile births.

That means a configuration-only change could turn a current-entity-only
forecast into hard action authority during a spell. The correct contract is:

`hard action authority = exact runtime root + exact scale schedule + complete
reached producer rollout + exact geometry/update order + robust delay prefix`

Any unsupported reached opcode, callback, child topology, runtime root, or
publication interval must make the affected horizon `UNKNOWN` and withhold
hard authority. A worker may still run in shadow mode to measure coverage and
latency.

## Source-Authoritative Geometry And Update Audit

| Area | Authoritative behavior | Current live behavior | Finding |
| --- | --- | --- | --- |
| Player lethal box | Runtime SHT half-extents; inclusive AABB | One scalar `PLAYER_RADIUS=2.0` | **Confirmed overinflation** |
| Bullet extents | Runtime width/height divided by two | Same | Correct |
| Bullet lethal lifecycle | State 1 only, and only when callback aux byte `+0x10B4` is zero | Every nonzero pool state is selected; lifecycle fields do not gate collision | **Confirmed false hazards** |
| Bullet update order | Transform handlers, velocity move, cull, lethal check, timer increments | State-2 recurrence plus mostly linear future motion and uncertainty | Partial |
| Laser collision | Player center rotated into laser-local space; inclusive AABB against finite rectangle | Lifecycle geometry lowered to segment/capsule radius | **Confirmed shape mismatch** |
| Enemy body | Full size divided by 1.5, then halved by player AABB helper | Enemy half-size is correct; player radius is 2 | Partial |
| Playfield clamp | Clamp player center to runtime rectangle | `8..376`, `16..432` | Correct for this route |

### Player lethal half-extents

`Player.cpp` initializes the lethal vector at `player+0x3D4` from the SHT
width divided by two, updates the cached lethal AABB after movement/clamp, and
uses that AABB in `FUN_0044a230`. All 60 stable hit-contact captures in the
OPT-002A dossier reconstruct half-extents `(1,1)`; 58 are bit-exact and two
differ only by float subtraction roundoff.

The live planner instead imports `PLAYER_RADIUS=2.0` into local bullet/body
checks, native packed hazard calls, global semantic generation/shrink, and
controller safety probes. `th08_laser_runtime.py` separately repeats the same
constant. Delay uncertainty is already represented elsewhere, so the extra
pixel is not a source-derived delay margin. It can erase two pixels of total
corridor width per axis and bias both local and global viable sets.

### Bullet lifecycle

`planning_bullet_active_slots()` selects all records whose native state is
nonzero. The decoder already retains `native_state`, state timer, and callback
aux state, but `_build_bullet_frames()` only treats state 2 specially and the
hazard kernels never filter collision eligibility.

In `BulletManager::OnUpdate`, only case 1 reaches the lethal
`Player::FUN_0044a230` block, and the entire collision block is skipped while
the callback aux byte is nonzero. Cases 2, 3, and 4 run spawn animation and
motion without killing the player; case 5 is cancellation/despawn. Treating
those records as lethal can create dense false walls exactly where the local
planner reports exhausted action sets.

The GEO-001B complete route now retains these fields.  Across 21,394,298
bullet-by-decision observations, 2,689,327 legacy candidates (12.5703%) are
not lethal under the source current-frame predicate.  Stage 5 is the clear
outlier at 1,125,175 of 4,973,810 (22.6220%); 840,965 are state-1 observations
on 1,120 decision frames where the Reisen callback auxiliary byte suppresses
collision.  Stage 4A is 484,249 of 4,214,434 (11.4902%) with no callback
suppression.  This establishes material Stage-5-specific false-hazard
pressure, but nearby geometry is retained only within 160 pixels and the
shadow had no action authority, so it cannot assign hit-count causality.

Current-frame eligibility is exact, but future eligibility is not a uniform
state timer.  States 2/3/4 leave their spawn animations when the associated
ANM VM script completes.  In addition, the 100%-matching
`ReisenFreezeBullets` and `FUN_00424c40` paths set and clear callback aux
`+0x10B4` based on ECL special-instruction/filter state.  A multi-frame exact
lifecycle projection must therefore retain and step the reached ANM VM and
callback controller; holding current aux or assigning a guessed fixed delay
would be false authority.

### Bullet motion and transforms

The width/height division is correct, and the retained state-2 recurrence is
consistent with the source's half-speed spawn motion. Active transformed
bullets are still projected mostly from current velocity plus heuristic
uncertainty. The exact 2,075-byte `Bullet::FUN_0042ffc0` and its flag handlers
are available, so current-bullet motion should become a canonical float32
stepper instead of accumulating pattern-specific uncertainty.

### Laser shape

The standalone `th08_laser_model.py` lifecycle geometry follows the source
well. The live consumer does not preserve the final collision primitive:
`pack_laser_frame()` converts the rectangle to a finite centerline segment
with `half_width + PLAYER_RADIUS`, and local/native hazard code performs a
closest-point capsule test. `Player::CalcLaserHitbox` instead rotates the
player center into laser-local coordinates and performs an inclusive AABB
overlap with a finite rectangle. Capsule end caps and rectangle corners are
not equivalent, and the player half-size is again inflated.

Only two current hits have a laser-contact primary label, so this is not the
dominant observed count, but the previous claim that the complete live laser
path was exact is retracted.

## Current Future-Birth Reality

The repository contains substantial future-source work, but none of it gives
active-spell action authority in the current route:

| Component | Actual scope | Live status |
| --- | --- | --- |
| `th08_ecl_birth.py` | Classifies one literal main-VM path; does not forecast geometry; stops on timer resets, common control flow, child topology, emission mutation, callbacks, or unknown opcodes | Trace-only; referenced only by its tests |
| `ECL_BIRTH_LOOKAHEAD_FRAMES=80` | Declared controller constant | No consumer; dead integration point |
| `th08_ecl_shadow/interpreter.py` | Narrow offline VM-local prefix | Stops on unsupported dependencies; no live authority |
| `th08_ordinary_future_sources.py` | Large fail-closed ordinary producer closure | Disabled in this route and rejects active spells/non-unit scale |
| `th08_future_birth_envelope.py` | Selected ordinary direct-fire envelopes/transforms | Partial helper, not route-wide spell births |
| Global corridor | Current bullets/lasers/bodies unless optional ordinary projection is active | Zero submitted jobs; spell future coverage absent |

The retained current-bullet ECL callback lookahead is also not a birth model.
Depending on stage, only 0–5,462 decisions reached its complete horizon; the
rest were missing a tag or stopped on control flow/timer resets. Those tags
can improve already-spawned bullet velocity prediction, but cannot warn about
the wave that has not been emitted.

The current complexity came from solving isolated pieces before there was a
source-complete execution kernel. The authoritative source now lets us replace
many overlapping special-case authorities with one common simulation path.

### Confirmed direct-fire semantic defects

The first source differential found two simpler defects before any new
architecture is enabled:

- `BulletManager::FUN_0042f5f0` centers fan modes 0/1 from
  `descriptor->count1 & 1`; `th08_future_birth_envelope.py` incorrectly uses
  instruction flags.  A deterministic 58,752-case mode/count/flag sweep found
  9,792 angle disagreements, all in modes 0/1.  In the statically decoded
  Route-2 inventory, 42 of 83 literal-count fan sites have differing count and
  flag parity; 22 of 45 fully literal sites are affected, including all four
  fully literal Final-B fan sites.
- Modes 0/2/4 automatically add the angle from the emitter to the player.
  `_pattern_speed_angle()` supports that input, but the ordinary direct-fire
  builder always records zero and causal conditioning therefore cannot
  recompute it for a candidate path.  The source atlas contains 128 such
  player-aim sites across the route.

The descriptor count fields are signed 16-bit fields even though ECL shot
arguments begin as 32-bit integers; the existing signed-low-word decode is
therefore correct and is not part of this fix.  Source `ZUN_PI`/`ZUN_2PI` are
binary32 constants, so spawn angle arithmetic must use their stored values
rather than Python's double-precision `math.pi`.  Rank adjustment is a
separate pending correction: source adds the full adjustment to nonzero
`speed1`, half to `speed2`, and clamps each adjusted speed to 0.3.

## Proposed Simpler Architecture

```text
coherent live root + candidate input/delay branch
                    |
                    v
       exact ECL/timeline/enemy forward kernel
                    |
                    v
      exact births + bullet/laser/body lifecycles
                    |
                    v
          exact per-frame hazard geometry
                    |
                    v
 adaptive time-expanded robust viability policy
                    |
                    v
 validated pending/held/fresh issue certificate
```

### 1. Coherent runtime root

Capture one versioned root containing the main and child VM PCs, timers,
locals/call state, enemy movement/emission descriptors, periodic/deferred fire
state, transform programs, laser state, RNG state, player SHT half-extents,
rank/subrank, health/phase gates, time scale, and relevant timeline state.
Bracket it with the same manager/frame checks already used by sensing.

### 2. One exact engine kernel

Implement the reached semantics of `RunEcl`, `DispatchShotInstruction`, enemy
post-dispatch movement/callbacks, bullet spawn/update/transform, laser
lifecycle, and contact geometry in native update order and float32 arithmetic.
Unsupported reached behavior returns a typed `UNKNOWN`; unsupported but
unreached code does not poison the horizon.

This should be generic. Each spell supplies ECL data and a runtime root, not a
new solver implementation. Offline compilation may index each spell's control
flow, emission sites, transform programs, and invariant branches, then cache
flow fields or policy fragments. Runtime execution joins that static program
with live locals, RNG, enemy state, and the candidate player path.

### 3. Action-conditioned futures

Player-aimed emission must be recomputed for each candidate path. RNG can be
exact when its state and all reached consumers are captured. Damage-dependent
phase transitions require either an exact player-shot/damage rollout or a
set-valued health/transition envelope. These are real remaining difficulties,
but the source identifies their exact boundaries; they no longer require
guessing opcode meaning or update order.

### 4. One viability planner

Feed exact hazard frames into an adaptive time-expanded predecessor rather
than separate local, corridor, ordinary, and envelope authorities. Use a
coarse grid only far from hazards and refine around narrow lanes/boundaries.
The hard set answers survival; future viable volume, escape width, focus/fast
cost, and boundary reserve rank actions only within that set.

The current robust delay quantifier and pending/held/fresh issue certificate
remain as the actuator layer. Those mechanisms have physical evidence and do
not need to be rewritten into the simulator.

## Ordered Implementation And Validation Plan

### A. Observability and shadow contract — no behavior change

GEO-001A now retains the native player lethal AABB/half-extents in the same
seven-call control-root transaction and preserves exceptional bullet
lifecycle state in compact/replayable traces. Decision rows expose a
source-collision shadow summary with an explicit no-authority role. The
legacy-versus-exact membership/action-set differential, exact laser-local
classifier, rank/RNG/producer roots, and global submission-gate expansion are
still open; observability phase A is therefore not yet complete.

GEO-001B adds the shadow-only `th08-source-collision-v1` kernel and a tracked
same-root differential. On retained root 2129, exact player geometry removes
13,040 of 32,893 legacy collision-grid positions; known state-2 lifecycle
removes another 351, with zero source-only points. All 18 one-step root-cohort
actions remain safe while minimum clearance increases by roughly 1.0–1.414px.
That action comparison is deliberately non-authoritative because the old root
lacks callback aux, omits seven H=1 births, retains four removals, and has no
lasers/bodies.

The complete-schema GEO-001B route closes the lifecycle-observability gate:
all 56,539 roots have stable `(1,1)` player half-extents and complete current-
pool state/aux counts, and the tracked streaming audit quantifies the 12.5703%
route-wide and 22.6220% Stage-5 legacy-only rates above.  It also records
393,216 laser observations and end-to-end timing without loading the 2.22 GB
trace into memory.  Exact route-wide geometry, future ANM/callback lifecycle,
and binary32 collision predicates remain open; phase A is therefore narrowed,
not complete.

1. Retain player lethal half-extents, bullet native state/timer/callback aux,
   exact laser-local rectangle, rank/subrank, RNG state, and the full reached
   VM/emitter root needed by the forward model.
2. Emit per-frame legacy-versus-source-exact hazard membership and action-set
   differences, including false-positive/false-negative reason codes.
3. Retain every global submission gate separately: scale coverage, scale
   authority, future-source coverage, root coherence, worker publication, and
   issue-version match.
4. Commit after focused decoder/trace/replay tests and an isolated Wine smoke.

### B. Exact lethal geometry and lifecycle — simplest promotion

1. Implement runtime `(half_width, half_height)` player geometry throughout
   local/native/global paths.
2. Gate bullets by native lethal state and callback aux state.
3. Preserve the exact rotated finite laser rectangle and correct enemy-body
   player expansion.
4. Differential against source-derived fixtures and retained physical roots;
   require zero exact-kernel disagreement before authority promotion.
5. Commit, then run one complete isolated Lunatic Route-2 gate. Compare not
   only hit count, but action-set exhaustion lead, false-hazard removals,
   boundary occupancy, focus/fast choices, and per-stage contacts.

### C. Exact current-entity forward update

Replace heuristic transformed-bullet propagation with the source-exact
transform/lifecycle stepper. Shadow old/new trajectories first, promote only
the covered exact subset, commit, and run the same complete-route gate.

### D. Global delivery in shadow mode

Build a source proof/capture for the time-scale schedule in every route stage,
not only Final B. Submit global jobs in shadow mode and require nonzero query,
completion, and on-time publication counts. Add the missing complete-future-
coverage authority gate before any action can consume a spell policy.

### E. Generic future births, producer family by producer family

Start with direct-fire/no-transform reached producers, then periodic/deferred
fire, player-aim modes, transform programs, lasers, child VMs/callbacks, and
timeline enemy births. Each family must pass source fixtures, retained-root
differentials, coverage accounting, and an explicit `UNKNOWN` test. Compile
per-spell program metadata from the same kernel; do not add handwritten
waypoints as authority.

Spell 170 is the largest current spell cluster at seven hits and is an
important later pressure gate, but the first semantic promotion should be the
simplest reached producer family, not the largest card-specific patch.

### F. Promote global viability authority

Only after scale, root, future-birth, geometry, and delay-prefix certificates
share one projection version should global viable actions constrain input.
Run focused Stage-4A/Stage-5/Final-B practices, then a complete route. VPS CPU
is expected to matter here: multiple exact candidate branches and adaptive
refinement finally produce work that can run on its cores.

## Success Metrics And Nonclaims

Every behavioral commit is followed by a complete isolated route as requested,
but different-RNG hit totals remain observational. Promotion also requires
mechanism metrics:

- nonzero and timely global submissions/queries/policies;
- future-source exact coverage in pre-hit windows;
- legacy/exact false-positive and false-negative hazard counts;
- robust exhaustion frequency and warning lead;
- viable-set size and boundary escape width;
- focus/fast selection inside the same certified viable set;
- sensing, planning, publication, and issue latency;
- per-stage/per-spell hits and hard no-Bomb integrity.

This audit does not claim that correcting the three geometry/lifecycle errors
will by itself remove a known number of hits, because the retained compact
trace lacks the required bullet lifecycle fields. It does not claim that every
future is deterministic under one root when candidate actions change aim,
damage timing, or RNG consumption. It does establish that the relevant native
semantics are now available, that the present strategic compute path was never
executed, and that a source-exact generic solver is both more defensible and
structurally simpler than extending the current collection of partial models.
