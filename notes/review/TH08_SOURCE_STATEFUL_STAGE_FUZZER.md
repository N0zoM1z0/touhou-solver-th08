# TH08 Source-Stateful Complete-Stage Fuzzer

Last updated: 2026-08-25.

## Status

The first source-closed offline laboratory is implemented on branch
`codex/th08-lunatic-source-audit`. Its purpose is to drive the real local
solver through long causal histories, not to manufacture isolated snapshots.
The stage program, gameplay RNG root, producer schedules, phase clears,
callback events, transforms, lasers, solver latency assumptions, and result
are serializable and replayable.

The recovered source repository was updated with `git pull --ff-only` before
this checkpoint and was already current at commit `57ee34f`. It remains
unmodified. The independent reduced C oracle lives in this solver repository
under `native/th08_source_oracle/`, so source-to-model evidence is reviewable
and versioned with the Python implementation.

This checkpoint is a strong test generator for a source-supported semantic
subset. It is not yet an arbitrary TH08 ECL interpreter and is not claimed to
reproduce a shipped spell from its stage file.

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

Every capsule uses schema `th08-source-stateful-stage-v1`, records source
authority commit `57ee34f`, and carries a canonical SHA-256 digest. Generator
implementation changes cannot alter an already serialized replay.

## Modeled Source Contract

The runtime currently closes the following source-derived behavior:

- one shared 16-bit TH08 gameplay RNG, including U16/U32/F32 conversion order;
- all direct-fire modes 0 through 8, including fan parity and player aim;
- the real 1,536-slot bullet pool and 256-slot laser pool;
- allocation before random-mode parameter sampling, and early loop termination
  at the first failed allocation;
- phase clears, moving resolved origins, periodic producer schedules, and
  source-order bullet scanning (`0`, then `1535..1`);
- callback 12 selection, phase transition, velocity replacement, and its
  non-colliding auxiliary state;
- sequential transform queues with the native wait-for-active-clear rule for
  deceleration, vector acceleration, angular velocity, stop-turn, stop-reaim,
  stop-snap, reflect-all, and reflect-sides/top handlers;
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
- ANM-dependent bullet lifecycle states 2, 3, and 4;
- callback 14 and other callbacks beyond the modeled callback-12 subset;
- derived child-pattern transform `0x1000000`, wrap transforms, and unsupported
  transform kinds;
- enemy bodies, items, shots, damage/power feedback, and global future-birth
  authority;
- Win32 x87/libm bit identity. The Linux C oracle is a source-level oracle;
  the shipped executable remains the physical numeric authority.

An offline collision is observational. The runtime does not invent a
post-hit/no-death-patch bullet transition. `normalized_hits` groups collision
frames by a configurable cooldown and is useful for deterministic comparisons
on the same capsule, but it is not the native route hit counter.

## Generated Workloads

Seed space is effectively unbounded. Each profile includes all nine fire
modes over its emitter sequence, odd/even fan counts, moving and oscillating
origins, tagged callback transitions, transform queues, lasers, phase clears,
and pool pressure.

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

## Independent C Differential

`native/th08_source_oracle/th08_source_oracle.c` is a deliberately small,
bounded transcription of recovered source kernels. It is compiled separately
from both the Python model and the optimized planner and covers:

- RNG U16/U32/F32;
- direct-fire modes 0 through 8;
- callback 12;
- inclusive bullet/player AABB;
- the eight supported transform handlers.

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

These are source-backed semantic corrections. None is presented as a route
hit improvement until it changes a complete future projection and passes a
controlled planner/physical gate.

## Commands

Build the tracked C oracle:

```bash
PYTHONPATH=scripts .venv/bin/python scripts/build_th08_source_oracle.py
```

Run a normal complete-stage gate and retain its replay capsule:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts .venv/bin/python \
  scripts/analysis/th08_source_stage_fuzzer.py \
  --profile gate --seed 0xce0132 --count 1 \
  --planner-stride 30 --planner-horizon 12 \
  --planner-threat-horizon 16 --planner-beam-width 8 \
  --geometry-oracle-stride 60 --geometry-oracle-horizon 3 \
  --output artifacts/benchmarks/th08_source_stage_fuzzer_gate_20260825.json
```

Replay an exact stored program by extracting its `program` object to a JSON
file and passing `--replay`. Failed cases can be retained and delta-debugged
with `--counterexample-dir`, `--shrink-failures`, and `--shrink-attempts`.
The campaign has no duration-based early termination; completion is the full
program frame count.

## Next Coverage Order

The fuzzer now provides the infrastructure needed to extend semantics without
Wine. The next work should remain incremental and differential:

1. import real retained resolved producer roots and compare their prefix to
   the generated-runtime kernel;
2. add ANM-dependent lifecycle transitions with an independent oracle;
3. lower child VMs/timeline births and callback 14 into the same event stream;
4. make future births action-conditioned where player aim or damage changes
   the producer root;
5. feed only a complete, version-matched horizon into the global viability
   planner, first in offline shadow mode;
6. use focused Practice and Wine only after a same-capsule global-policy
   differential changes a losing predecessor into a certified viable one.

This keeps the core general. Per-stage/spell compiled programs and caches are
appropriate once their source dependencies are reached; handwritten policies
remain a last resort for a measured residual.

The importer prerequisite is now explicit. A default-off, spell-filtered
Practice observer writes canonical content-addressed coherent root capsules;
capture-only results cannot reach the planner. No legacy Stage-5 trace contains
the required root, so the first real capsule still requires one isolated
physical acquisition. Offline replay and event import begin only after its
SHA-256 and exact runtime ECL identity are retained.
