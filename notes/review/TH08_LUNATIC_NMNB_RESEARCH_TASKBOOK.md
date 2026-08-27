# TH08 Sakuya/Remilia Lunatic NMNB Research Taskbook

Last updated: 2026-08-27.

> Active scope override (2026-08-27): first close Sakuya/Remilia Easy Route-2
> Final-B NMNB as the online execution/model proof, then raise the unchanged
> general solver to Lunatic. The game may never wait for solver work or remove
> solver time from a game-visible clock. Linux is the search/replay-generation
> platform; original v1.00d Wine replay is final equivalence authority. The
> 2026-08-01 Hard/pause text elsewhere is historical evidence, not current
> authority. Source/runtime findings are tracked in
> `notes/review/TH08_SOURCE_AND_RUNTIME_AUDIT.md`.

## 1. Program Objective

Produce a physically validated original-game Sakuya/Remilia controller that
completes:

- Lunatic Stage 3;
- Lunatic Stage 4A;
- Lunatic Stage 5;
- Lunatic Final-B;
- a fresh Lunatic Route-2 game-start run;
- then Extra;

with no misses and no Bombs.

Offline witnesses, reconstructed-engine survival, replay completion, and
practice clears are milestones, not acceptance. Final acceptance requires
original-game physical execution, correct sensing/issue/timing/transitions,
retained resources and replay evidence, and repeated clean results.

## 2. The Progress Rule

The only meaningful optimization target is global solver performance:

- fewer canonical first hits or a later first hit under controlled roots;
- increased exact native survival horizon/minimum clearance;
- fewer physical hits across rotated workloads;
- ultimately NMNB completion.

Do not call more code, tests, reports, schemas, IDA labels, decoded fields,
planner nodes, or benchmark speed progress unless it causally enables one of
those outcomes.

Iteration comes first:

1. find the current first failure;
2. make the smallest falsifiable hypothesis;
3. run the smallest useful experiment;
4. change one general mechanism;
5. measure again;
6. either promote the winner or record the failure and pivot.

Use import smoke and affected focused tests while iterating. Full suites are
checkpoint gates. Physical play is sparse but mandatory. Broad audit,
formatting, CLI/schema polish, exhaustive checks, and unrelated refactors wait
unless they block the experiment.

## 3. Generalization Rule

Stage/spell identities are workloads, not algorithms.

Start with game-general mechanics:

- geometry and timing;
- hazard birth/update/removal;
- active/held/pending input;
- action-conditioned player and enemy state;
- Focus and movement speed;
- combat, enemy defeat, and resource transitions;
- robust planning and delivery.

Do not tune a waypoint, weight, mask, horizon, or exception for one spell
until a general formulation has been tried and a repeated native/physical
counterexample shows why the local exception is necessary.

Avoid the other extreme: do not postpone physical contact until the model is
“complete.” Rotate focused trials among Stage 3/4A/5/Final-B. A change that
wins one root must survive another root and another workload before
promotion. After a material integrated improvement, pay one fresh full-route
Lunatic diagnostic from zero Power.

## 4. Authority Ladder

Evidence increases in this order:

1. static reasoning or external reference;
2. shipped-instruction/dataflow revalidation;
3. deterministic unit/oracle case;
4. retained original-game native root and exact parent repeat;
5. action-conditioned native branches;
6. model/native first-mismatch differential;
7. integrated shadow/deadline evidence;
8. focused physical practice;
9. fresh full-route physical run;
10. repeated NMNB acceptance.

Never blur:

- exact finite-model feasibility and global optimality;
- offline/native evidence and live action authority;
- same-root causal comparisons and different-RNG observations;
- an immutable candidate and post-publication survival;
- static opportunity and executed native transaction.

## 5. Canonical Research Loop

### Step A — Localize

Use the first hit of a fresh run. Retain:

- canonical frame/root;
- player, hazard, enemy, resource, RNG, timing, and input state;
- collision object and signed clearance;
- content/model/policy versions;
- enough raw evidence for replay/root reconstruction.

Later hits are diagnostics, not independent clean-route samples.

### Step B — Reproduce

Re-run the recorded parent in original TH08. Require exact state and collision
classification at the declared seam. If it does not reproduce, fix capture,
root identity, or timing before touching the planner.

### Step C — Branch

Use the wind tunnel to execute candidate complete no-Bomb actions from the
same native root. Grow a causal tree by promoting actual endpoints to new
roots. Never attach the recorded future after an alternative action and never
force future RNG equal after execution diverges.

All 36 masks are useful at a decisive root; they are not mandatory for every
small edit. Search a representative subset first, then pay the portfolio when
selecting a durable witness.

### Step D — Differential

Run the same root/actions through the explicit model and native executor.
Compare every frame and stop at the first mismatch. Classify it:

- sensing/capture;
- player/control transition;
- hostile birth/update/removal;
- enemy/combat/resource;
- RNG/content;
- planner recurrence/objective;
- publication/deadline/actuation.

Fix the earliest responsible layer. Do not compensate downstream with a
weight or waypoint.

### Step E — Synthesize

Search only inside the declared causal model. Retain the exact witness,
minimum clearance, uncertainty branch, deadline, and failure mode. Timeout is
unresolved, not losing. Unknown-direction approximations cannot authorize
hard safety.

### Step F — Native confirmation

Execute the immutable winner in original TH08 from the identical root. Reject
it on state mismatch, unsupported event, collision, resource inconsistency,
or version drift.

### Step G — Integrated physical falsifier

Run one named focused workload that exercises the changed mechanic. Confirm
no Bomb, deadlines, pickup/no-write, transitions, and replay retention. Rotate
the next trial to another workload/root.

### Step H — Global check

After a material integrated improvement—not after every local edit—run one
fresh Lunatic Route-2 game-start diagnostic. Compare first-hit phase,
stage-attributed hits, resources/Power, deadline health, and failure-class
distribution. Use it to choose the next canonical root.

## 6. Active Workstreams

### WS-A — Native root corpus and wind tunnel

Current foundation:

- Stage-5 root 2129 reproduces exactly;
- original game executed all 36 root masks;
- 324 causal branches found an H=32 no-hit witness;
- natural pump matches 32/32 ticks;
- warm batching already demonstrates a large iteration-speed gain.

Next:

1. keep the current root as a regression;
2. add a small diverse corpus from Stage 3, 4A, 5, and Final-B;
3. include ordinary-enemy, spell, early-Power, dense-hazard, laser/transform,
   freeze/dialogue, and transition roots;
4. implement a persistent service only when single-writer/session poison
   recovery and rebootstrap are safe;
5. record branch throughput and bootstrap amortization, but optimize them only
   when they block solver iteration.

Success: one command reproduces and branches representative roots without a
whole-stage prefix per candidate.

### WS-B — Selective native semantic reconstruction

Implement only event classes exposed by a current first mismatch.

For each class:

1. compare external TH08/Touhou decompilation or reimplementation projects for
   orientation;
2. revalidate the shipped binary in IDA at instructions, callers/callees, data
   flow, layouts, and calling convention;
3. capture bounded runtime evidence where static proof is insufficient;
4. encode exact binary32/RNG/update order;
5. build an independent scalar oracle;
6. differential against original TH08;
7. return `UNKNOWN` outside the proven boundary.

External projects are accelerators for ECL/ANM/SHT formats, replay input,
mechanics, and naming. They are not authority for this exact binary, patch,
route, timing seam, or live memory layout.

### WS-C — Robust solver

Current 2026-08-27 priority override: the non-blocking Linux path now
structurally connects future-source closure and a real one-frame 4 px/H80
global winning set to named, non-relaxable local action authority. Preserve the
earliest pending policy so rolling solves cannot starve activation. Manager-
frame artifacts also require the implemented input/manager unit-cadence
certificate and matching async generation; dialogue/freeze/skip/mismatch
revokes them. The authorized short Easy delivery trace has now failed this
gate: 2,866 roots were clock-certified, but 574/574 future submissions failed
and publication/query/constraint counts were zero. CE-0273 is the authority.
Do not tune objectives, lead, grid, or beam. Protocol v4 now implements the
required runtime-owned leased packed source root, direct active-record
immediate decode, and one shared immutable reader for runtime identity, scale,
future, and global workers. The foreground owns no full-pool or large live
source scan. This is deterministic implementation evidence only; do not repeat
the physical trace until the unchanged configuration can retain packed-root,
producer, deadline, and finite/neutral-fallback telemetry and a physical run is
explicitly authorized.

That trace is not yet a hard-safety promotion gate. The required
native/structure-of-arrays path improves synthetic 800-bullet 8/12/8 p95
planning from 17.545 to 10.362 ms, but end-to-end 60 Hz capacity is unobserved.
The route withholds continuation leases until repeating the action has a
same-version second-layer global predecessor; current misses are neutral and
unresolved. The parallel nonphysical
research gate is an H32 all-17-action source factorization that measures the
first player/aim/damage/RNG/lifecycle divergence. Its result decides whether to
build the proposed shared flat source-order transition kernel directly or use
an exact-near/conservative-far hybrid. The complete decision is in
`notes/architecture/TH08_SOURCE_DRIVEN_ONLINE_SOLVER_20260827.md`; CE-0272
records the static integration corrections and CE-0273 records the physical
producer failure.

Keep robust reach-avoid/viability as the hard-safety backbone. The intended
hierarchy is:

1. exact current root and input belief;
2. hard collision/viability filter;
3. factored action generation: direction × duration × Focus;
4. within viable actions, rank interior clearance, useful position,
   nonspell damage/exposure, and Power;
5. refine canonical losing roots with causal action trees and exact witnesses;
6. publish only immutable, deadline-safe results.

Improve in this order:

- correct state/action/uncertainty;
- action factorization and horizon allocation;
- admissible dominance/canonicalization/bounds;
- selective resolution near first loss;
- objective shaping inside viability;
- implementation speed.

Alternative methods:

- MCTS/Monte Carlo/learned value/behavior cloning may propose or order
  candidates offline;
- model-predictive control can supply short-horizon receding decisions;
- imitation from demo/replay can provide priors, not safety;
- beam widening or learned pruning stays proposal-only unless an exact
  verifier checks the chosen action.

No heuristic may discard a safety branch or condition on hidden state without
proof.

The future-source geometry/version gate is closed deterministically. Stage-4A run
`20260731_152921` enabled the experiment but all 7,202 nonspell decisions
failed an invalid `player+0xE2A68 == 0` gate, producing zero action
constraints and zero early-kill applications. Native code shows that field is
a retained deathbomb-window limit. Counterfactual roots with only the gate
removed still permit `down_left` at global exhaustion and alias all 17
actions under an uncontrollable prefix and at the saturated corner. The
replacement now uses phase-only transition semantics, fresh prefix
certificates, exact active/held/pending pickup branches, a 4px Boolean lower
kernel with cell-radius clearance, and exact active-policy version binding.

Collision-control projection v14 and the fail-closed ordinary source executor
now cover the manager singleton, ordinary main/auxiliary ECL, callback gates,
emission descriptors, motion/phase state, and timeline births for the full
268-frame source horizon. The exact annular-sector/AABB projection is consumed
both before and after global publication. Observation-aligned native replay
roots 816/831/834/848/908 first falsify the old result: at the real H=80 the
16px signed predecessor is empty at all five roots. The factorized 4px lower
gate recovers exactly `left_fast/down_left_fast` at f817 and excludes the
retained losing active/issued actions; f833/f835/f850/f910 remain empty.
Native exact recurrence and the live adapter agree, with no unresolved
action. The first Stage-4A physical gate `20260731_220830` produced zero hard
authority because none of 1,754 sparse future-source captures completed; it
falsified capture/delivery rather than the finite-model set. The corrected
source v3 uses one contiguous manager+pool read and closes the reached
dynamic-count, auxiliary subtraction, indexed timeline field, and FRScreen
gate cases. Exact all-clear and terminal-first native paths remove the
3-second empty-field bootstrap; hard membership no longer pays eager soft
recovery cost. Complete Linux and Windows gates pass. The correctly
configured follow-up `20260731_231944` then completed only 1/1,859 source
roots because 1,836 contiguous captures still crossed manager frames; zero
hard decisions resulted. `20260731_230657` is configuration-invalid because
it omitted the runtime ECL identity flags. Persistent read-into storage and
zero-copy manager/pool views now remove about 10.6 ms of observer work from
the exact bracket.

That activation gate ran as `20260731_233856`: 119/1,914 source roots
completed and 196/193 ordinary constraints were applicable/effective, but no
useful nonempty authority survived within 80 frames of a hit. Treat capture
bracketing as activated and source-semantic starvation as current. Source v4
lowers captured enemy-angle variable `10069`, legal auxiliary timer roots,
and generic native opcode-`0x02` delay scheduling. Stage-4A
`20260801_002006` verified those two semantic failures disappeared, but exact
authority was absent from all 383 decisions in the 80-frame nonspell hit
windows. Complete roots 1137..1200 were stranded behind an UNKNOWN-source
future publication. Ordinary mode now refuses to spend a solver slot on
incomplete source coverage and uses a completed exact pending policy as the
pre-publication terminal kernel before its epoch. Revalidate that delivery
correction, then integrate armed health/timeout successor sources and the
remaining transform/opcode/callback/movement gaps without relaxing
fail-closed coverage. Total hits remain secondary different-RNG evidence;
local scoring and hostile-birth ranking remain later.

Stage-4A `20260801_004533` validates the pending-terminal correction: 110
effective nonspell decisions used a completed pending policy. It also
separates solver costs. Complete roots with up to 750 future sectors spent
6.1..23.2 seconds constructing exact signed-clearance volumes versus
0.23..0.81 seconds in the Boolean recurrence, and no authority reached a
nonspell hit window. The native sector kernel now uses exact grouped angular
unions plus disjoint frame parallelism; deterministic Python/native parity and
the f817/833/835/850/910 chain pass. Re-run Stage 4A before working on the
remaining phase/transform/opcode/callback/movement coverage. Run Stage 5 only
if Stage 4A shows the expected pressure-window authority improvement.

Stage-4A `20260801_011902` validates the sector implementation but exposes the
next causal deadline. Maximum physical clearance construction fell from 23.2
seconds to 0.993 seconds, yet exact authority remained absent from all 380
nonspell hit-window decisions. For the canonical frame-796 hit, source 639
spent 478 ms in clearance and 918 ms in Boolean viability and arrived after
the last nonnegative gate at frame 714. Therefore optimize the exact
set-valued recurrence before expanding source semantics. The implemented
all-action interior proof preserves the five-root action sets and cuts the
Windows maximum from 2,071 to 775 ms. Physically revalidate this deadline
correction; only then prioritize armed health/timeout successors and remaining
source gaps. Stage 5 remains conditional on useful pressure-window authority.

Stage-4A `20260801_015631` validates that recurrence correction: nonspell
viability maximum/p95 fell from 3,026/1,664 to 1,038/926 ms. Directional exact
sets occurred 102 times before first hit 2009, but all 238 nonspell hit-window
decisions still lacked authority. The canonical gap is now future transform
coverage, not armed phase succession: roots 1915..2007 repeatedly reached a
nonzero program, with opcode-`0x19` interleaved. Source v5 lowers the observed
player-relative stop/re-aim as a full-direction bounded disc and interval-adds
`0x19`; every unhandled active transform remains fail closed. Re-run Stage 4A
and require nonzero useful pressure-window authority before Stage 5.

Stage-4A `20260801_022228` removes transform and `0x19` from live failure
counts and reaches the first directional nonspell hit-window sets (5/8/6
actions at frames 3501/3518/3532). All three were deadline-held and therefore
ineffective: post-capture advance 15/16/12 exceeded pickup-support high 6
while held `up_right` persisted. Reserve controller/game capacity by lowering
the ordinary background owner priority and capping native workers at eight;
accept the retained Windows solve maximum increase 804→1,095 ms because the
initial publication lead is 80 frames and action sets are unchanged. Close
reached auxiliary `0x05`/`0x2E` exactly, then rerun Stage 4A. Stage 5 still
requires effective, not merely applicable, pressure-window authority.

Stage-4A `20260801_024419` shows that resource isolation is useful but not
sufficient: p95 solve latency improves slightly, one 5,290-ms tail remains,
and both directional hit-window policies miss issue by 20 frames. The reached
source blocker is now ordinary slot-0 phase arming (1,243/1,714 incomplete
roots); `0x05`/`0x2E` are absent. Capture exact phase timer and successors and
prove only far timeouts (`elapsed + H < timeout`) unreachable. Health-driven
or horizon-reachable successor transitions remain fail closed. Re-run Stage
4A and require effective directional pressure-window authority before Stage
5.

The current offline branch has now crossed the generic callback/global
integration boundary that this workstream previously lacked. Child/timeline
births, callback 14, exact bounded composition against the sensed pool, the
21-type global spawn lifecycle, and a projection/bullet/policy clock
certificate are connected through `CorridorSolution`. The controller only
submits a callback-bearing future under exact unit scale and a zero-span pool
capture, and performs the pool composition only after a due/free submission
slot exists. The join is rooted at that worker snapshot and is deliberately not
reused by later local-prefix certificates. Complete Linux discovery passes
1,511 tests with five skips. This is not progress by the taskbook's outcome
rule yet: no same-root losing kernel became viable and no Wine action was
issued. The smallest next experiment is a retained Stage-5 offline global
solve; close only its first reached producer/transform or overconservative-
geometry blocker, and pay a physical gate only after a useful policy arrives
within deadline.

### WS-D — Combat, Focus, and Power

This is the highest-priority experiment after cleanup.

#### D1: kill-before-saturation

Hypothesis: for ordinary enemies, survival improves when feasible actions
kill them before they emit dense aimed patterns.

Test:

- start from a generation-safe same root;
- restrict to survival-feasible schedules;
- branch Focus/unfocus/refocus and horizontal positioning;
- measure exact HP/defeat time, hostile births prevented, minimum clearance,
  and native survival horizon;
- repeat on a second enemy/root/stage.

Spells remain survival-first unless native duration reduction proves a
meaningful safety benefit.

Current checkpoint:

- one same-root Stage-5 branch defeated a 20-HP ordinary enemy and suppressed
  later hostile births;
- one default-off physical Stage-5 gate applied 27 fresh-safe unfocus
  preferences with zero Bombs;
- the different-RNG physical result moved first hit 2124→6981 but total hits
  12→13, while global policy guidance remained unavailable;
- the publication failure was a deterministic 120-frame diagnostic-scale
  horizon versus a 161–162-frame initial rolling-policy requirement. The
  repaired 269-frame path physically delivered 1,915 unique Stage-4A policies
  and 12,156 queries while remaining shadow-only;
- 26 of 39 actual fresh-safe early-kill selections occurred after shadow
  kernel loss and only nine were also shadow-global safe, so short local
  safety is not the intended survival filter;
- the following Stage-4A gate applied 124 preferences before first hit 4148,
  all inside a winning queried shadow-global set and fresh issue-safe set,
  with zero Bombs;
- the first attempt lost its last winning query at frame 3679. A 200-HP
  middle-wave enemy appeared near x=320 at frame 3864 but the old HP observer
  selected it only at frame 3900 at 15 HP;
- full-health ordinary targeting remains implemented default-off. The
  stable-clock/live-byte-verified fixed-spawn forecast was physically
  falsified and is now withheld from the live preference path;
- the authorized physical gate retained full-health body sensing but
  falsified the timeline forecast: all 376 observations recycled the same
  time-1 startup birth and only three affected input;
- preserve observed-body early kill inside the future exact ordinary viable
  set and fresh issue set; repair exact timeline lifecycle only before any
  future forecast experiment. First establish ordinary-stage pre-exhaustion
  authority,
  then repeat the native kill/prevented-birth result on a second root before
  promotion. This checkpoint supports D1 but does not promote it.
- the attempted scalar-reserve gate `20260731_152921` applied zero early-kill
  preferences because its eligibility source never activated. The result
  does not falsify observed-body early kill; it removes the scalar reserve as
  the proposed survival-feasible set.

#### D2: Focus as control

Do not assume Shift is always held. Unfocus may provide faster travel and a
different shot footprint; focus provides precision and another footprint.
Static coverage already rejects the simple “unfocused is wider” rule. Let
same-root native consequences choose.

#### D3: early Power

From a clean zero-Power prefix:

- find a survival-feasible collection path;
- observe allocation, pickup, and exact Power threshold crossing;
- carry the new Power state into later shot/combat behavior;
- require a causal later survival or exposure improvement.

Later dense sections remain survival-first. Post-death collection is not part
of an NMNB policy.

Detailed boundary: `notes/CURRENT_COMBAT_RESOURCE_MODEL.md`.

### WS-E — Live delivery

Only after an offline/native winner exists:

- add default-off shadow integration;
- prove immutable version matching and cancellation;
- measure compute/publication/issue deadline;
- preserve fresh local fallback;
- test held-mask no-write and pending action;
- validate manager-frame freezes/dialogue and transitions;
- then request a focused physical gate.

The issue thread performs lookup only. It does not start cold search.

## 7. Milestones

### M0 — Wind tunnel foundation

Complete. One canonical root supports exact parent repeat, causal branches,
H=32 witness, and natural-pump agreement.

### M1 — Representative root corpus

At least two roots per major event family, including more than one
stage/RNG/phase. Every parent repeats or is explicitly rejected.

### M2 — Closed short-prefix differential

The explicit model matches original TH08 for the root corpus until a declared
unsupported event, with no future reuse or hidden-state clairvoyance.

### M3 — General combat/control win

Kill-before-saturation, dynamic Focus, or safe Power produces a same-root
native survival/exposure win on at least two representative roots.

### M4 — Live delivery

One immutable candidate is available before issue deadline with version
matching, safe fallback, no stale publication, and no Bomb.

### M5 — Rotated practice closure

Repeated clean passes on Stage 3, 4A, 5, and Final-B. A change must not pass
only the workload it was developed on.

### M6 — Lunatic NMNB

One fresh game-start Route-2 run completes NMNB. Robust closure requires two
additional clean full routes on distinct natural RNG roots, for three retained
clean full routes total. These are final acceptance repeats, not iteration
gates paid after ordinary changes.

### M7 — Extra

Revalidate route/content/resource assumptions, extend the representative root
corpus, and repeat the same closure loop.

## 8. Physical Sampling Policy

Do not run all workloads after every change.

Use:

- one focused stage for the hypothesis;
- a different stage/root for generalization;
- a full route only after a major integrated gain or when stage interaction,
  zero-Power history, or transition/resource carry is the actual question.

Suggested rotation:

- Stage 3: early route, zero-Power/collection, ordinary enemy pressure;
- Stage 4A: dense geometry, lasers, broad control;
- Stage 5: canonical wind-tunnel and nonspell combat roots;
- Final-B: time-scale, boss/spell, late-route resources/delivery;
- full route: global resource/transition/generalization audit.

A physical run that changes RNG and produces fewer hits is encouraging but
not causal. Use its first hit to seed the next controlled root.

## 9. Measurements

Every candidate dossier should contain:

- immutable root/content/model/policy identity;
- parent-repeat status;
- action schedule and actual native input;
- first mismatch or unsupported event;
- native/model per-frame agreement;
- minimum signed clearance and collision object;
- enemy HP/defeat and hostile births when applicable;
- Power/lives/Bombs transactions;
- compute/publication/issue timing;
- exact witness or unresolved status.

Every physical dossier should contain:

- route/difficulty/team/stage and repository checkpoint;
- frames/decisions/hits/Bombs, first hit, stage/phase attribution;
- lives/Bombs/Power/items;
- deadline/fallback/foreground/transition health;
- replay and raw-bundle identity;
- whether comparison is same-root causal or different-root observational.

Primary program metrics:

- canonical first-hit survival horizon;
- repeated clean-pass rate per rotated workload;
- fresh full-route total and per-stage hits;
- fraction of first failures by model/planner/delivery class;
- native branches per warm session and time to a verified candidate.

## 10. Agent Task Card

Every research task begins with:

```text
Global failure:
Canonical root/workload:
Hypothesis:
Responsible layer:
Observable state and allowed actions:
Smallest falsifier:
Expected metric:
Focused tests:
Native/physical gate:
Stop condition:
```

Every handoff ends with:

```text
Observed result:
What was falsified or promoted:
Exact evidence:
Remaining first mismatch:
Effect on global hits/solver:
Next smallest experiment:
```

If “Effect on global hits/solver” cannot be answered, explain why the work was
necessary to unblock the next causal experiment. Otherwise do not prioritize
it.

## 11. Immediate Backlog

1. Keep the corrected capture/issue player-phase predicate; never restore the
   retained deathbomb-window limit as an alive-state gate.
2. Keep the exact active/held/pending predecessor and require the same future
   projection geometry across the publication prefix and corridor horizon.
3. Preserve fail-closed source semantics; never convert an unsupported
   ECL/timeline/callback/motion case into free space.
4. Keep the physically effective computation-delay/action-conditioned table:
   local ranking orders work only; the fresh exact issue-age row is authority.
5. Keep source-v14 future coverage fail closed. Stage-3 `152531` physically
   falsified lease v3 consumption despite 653 complete source roots, 267
   prepublication issues, 13 delayed issues, ten creates, and three renewals:
   both selected leases failed at issue. Lease v4 corrects only the retained
   false seams: contact-disabled bodies, decorated labels/SHOT-only pulses,
   and the redundant fresh-local veto. A
   compatible fallback root renews held/no-write first; another direction
   requires a new safe final-age predecessor. Root, epoch, stage, phase,
   pending support, exact position, expiry, old source semantics, unstable
   snapshot, or an uncontained fresh observation revokes it. Active hostile
   bodies use the original exact ECL/native-motion trajectory; never restart a
   fresh linear future. Preserve the native one-frame publication-to-motion
   phase: observations use published input; positions use shifted motion.
   Stage-3 `155718` then selected the compatible v4 lease 30 times and made
   29 held/no-write issues effective; terminal expiry was the sole revocation.
   This promotes the persistence seam only.
6. The retained f817/833/835/850/910 empty actual rows and physical
   f1456/f1469/f1470/f1479 and f3191/f3192 continuations regress. Stage-3
   `20260801_134853` produced only one hit/no-Bomb but zero leases because all
   ordinary roots lacked a future policy. Source semantics v12 removes its
   false finite-fraction UNKNOWN only under exact unit time scale. The repeat
   `141250` delivered 692 complete sources and 265 effective exact issues, but
   all four created leases were revoked by fresh-body containment and none was
   consumed. Parent `5fc6d92` cross-workload runs then produced Stage-4A
   18/10 versus direct baseline 21/12 and Stage-5 exactly 18/10 versus 18/10;
   zero leases were consumed in either. Preserve these fail-closed results.
   Source v13 now replaces the inconsistent fresh linear future with complete
   active-hostile source trajectories and observation-time containment; do
   not weaken unknown topology or future-source coverage. The v13 Stage-3
   rotation `152531` completed six hits/four nonspell, no Bomb, but zero
   effective leases. Its v4 successor `155718` completed seven/five with 29
   effective lease issues and no Bomb. Aggregate hits remain different-RNG
   observations. All five ordinary hit windows still lacked exact authority;
   the next gate is exact full-H268 source closure for reached main ECL
   `0x05`/`0x06` and captured movement state 2. Source v14 implements those
   semantics and fixes the state-3 timer current offset from `+0x2DDC` to
   `+0x2DE4`; missing timed roots remain UNKNOWN. Stage-3 `163434` confirms
   that correction physically: complete roots rose 645→801, full-H268 roots
   47→58, and the named failures disappeared. It still delivered zero exact
   authority in all three ordinary pre-hit windows. The first full root before
   f1253 was only 30 frames early and its 2352.884 ms solve completed at f1371,
   after the hit. Close newly reached exact `0x19`, `0x6F`, bottom-level
   `0x35`, and subsequent transform cases far enough upstream to cover the
   measured publication delay. Rotate Stage 4A only after deterministic
   source lead improves; hidden state remains fail closed.
   Source v15 now lowers those exact reached cases: main `0x19/0x1A`, dynamic
   i16 type/color, `0x25`, point-valued `0x6F`, and depth-zero auxiliary
   `0x35`. Motion-changing transforms receive a conservative disc bound and
   template replacement consumes maximum reached geometry. The actual Stage-3
   time-65 wave closes through six fires in the deterministic gate. Repeat
   Stage 3 and require earlier full-H268 lead plus authority in a former hit
   window; a label-only shift or no added lead fails the experiment.
   Stage-3 `171249` passes that narrow gate: 83 roots carried full H268 and
   the canonical f594 window had 13 full roots plus 43/50 effective exact
   prepublication issues. It instead exposes an unsafe computation gap.
   f565 certified held `down_left` only through f571; f566 then spent 394.522
   ms in the synchronous constant-H80 delayed scan and did not issue until
   f594. Retained slot 1 first overlaps the unchanged held path at f587.
   Before another stage rotation, require an exact held-action/lease guard
   before any long scan and prioritize current-kernel viable repair actions
   inside the bounded terminal probe. The guard must prevent this scan from
   starting; merely relabeling the later hit is failure.
   The guard and probe-order change are implemented. Retained f566 exact
   geometry rejects the held path, and current-kernel ordering selects
   `down_left/up_left/down`; 33/33 focused Linux and Windows tests pass. The
   rotated Stage-4A trace must show the guard blocking unsafe scans and no
   shadow-only widening.
7. Preserve the now-connected generic child/timeline/callback current-pool
   join. The existing four physical Stage-5 v1 capsules cannot supply the
   requested same-root solve because they omitted current bullets/lasers and
   their raw trace was cleaned. New explicit captures retain compact current
   hazards under the same clock. Current-hazard schema v2 now retains every
   queued native transform record plus active handler and culling state, while
   leaving the packed local decoder unchanged. The generic quick-stage
   regression also proves the old
   transform envelope unsound: 1,069/1,969 survivor samples escape it, worst
   97.060802px versus 31px. Global geometry v4 must therefore remain
   shadow-only whenever a current transform is active. The retained 18-record
   program now executes in source order in independent Python/C kernels;
   queue/immediates, eight motion handlers, barrier/wrap, movement, culling,
   and retirement pass long differential histories. Template replacement and
   derived births still fail closed. The persistent 1,536-state C kernel is
   0.02446 ms median, but Python conversion makes one wrapped frame 22.233 ms;
   preserve flat native state in the global worker.  The Easy diagnostic now
   has a 9-hit Final-B checkpoint.  AUD-093 source-confirms that two residuals
   are existing bullets whose pool ages were reversed relative to the final
   player root; exact pre-hit replay excludes the issued actions while other
   actions remain.  The corrected physical falsifier completes with 11 hits,
   but every contact is now observed or modeled; ten reach short-horizon
   action-set exhaustion.  AUD-094 showed that supported ages were incorrectly
   counted as simultaneous bullets.  The per-slot outward-rounded age hull
   now passes the exact contacts,
   complete suite, and atomic/straddled stateful differential while reducing
   a 400-bullet local pass about 13 percent.  The proposed unconditional
   10..32 local tail failed complete-stage A/B: constant-action continuation
   is not closed-loop viability and introduced a new hit.  Its conditional
   implementation now uses exact native/time-scale movement, while ordinary
   Easy retains the ten-frame beam.  Audit the first avoidable loss before the
   physical boundary/exhaustion contacts, then require a clean Final-B
   Practice before one complete Easy Route-2 NMNB attempt.  Then close
   template/derived births, connect a complete current-plus-future horizon to
   global shadow, take one fresh v2 Stage-5 root, and require a same-root
   losing-to-viable change plus bounded solve/publication cost before returning
   to Lunatic.  Use surplus VPS cores for parallel independent roots:
   controlled per-root scaling improves through 16 workers and regresses at
   24/32.

Optional warm-service work and learned/MCTS candidate ordering stay behind
this backlog unless branch latency becomes the measured bottleneck.

## 12. Stop Rules

Stop or pivot when:

- the parent root is not reproducible;
- the event leaves modeled authority;
- a candidate wins only through hidden-state knowledge or future reuse;
- an approximation has unknown-direction safety error;
- a deadline/fallback gate fails;
- two representative roots reject the hypothesis;
- focused physical repeats show no general benefit;
- work is accumulating tests/docs/schema without advancing the next causal
  solver experiment.

Record durable failures in `notes/counterexamples/CE-0220-0269.md`. Preserve
the complete chronology through `notes/RESEARCH_LOG.md` and other retired
history through the archive tag; keep the active taskbook about what to do
next.
