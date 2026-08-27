# Source-Driven Online TH08 Solver

Last updated: 2026-08-27.

Status: **architecture decision and implementation target**. The existing
future-projection/corridor path is now connected to Linux online action
selection as a transition baseline. It is not the intended final solver.

## Verdict

The non-blocking Linux execution boundary is the right boundary. The current
solver representation is not.

Keep two scheduling tiers:

1. a small exact next-frame shield that always races the next 60 Hz input
   epoch; and
2. a rolling background reachability computation that can take hundreds of
   milliseconds while the game continues.

Do not keep three independently evolving models of the same world as the end
state: a current-pool local beam, a set-valued future-birth envelope, and an
exogenous-hazard corridor. They create expensive joins and lose the most
important source dependency: the future world is a function of the selected
player path.

The intended end state is one source-order transition kernel used by both
tiers. The immediate tier evaluates its first physical-frame edges. The
background tier expands and solves the same edges farther ahead, publishes a
versioned viable successor set, and never blocks the game.

### Feasibility judgment

It is **hypothesized** that Easy Route-2 NMNB is achievable by this
deterministic, non-RL online route. Nothing found in the authored update order,
input boundary, or retained hazard semantics imposes a structural need for
stopped time. The existing exact collision, ECL, lifecycle, scale, and global
viability components also cover the necessary kinds of state.

That is not a completion claim. No physical online trace has yet shown that
the new authority is both queried and delivered at useful frequency, and the
current held fallback can outlive its one-frame witness. Lunatic feasibility
depends on branch sharing and incremental rebase keeping the background graph
bounded; Gate 2 below is the explicit falsifier. The route is therefore
architecturally plausible, while present NMNB effectiveness remains
**unobserved**.

## Physical Contract

- Objective: Sakuya/Remilia Easy Route-2 Final-B NMNB, then Lunatic Route-2
  NMNB.
- Hard constraints: original logical cadence, no stopped game time, no
  subtracted solver time, no Bomb bit, and no stale action.
- Observation: one immutable post-update native root and older publications.
- Action: one complete mask for exactly the next input epoch. Selecting the
  held complete mask is no-write.
- Immediate uncertainty: none in Linux command pickup after an exact packet
  is accepted; a missed deadline retains the held mask. Model/content
  uncertainty remains explicit and fail-closed.
- Deadline: the next physical `Controller::GetInput` epoch. Late results are
  discarded rather than queued.
- Fallback: held complete mask while the bridge is connected; neutral
  Shot+Focus after disconnect or bridge failure.
- Falsifier: a wrong-epoch action, Bomb, game-thread wait, noncausal future,
  or an action advertised as viable without a matching source transition and
  continuation witness.

## Why Native Linux, And What It Does Not Solve

Native Linux is selected as the search and replay-generation platform because
the solver can own an exact, local input-epoch protocol at the authored sample
boundary, capture native state through `/proc/<pid>/mem`, and rebuild/instrument
the game without a Wine/Windows cross-process input and sensing path. The
non-blocking Unix sequenced-packet mailbox gives explicit on-time/late
semantics, and the Linux replay writer preserves the realized input stream for
later proof. These are **observed implementation advantages**: they reduce
boundary ambiguity and make deadline failures measurable.

Linux is not numerical or semantic proof of TH08 v1.00d, and it does not make
the planner arithmetic intrinsically cheap. Compiler, floating-point, source
reconstruction, and runtime differences remain possible. The original
Japanese executable under Wine therefore remains the final `.rpy` playback
authority. Retained 17.72 ms mean / 32.17 ms p95 foreground timing also shows
that Python beam preparation, rather than Wine sensing alone, is already over
the physical budget. Linux is the better controllable execution boundary, not
a substitute for the shared flat kernel or for replay equivalence evidence.

## Authored-Source Findings

The following are **observed** in the authored reconstruction and its 100%
matching functions. Addresses refer to TH08 v1.00d.

| Calc priority | Relevant work | Consequence |
| ---: | --- | --- |
| 0 | `Supervisor::OnUpdate` samples `g_CurFrameInput` | Input is known before the gameplay update. |
| 7 | replay RNG root capture/reset | RNG provenance belongs to the physical update root. |
| 9 | `Player::OnUpdate` / `FUN_0044AEC0` resolves direction/focus, moves and clamps the player, updates hitboxes/options/shots | The new action changes this frame's player state before hostile births. |
| 11 | `EnemyManager::OnUpdate` applies player-shot damage, runs timelines and active enemy `RunEcl` instances in slot order | Focus/position can change damage, phase timing, ECL control flow, and births. |
| 12 | spell update | Spell state and time-scale effects are part of the same ordered transition. |
| 14 | `BulletManager::OnUpdate` runs spawn states/transforms, moves, culls, and checks collision | A birth from priority 11 can move and become relevant in the same logical update. |
| 17 | replay recording copies actual `g_CurFrameInput` | The saved replay attests the realized input sequence after gameplay consumers. |

`DispatchShotInstruction @ 0x00422720` and
`BulletManager::FUN_0042F5F0` show that aim modes 0/2/4 read the current player
position when the descriptor is spawned. `EnemyManager::OnUpdate` evaluates
player-shot damage before its ECL loop. `BulletManager::OnUpdate @ 0x00431240`
then advances the resulting bullet states and performs collision later in the
same update.

It is therefore **inferred** that the post-update publication now installed
in the Linux runtime is the correct causal seam: action `a[t+1]` is chosen
from state `S[t]` and is sampled before the transition to `S[t+1]`.

It is also **inferred** that a single precomputed hazard movie cannot be the
complete planner state. At minimum, future hostile state depends on:

- player position at aimed-fire sites;
- focus, option state, and player-shot geometry;
- enemy damage, health gates, death, and phase timing;
- RNG state and the reached call order after a branch;
- time scale, ECL children/callbacks, bullet transforms, and laser lifecycle.

A conservative envelope can remain safe, but widening every player-dependent
birth over a large reachable rectangle destroys the narrow corridors that a
survival policy is supposed to find.

## Assessment Of The Current Stack

### Retain

- exact Linux input epochs, non-blocking publication, late discard, held
  no-write, hard no-Bomb, and Wine replay proof;
- coherent source capture and immutable content/runtime version joins;
- exact scale authorities for Stages 1--5 and Final-B;
- source-stateful ECL/timeline/birth/lifecycle work already validated offline;
- signed-clearance collision kernels and the independent scalar/C oracles;
- hard-set intersection and losing-state labels, with objectives only inside
  the viable set.

### Replace as hard planner representation

- the width-24, H10 local beam as the only path search;
- an action-independent future envelope as the primary description of aimed
  births;
- a uniform spatial grid as the only global state representation;
- a control layer longer than one physical frame when its first action is
  consumed by a controller that can change action next frame;
- Python object reconstruction on every projected world step;
- stage/spell-specific planners or waypoints standing in for engine
  semantics.

The current local/global separation is thus not wholly wrong. Its deadline
separation is necessary. Its duplication of transition semantics is the
problem.

## Target Architecture

```text
                 immutable post-update root S[t]
                              |
             +----------------+----------------+
             |                                 |
             v                                 v
  exact next-frame shield             rolling source compiler
  T(S[t], each action)                 + branch-aware viability
             |                                 |
             +-------------+-------------------+
                           v
        intersect immediate-safe actions with a fresh
          version-matched viable-successor publication
                           |
                           v
              exact action for input epoch t+1
```

### 1. Runtime-owned packed observation ring

The Linux runtime should eventually publish an immutable packed root rather
than require Python to reconstruct large object graphs from many scalar
reads. The ring contains raw binary32/native fields and a monotonically
versioned update epoch. The solver remains a separate process, and the runtime
does not accept gameplay/RNG writes.

This is **proposed**, not yet implemented. Its falsifier is measurable frame
perturbation or semantic drift versus the current native state and replay
differential. Until it passes, `/proc/<pid>/mem` coherent capture remains the
authority.

### 2. Compiled source event tape

Decode static ECL once and compile reached instructions into an immutable
event/control-flow tape. Join it at runtime with VM PCs, timers, locals,
children, enemy slots, health, rank, RNG, scale, and active bullet/laser
state. Each operation is tagged by dependency:

- `WORLD_ONLY`: identical across player actions;
- `RNG_ONLY`: identical while reached RNG call order is shared;
- `PLAYER_AT_EVENT`: aimed birth or player-relative operation;
- `DAMAGE_GATED`: health/death/phase control flow;
- `UNKNOWN`: reached semantics without an exact or conservative executor.

This makes branch sharing explicit. Most world-only work is executed once;
only player- or damage-dependent suffixes fork.

### 3. One flat native transition kernel

Define the actual planner primitive as:

`T(versioned_world_state, complete_input_mask) -> successor | UNKNOWN`

It runs in authored physical order and binary32 arithmetic. State is stored
in flat structure-of-arrays buffers with copy-on-write pages or compact
branch deltas. A candidate does not copy the full enemy and 1,536-bullet
world. It references a shared spine and records only divergent player,
emission, damage, RNG, and lifecycle state.

The existing native 1,536-state bullet step is already fast; retained
evidence shows the Python preparation wrapper, not the arithmetic kernel, is
the current cost center. The new boundary must therefore ingest packed roots
and retain flat state across frames.

### 4. Immediate exact shield

For every online root, evaluate all legal no-Bomb next actions through at
least the next complete physical update, including births before priority-14
collision. This tier has no beam and no spatial discretization. It publishes
an exact immediate-safe set or `UNKNOWN` before the next input epoch.

If no background continuation is available, rank immediate-safe actions by a
bounded survival value, but do not call them globally viable. If the deadline
is missed, publish nothing; the bridge retains held input.

The timing target is measured end to end, not assigned to one function. The
first engineering gate is p95 capture+decode+shield+send below 12 ms, p99
below 16 ms, zero wrong-epoch accepts, and an explicit count of consecutive
held fallbacks. These are promotion targets, not current measurements.

### 5. Rolling branch-aware viability graph

The background worker expands the same `T` edges. A node key includes every
state component that can affect a future observation or transition. Nodes may
merge only when those components and the next observable branch agree. A
position-only merge is not valid after different aimed births or damage
histories.

Near the query root, every edge is one physical frame. Farther ahead, the
worker may use adaptive temporal/spatial slabs only if a macro edge represents
the ability to choose at every internal physical frame; it may not silently
mean “hold this action for eight frames.” Fine 2--4 px cells or exact reachable
positions are used around hazards, walls, and viability boundaries; empty
space can remain coarse.

The publication should be a content-addressed policy graph/slab with:

- exact source/context/RNG/scale/model versions;
- covered physical frame interval;
- root state/signature and branch assumptions;
- viable first-action set and successor witnesses;
- typed unsupported/timeout regions;
- max-survival and bottleneck values for losing states.

On the next observation, a matching realized successor rebases the graph by
dropping its consumed layer. Divergence revokes only the incompatible branch,
not every still-matching shared slab.

### 6. Lexicographic objectives

The order is:

1. survival/viability;
2. future viable volume, escape width, and worst-branch clearance;
3. damage and phase duration;
4. Power/item collection and useful position;
5. movement smoothness and other tie breakers.

Fast/focus and wall distance are not global heuristics. They are action
properties ranked inside the viable set. This directly addresses the Easy
31-hit signature without assuming that boundary occupancy itself is the
cause.

## Transitional Online Authority Implemented Now

The current Linux branch deliberately wires the existing components before
replacing them:

- future-source capture and global corridor work run asynchronously;
- runtime ECL, scale, projection, geometry, context, and policy versions are
  joined fail-closed;
- a complete future projection is supplied to local hazard evaluation when
  its remaining coverage spans the full local horizon;
- a real global winning action set is passed as named hard action authority;
- any named hard set may be narrowed by fresh local evidence but never
  relaxed;
- the earliest completed future policy remains pending until its source epoch,
  and no newer solve is submitted meanwhile, so rolling publication cannot
  postpone the first queryable policy forever;
- the online global recurrence uses one physical frame per control layer; and
- manager-frame policy time is admitted only inside a generation-tagged 1:1
  interval with the physical input epoch, with explicit dialogue,
  scripted-freeze, manager-skip, player/Bomb, and context fail-close gates.

The last correction is essential. The generic predecessor holds one selected
action for its complete layer. The historical eight-frame policy cannot be
queried at an intermediate frame and then consumed as a freely changeable
one-frame action. It remains useful as soft far-horizon guidance, not online
hard authority.

The pending-publication rule is equally a correctness condition, not only an
optimization. A producer that finishes more quickly than its 80-frame lead
would otherwise replace an epoch-180 pending result with epoch 188, 196, and
so on before any result became active. This starvation was **inferred from the
state machine and fixed before physical promotion**; a deterministic
regression now proves that the earliest pending epoch becomes active.

The dual-clock rule is also a correctness condition. **Observed in authored
source:** the EnemyManager skip flag can stop its frame counter at the early
return, while scripted global freeze can stop bullet/individual-enemy motion
without stopping the manager callback's final counter increment. **Inferred:**
an unqualified manager-frame policy can therefore age too slowly or too
quickly relative to input and hazard transitions. The implemented transitional
join requires two coherent safe roots with equal positive input/manager
deltas, records the affine source-epoch binding on the solution, and revokes
all work from the previous clock generation on any mismatch. This makes the
old corridor honest inside its declared ordinary unit-cadence interval; it
does not eliminate the need for a source-order transition kernel that models
freeze/dialogue transitions themselves.

An offline synthetic 4 px/H80/one-frame benchmark on the current machine took
approximately 0.34--0.52 seconds with 100--400 moving AABBs, versus 0.053
seconds with no hazards. This is compatible with a rolling background worker
and a 48+ frame lead; it is not compatible with recomputing global viability
inside every 16.67 ms action deadline.

This transitional path is **implemented but physically falsified as a
producer**. The authorized 3,600-observation Easy Stage-1 Gate 1 certified the
input/manager clock on 2,866 roots with zero cadence mismatch, yet rejected all
574 future captures. Scale remained
`root_only_source_inventory_unknown`; corridor submissions, policy queries,
and constrained actions were all zero. The run also recorded 1,205 stale
captures, 2,424 stale plans, and 4,341 native deadline misses.

The implementation explains the failed boundary. Moving the ordinary future
capture to a worker did not remove its requirement that a roughly 10 MiB
source observation and supporting reads fit inside one unchanged manager/
update-serial bracket. The Stage 1--5 scale authority still retries a complete
source inventory synchronously before the foreground action is published.
The exact exception/status subreasons were not retained, so their attribution
is **inferred from code plus aggregate physical statuses**, not an exception-
level observation. CE-0273 retains that distinction.

The runtime-owned packed observation ring is therefore no longer an optional
latency refinement for this route. It, or an equivalent immutable double-
buffered source publication, is the next producer boundary. A foreground
action transaction may read only the small published root/certificate; it may
not attempt the large inventory itself.

It is not yet a 60 Hz hard-safety implementation. The retained native
`8/12/8` synchronous foreground measured 17.72 ms mean and 32.17 ms p95 for
complete read, decode, and plan. In the non-blocking runtime, late work is
correctly discarded, so the same cost predicts frequent held frames rather
than slowed game time. The present one-frame local/global edge does not certify
repeating its action across those missed epochs. This is **observed timing plus
an inferred contract gap**, and is a promotion blocker. The route tool uses
`8/12/8` as the smallest measured foreground, while deeper precision stays in
the H80/4px background tier; the shared flat immediate kernel is the required
remedy rather than widening the Python beam.

## Decisive Experiments

### Gate 1: delivery, without policy tuning

On an explicitly authorized short Easy workload, require nonzero counts for
complete future captures, corridor submissions, on-time publications,
queryable one-frame policies, and issued globally constrained actions. Retain
deadline misses, exact sampled-mask echoes, certified clock generations, and
every cadence/gate revocation. A zero authority count or any constraint outside
the certified clock interval is an integration failure, not a local fallback
success.

**Observed result, 2026-08-27:** Gate 1 failed with 0/574 complete future
captures and zero corridor/query/constraint counts. Do not repeat it after
interval or lead tuning. Repeat only after the immutable runtime publication
and missing failure/resource/consecutive-hold telemetry are installed.

### Gate 2: source dependency factorization

For a retained Easy source root, branch all 17 first actions for H32 and
record the first divergence class: player-only, aimed birth, damage/phase,
RNG call order, transform/lifecycle, or unsupported. Measure shared versus
branched bytes and transitions. This falsifies the assumption that the exact
branch graph is tractable before a large rewrite.

### Gate 3: policy usefulness

At a same-root Easy pre-hit/exhaustion window, compare:

- current local-only result;
- the transitional exogenous corridor; and
- source-conditioned rolling viability.

Require zero false-safe first actions against an independent native/source
rollout, a concrete losing-to-viable or earlier-safe-action change, and
bounded publication latency. If exact future state changes no action, the
next target is search horizon/value rather than more producer work.

### Gate 4: physical and replay proof

Only after Gates 1--3, run a rotated Easy workload and then a full Easy route.
A candidate NMNB replay must complete with zero native hit edges and zero Bomb
input in the original Japanese v1.00d executable under Wine. Linux deadline
evidence and Wine replay evidence are separate mandatory axes.

## Lunatic Migration

Lunatic must not trigger a full global solve at every frame. It uses the same
rolling graph, static event tape, branch sharing, spatial indexing, and
incremental rebase. Greater bullet density mainly expands batched geometry;
it should not multiply ECL interpretation or copy whole world states per
action.

If H32 exact branching grows beyond the background budget, the fallback is a
sound hybrid: exact branch-aware near field plus conservative symbolic
far-field sets and an overlapping terminal viability slab. The fallback is
not stopped time, arbitrary frame skipping, or an action-independent player-
aim guess presented as exact.
