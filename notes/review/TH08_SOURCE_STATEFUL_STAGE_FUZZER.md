# TH08 Source-Stateful Complete-Stage Fuzzer

Last updated: 2026-08-25.

## Status

The first source-closed offline laboratory is implemented on branch
`codex/th08-lunatic-source-audit`. Its purpose is to drive the real local
solver through long causal histories, not to manufacture isolated snapshots.
The stage program, gameplay RNG root, producer schedules, phase clears,
callback events, transforms, lasers, solver latency assumptions, and result
are serializable and replayable.

The complete-stage runtime now executes callback 14 as well as callback 12.
This closes the exact source-ordered transition that caused the physical Easy
Stage-5 hit: a tagged state-1 bullet may remain present while auxiliary state
suppresses collision, then become lethal in the callback pass before the same
frame's movement and collision test. The workload records those reactivations
explicitly instead of hiding them inside aggregate callback counts.

The recovered source repository was updated with `git pull --ff-only` before
this checkpoint and was already current at commit `57ee34f`. It remains
unmodified. The independent reduced C oracle lives in this solver repository
under `native/th08_source_oracle/`, so source-to-model evidence is reviewable
and versioned with the Python implementation.

This checkpoint is a strong test generator for a source-supported semantic
subset. It is not yet an arbitrary TH08 ECL interpreter and is not claimed to
reproduce a shipped spell from its stage file.

The resolved-stage policy boundary is now executable.  By default the
closed-loop campaign joins the delayed coherent current root to its complete
source-known event suffix and passes that versioned projection through every
local hazard consumer.  `--no-future-hazards` retains the historical blind path
only for controlled A/B replay.  This is authority for generated resolved IR,
not arbitrary ECL or the production Wine issue loop.  A requested future that
cannot close is recorded and makes the case fail; it is never silently treated
as empty space.

The executor/planner cadence is also part of the model.  Player, bullets, and
lasers are dequeued from one root; their relative snapshot lag is zero, while
the elapsed source-to-issue age is charged once as control delay.  Because the
executor cannot replace a command between planner ticks, the certified action
hold is at least the planner stride.  Large strides are therefore explicit
high-latency stress cases, not cheap approximations of a fast controller.

## Why The Old Stateful Fuzzer Was Insufficient

Snapshot mutation can make individually plausible bullets while violating the
history that produced them. It does not reliably preserve the shared RNG
stream, finite native pools, callback selection, queued transforms, lifecycle
timers, phase clears, or the order in which those systems interact. It
therefore misses transition bugs and can also report impossible failures.

The replacement begins at a resolved producer event and executes the retained
state forward. A generated case is a complete program rather than a bag of
frames:

```text
seeded stage grammar
  -> contiguous phases and resolved producer schedules
  -> native-order pool allocation and shared gameplay RNG
  -> callback / transform / bullet / laser lifecycle
  -> delayed sensed snapshots
  -> real Sakuya/Remilia local planner
  -> delayed hard-no-Bomb input and collision observation
```

Every capsule records source authority commit `57ee34f` and carries a
canonical SHA-256 digest. Schema v1 preserves the original resolved-descriptor
programs, v2 adds an already-resolved aim, and v3 adds the native bullet
type/lifecycle flags. Schema v4 makes every new emitter select one of the 21
real template rows and records the distinct collision and visual/culling
geometries. Readers recompute the required schema from program features, so a
v2/v3/v4 payload cannot be relabeled as v1. The tracked v1 gate remains
hash-verifiable and parseable, but is no longer source-closed because it lacks
visual culling geometry. Generator implementation changes cannot alter an
already serialized replay.

## Modeled Source Contract

The runtime currently closes the following source-derived behavior:

- one shared 16-bit TH08 gameplay RNG, including U16/U32/F32 conversion order;
- all direct-fire modes 0 through 8, including fan parity and player aim;
- the real 1,536-slot bullet pool and 256-slot laser pool;
- all 21 source/asset template collision and visual-culling geometries;
- allocation before random-mode parameter sampling, and early loop termination
  at the first failed allocation;
- phase clears, moving resolved origins, periodic producer schedules, and
  source-order bullet scanning (`0`, then `1535..1`);
- the type-indexed state-2/3/4 spawn lifecycle for all 21 initialized native
  bullet templates, including native flag priority, divided pre-activation
  motion, nonlethal gating, and same-update state-1 activation;
- the same lifecycle inside the real local hazard projector. Live pool
  decoding recovers type from the already-captured normal ANM `scriptIndex`;
  the 21 source rows are one-to-one, so this adds no sensing call;
- callback 12 and callback 14 selection, shared phase/auxiliary transition,
  velocity replacement/restoration, and collision gating. Events are applied
  in their source order before bullet movement; callback-14 suppressed-to-
  lethal transitions and same-frame collisions are retained separately;
- sequential transform queues with the native wait-for-active-clear rule for
  deceleration, vector acceleration, angular velocity, stop-turn, stop-reaim,
  stop-snap, reflect-all, and reflect-sides/top handlers;
- exact export of each generated bullet's 18-record program, queue cursor,
  active handler timers/parameters, and culling counters into the compact
  retained-current-hazard root used by offline global replay;
- unit-time-scale bullet motion, offscreen culling, and exact supported laser
  spawn/lifecycle/collision geometry;
- exact player movement ordering used by the offline closed loop;
- a delayed sensing queue, delayed issue queue, hard no-Bomb assertion, local
  planner timing, and periodic NumPy-versus-native geometry differential.

The runtime refuses a program with any `source_unknowns`. Generated origins
are explicitly **resolved descriptor schedules**. Exactness begins after an
ECL/child/timeline producer has resolved its operands; the generator does not
pretend that its schedules are reached ECL bytecode.

The following remain outside the exactness claim:

- arbitrary main/auxiliary/child ECL execution and enemy timeline births;
- general ANM VM execution, and composition of spawn lifecycle with callback
  tags or transform programs; those compositions currently fail closed;
- callbacks other than the modeled callback-12/14 subset;
- derived child-pattern transform `0x1000000`, complete-stage-runtime wrap
  composition, and unsupported transform kinds (the retained-current scalar/C
  frame now covers wrap itself);
- enemy bodies, items, shots, damage/power feedback, and global future-birth
  authority;
- Win32 x87/libm bit identity. The Linux C oracle is a source-level oracle;
  the shipped executable remains the physical numeric authority.

The generic `0x5A`--`0x5E` enemy-constructor transition is now separately
closed in Python/C, including parent guards, copied-template initialization,
synchronous-bootstrap success, and post-bootstrap linked-child writes. It is
deliberately not listed as complete-stage runtime coverage until the retained
child VM and native manager-slot schedule consume that kernel.

An offline collision is observational. The runtime does not invent a
post-hit/no-death-patch bullet transition. `normalized_hits` groups collision
frames by a configurable cooldown and is useful for deterministic comparisons
on the same capsule, but it is not the native route hit counter.

## Generated Workloads

Seed space is effectively unbounded. Each profile includes all nine fire
modes over its emitter sequence, odd/even fan counts, moving and oscillating
origins, all 21 native bullet types and all three spawn-state flag classes,
tagged callback-12/14 transition cycles, transform queues, lasers, phase
clears, and pool pressure. Lifecycle emitters are isolated from
callbacks/transforms until
their source composition order is closed; the same generated stage still
contains independent callback and transform histories.

| Profile | Frames | Phases | Intended use |
| --- | ---: | ---: | --- |
| `quick` | 480 | 4 | unit/CI replay and shrinker checks |
| `gate` | 3,600 | 12 | normal solver and geometry campaign |
| `research` | 7,200 | 18 | long transition and performance campaign |
| `extreme` | 12,000 | 24 | deliberate native-pool saturation beyond shipped Lunatic density |

The first seed-`0xce0132` extreme runtime completed all 12,000 frames in about
79 seconds. It requested 11,372,341 births, allocated 137,914, suppressed
11,234,427 because of the finite pool, reached all 1,536 bullet slots, spent
1,655 frames saturated, activated 156,186 transforms, applied 71,616 callback
changes, and spawned 336 lasers. Its final source-state digest was
`5749550513434dc311d0980e038071a66507da7d32a54ee2102fdfddddd4153e`.
This demonstrates pressure and long-state execution, not equivalence to a
specific ZUN-authored stage.

The retained acceptance campaign is
`artifacts/benchmarks/th08_source_stage_fuzzer_gate_20260825.json` (artifact
SHA-256 `17f62a08e17d207ac371a51b11187e310ad27d27411a921763359045e553a851`).
Its identity is `gate:0000000000ce0132:48cf57f51adf6519`. It completed all
3,600 frames with 50,297 allocated births, 32,301 transform activations,
35,056 callback changes, 60 laser spawns, 122 pool-saturated frames, and 120
real planner calls. Hard no-Bomb, planner exceptions, and all 180 periodic
geometry comparisons passed. Complete C lockstep retained exact RNG and
collision membership; maximum admitted source-libm position/velocity drift
was `0.0005874634 px`/`4.7683716e-7`.

The campaign recorded 134 cooldown-normalized collision events. That number
measures this deliberately hostile synthetic capsule and is not a route score
or a claim that the current local planner solves beyond-Lunatic pressure.

The v3 lifecycle gate used the same seed/profile and completed 3,600/3,600
frames. It allocated 57,871 of 190,326 requested births, reached all 1,536
slots, activated 18,665 native spawn lifecycles, executed 120 planner calls,
and compared 1,412,926 reached lifecycle states/positions with the independent
C oracle. Lifecycle state and position matched exactly; the maximum existing
non-lifecycle libm drift was `0.0005874634 px`. Hard no-Bomb and every geometry
gate passed. Planner median/p95 were 22.37/27.28 ms. Its 152 normalized
collisions are a new, deliberately changed
synthetic workload, not comparable route hits. To limit artifacts, the
103,397-byte full report was kept only in `/tmp`, recorded by SHA-256
`16176920feeee82024d81d0ee96acc99b533beaaf8119124d737ad7322c994de`,
and removed after this summary; the older compact v1 gate stays tracked as the
backward-compatibility fixture.

The callback-14 gate used seed `0x8414` and completed 3,600/3,600 frames with
the independent C source oracle enabled. It allocated 49,462 of 153,839
requested births, reached all 1,536 slots, executed 25,889 callback-12 and
28,064 callback-14 changes, and observed 5,212 auxiliary-suppressed-to-lethal
reactivations. Two reactivated bullets collided in that same source-ordered
frame, proving that the long-stage harness reaches the transition seen in the
physical Stage-5 failure. All 1,220,560 lifecycle samples matched the C oracle
exactly; callback velocity drift was at most `4.7683716e-7` and accumulated
non-lifecycle position drift was `0.0010681152 px`. The 450 planner calls,
hard no-Bomb gate, and complete differential passed. The 120,873-byte report
was retained only long enough to record SHA-256
`13e431aff2c1fc1aeda90c1c467a644fee4f7ef1e8a1530f8b50cb6e3dd85e2b`,
then removed; it is not a tracked artifact.

## Independent C Differential

`native/th08_source_oracle/th08_source_oracle.c` is a deliberately small,
bounded transcription of recovered source kernels. It is compiled separately
from both the Python model and the optimized planner and covers:

- RNG U16/U32/F32;
- direct-fire modes 0 through 8;
- all 21 type-indexed state-2/3/4 spawn lifecycles;
- all five generic enemy/linked-child constructor classes `0x5A`--`0x5E`,
  with arbitrary post-bootstrap position and flag state;
- callback 12 and callback 14, including their shared phase/auxiliary state;
- inclusive bullet/player AABB;
- the eight motion handlers; and
- a complete retained-current transform frame covering queue admission,
  immediate records, barrier/wrap, source-order handlers, movement, visual
  culling, and retirement, with template/derived births failing closed.

The build helper hashes the C source, header, and compiler flags into a stamp.
Loading the oracle rebuilds when that stamp differs, preventing a changed
source file from being tested against a stale shared object.

Complete-stage lockstep compares every spawn and callback, discrete pool and
lifecycle state, final RNG state/call count, and bounded numeric drift. The
remaining small drift is explicitly limited to Python double-libm
`sin`/`cos` versus C `sinf`/`cosf`; discrete state and RNG must be exact. The
transform differential additionally exercises randomized mutable states for
all eight handlers.

## Bugs Found By This Infrastructure

1. Callback-12 bullets with nonzero auxiliary state were projected as lethal
   even though the source collision path gates them out.
2. Future-frame callback arrays shared one mutable NumPy buffer, so a later
   callback retroactively changed earlier projected frames.
3. `Th08Rng.next_unit()` divided in Python double precision before converting
   to binary32. The source first casts the U32 numerator to float. The old
   model disagreed for 62,784 of 65,536 first-seed values.
4. Random fire modes sampled parameters before checking for a free pool slot.
   The source allocates first, so a full-pool rejected tail consumes no RNG.
5. The native test loader could silently reuse an old `.so` after C/header
   edits. Content-stamped rebuilds now close that infrastructure hole.
6. The first long-stage C differential used an empirical age tolerance that
   rejected valid accumulated binary32/libm drift. It now propagates a
   per-slot forward roundoff budget while requiring exact collision membership.
7. The older dense AABB oracle was stale after callback-aux promotion and
   encoded the old state-5-only filter. It now differentially isolates
   geometry, state-5, and callback-aux effects.
8. The standalone future lowerer knew the generic spawn lifecycle, but the
   long-stage IR/runtime rejected it, leaving an important transition family
   outside stateful stress. Schema v3 now executes it and checks every reached
   lifecycle bullet against C without conflating native state with callback-12
   phase state.
9. The real local projector still hardcoded the one observed state-2
   completion timer, advanced states 3/4 at full speed, and treated every
   preactivation state as immediately lethal. The decoder now derives template
   type from the copied normal ANM script; all 21 types and states 2/3/4 match
   C position/state/lethality from multiple preterminal roots. The long gate's
   outcome did not change, so this is not presented as a policy gain.
10. The first child-constructor draft tested suppress bit 10 on the copied
    manager template and assumed the synchronous child ECL left geometry
    unchanged. Source instead tests the parent flag, then applies link writes
    to the state returned by `RunEcl`; a failed bootstrap receives no writes.
    The standalone Python/C constructor differential now locks that ordering
    before the long-stage VM is allowed to consume it.
11. The retained live transform object was named like a complete runtime but
    contained only the stop/turn union at native `+0x1004..+0x102c` and one
    pending record. Vector, angular, reflection, barrier, wrap, and the rest of
    the 18-record program were lost across serialization. The diagnostic and
    long-stage roots now retain the exact program plus only active, meaningful
    handler blocks; the fast packed decision decoder remains unchanged.
12. Reflection and offscreen culling reused the lethal collision half-extents.
    Source instead tests the current ANM sprite width/height. The shipped
    asset proves the fields can differ substantially (type 10 is 12 px for
    collision versus 32 px for culling), so the stage runtime and independent
    C oracle now carry the two geometries separately.
13. The Python timer reference compared native `float32(0.99)` with a Python
    binary64 literal. At that exact threshold it could take a different
    full-rate/fractional branch than `Supervisor::TickTimer`/`Decrement`.
    Frame operands and source thresholds are now canonical binary32 values.
14. A batched C call stops at its first unsupported transition, after earlier
    entries may already have advanced. The Python owner now poisons that batch
    and refuses decode/reuse; fade entries are stable nonlethal terminals for
    the covered prefix instead of invalidating all later entries.
15. Closed-loop sensing delayed bullets and lasers but paired them with the
    current player position, then charged `snapshot_lag` again.  The queue now
    stores the complete player/hazard root and derives one elapsed control
    delay from its source frame.
16. The beam assumed it could change direction after two frames even when the
    campaign invoked it only every eight frames.  The effective action hold is
    now `max(action_hold_frames, planner_stride)`, so low-cadence laser traps
    cannot be hidden by fictitious intermediate commands.
17. Future-join failure was diagnostic only and could leave the case marked
    passing after current-only fallback.  Enabled future coverage is now a
    hard campaign/fuzzer pass condition, with incomplete reasons retained.
18. The first transform-1 future envelope used descriptor speed, but source
    writes magnitude 5 at timer zero and then subtracts `timer*5/16`.  The
    future-birth and current-pool fallback bounds now include the fixed 5 px
    maximum and retain the current root AABB at projection frame zero.

These are source-backed semantic corrections. None is presented as a route
hit improvement until it changes a complete future projection and passes a
controlled planner/physical gate.

## Commands

Build the tracked C oracle:

```bash
PYTHONPATH=scripts .venv/bin/python scripts/build_th08_source_oracle.py
```

Run a normal complete-stage gate. Write routine successes to temporary storage;
retain only compact summaries or minimized counterexamples in the repository:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts .venv/bin/python \
  scripts/analysis/th08_source_stage_fuzzer.py \
  --profile gate --seed 0xce0132 --count 1 \
  --planner-stride 2 --planner-horizon 12 \
  --planner-threat-horizon 16 --planner-beam-width 8 \
  --geometry-oracle-stride 60 --geometry-oracle-horizon 3 \
  --output /tmp/th08_source_stage_fuzzer_gate.json
```

Replay an exact stored program by extracting its `program` object to a JSON
file and passing `--replay`. Failed cases can be retained and delta-debugged
with `--counterexample-dir`, `--shrink-failures`, and `--shrink-attempts`.
The campaign has no duration-based early termination; completion is the full
program frame count.

Future hazards are enabled by default.  Add `--no-future-hazards` only to form
a matched historical A/B control.  At commit time the fixed quick corpus
`0x841400..0x841407` completed with zero hits/collision frames in both modes;
the authoritative mode closed 1,920/1,920 joins.  Routine full reports remain
in `/tmp`; the semantic record is kept in AUD-086 and the research log.

## Next Coverage Order

The fuzzer now provides the infrastructure needed to extend semantics without
Wine. The next work should remain incremental and differential:

1. preserve the completed retained-root importer, child/timeline scheduler,
   callback-12/14 stream, 21-type lifecycle, and source/C differentials;
2. preserve the completed scalar/C execution of the retained 18-record
   current-bullet program: source-order motion, barrier/wrap/immediates,
   movement, culling, typed unsupported births, and long differential corpus;
3. retain the measured persistent native batch boundary. Its 1,536-state
   kernel is 0.02446 ms median, while Python encode/decode makes the wrapper
   22.233 ms; do not put the object wrapper in the 16 ms local issue loop;
4. preserve the completed exact-clock local join for resolved births,
   callback 12/14, lasers, current bullets, action-conditioned aim bounds, and
   fail-closed request coverage; use the fixed quick corpus as its smoke gate;
5. replace the callback/active-transform AABB object fallback with a packed,
   persistent batch and exercise a denser gate at the real two-frame cadence;
6. add template replacement and derived finite-pool child births, then feed
   only a complete, version-matched current-plus-future horizon into the
   global viability planner in offline shadow mode, with player-relative
   re-aim explicitly action-conditioned or conservatively set-valued;
7. use focused Practice and Wine only after a same-capsule global-policy
   differential changes a losing predecessor into a certified viable one and
   the submission/publication latency is bounded. In parallel, use a full
   Easy Route-2 NMNB attempt as an infrastructure falsifier: any Easy hit is
   investigated as a sensing/model/issue failure, not excused as search cost.

This keeps the core general. Per-stage/spell compiled programs and caches are
appropriate once their source dependencies are reached; handwritten policies
remain a last resort for a measured residual.

The importer prerequisite is now explicit. A default-off, spell-filtered
Practice observer wrote canonical content-addressed coherent Stage-5 root
capsules; capture-only results cannot reach the planner. Offline replay checks
each capsule's SHA-256 and exact runtime ECL identity. The retained roots still
reach child/callback boundaries before a complete hostile-birth horizon, so
they remain shadow evidence rather than action authority.
