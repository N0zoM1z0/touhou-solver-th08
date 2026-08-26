# Linux Lockstep Search with Original-Replay Authority

Date: 2026-08-26

Status: **bridge, local sensing, and route bootstrap implemented; replay differential pending**

This note records a deliberate change in viewpoint. The Linux reconstruction
is not merely a cheaper replacement for Wine process sensing. It can become a
solver-controlled transition runtime: pause at the original input-sampling
boundary, compute for as long as necessary, advance exactly one original game
update, and save an ordinary TH08 replay. The shipped Japanese v1.00d Windows
executable remains the final authority by replaying that candidate.

The central separation is:

- **search clock:** arbitrary real CPU time used by the solver;
- **game clock:** the ordered logical update/input epochs of TH08;
- **render clock:** platform presentation and FPS bookkeeping.

Only the search clock may expand. A slow planner must not cause the game to
advance extra updates, skip updates, sample a different input, perturb its
held-input state machine, or record artificial slowdown. This turns latency
from an unmodeled control delay into computation between two game transitions.

## Completion authority

Evidence is promoted in three explicit levels:

1. **Linux candidate:** the native runtime completes Easy Route 2 Final-B
   NMNB with no Bomb input while recording a replay. This proves only behavior
   in that build.
2. **Cross-runtime differential:** the candidate replay is accepted by both
   runtimes, and their semantic state fingerprints agree at every checked
   logical input epoch. This is a determinism gate, not yet the final result.
3. **Original completion:** the unmodified original Japanese v1.00d executable
   under isolated Wine plays the Linux-generated replay through the complete
   route with zero native hit edges and zero Bomb input. Only this level closes
   the Easy NMNB target.

A Linux-only clear, a replay that the original rejects, or a replay whose two
runtimes diverge before completion does not count.

## Source-backed feasibility

The separately cloned runtime is pinned initially at source revision
`4cffb2afa8d4a62083a5afc4a1968f51e96ac2cf`. Its modern Linux target compiles
the shared production gameplay sources, including `BulletManager.cpp`,
`EnemyManagerUpdate.cpp`, `EnemyTimeline.cpp`, the ECL units, `Player.cpp`,
`GameManager.cpp`, and `ReplayManager.cpp`. Linux-specific SDL/OpenGL behavior
lives under `src/modern/linux/`.

The Linux linker script also places target-owned globals at the original
addresses. Examples include `g_EnemyManager=0x00577f20`,
`g_BulletManager=0x00f54e90`, `g_GameManager=0x0160f508`,
`g_Rng=0x0164d520`, `g_CurFrameInput=0x0164d528`, and
`g_Player=0x017d5ef8`. The existing sensor can therefore be adapted to a local
process reader without translating the whole state model. Fixed placement is
an integration convenience, not proof of runtime equivalence.

The first implementation checkpoint is now concrete.  The runtime branch
`solver/linux-lockstep-replay-bridge` contains commits `8ffe729` and
`02ca583`; its current verified ELF SHA-256 is
`c773f9cc925350e2c2c3e80c0c7dd30954a2003488fce70dae19c53391ddc61d`.
The solver branch contains the protocol/process adapter at `878c3e4` and the
exact-child session owner at `eaa643a`.  These identities are out-of-band
configuration and audit evidence; protocol metadata does not substitute for
binary verification.

The source identifies a narrow generic hook:

- `Supervisor::OnUpdate`, calc priority 0, calls `Controller::GetInput` before
  later gameplay callbacks;
- recording `ReplayManager::OnUpdateHighPrio`, priority 17, copies that input
  into the replay stream;
- on Linux, the keyboard `GetDeviceState` implementation delegates to
  `FillKeyboard` in `src/modern/linux/linux_compat.cpp`.

An opt-in Linux-backend bridge at this boundary can therefore provide ordinary
keyboard state without editing stage logic, spell logic, the player update, or
the replay recorder. `CHAIN_CALLBACK_RESULT_RESTART_FROM_FIRST_JOB` may cause
another genuine input-sampling pass inside one outer render call; the bridge
must treat every such call as its own ordered epoch rather than deduplicating
by render count or `enemy_manager_frame`.

## Logical-time invariants

The bridge must preserve all of the following:

1. One solver action is consumed by exactly one successful
   `Controller::GetInput` sample. Repeated samples are never silently merged.
2. `g_LastFrameInput`, `g_CurFrameInput`, `g_GuiMessageInputCurrent`, and the
   held-key repeat counters remain owned by the original shared code.
3. The bridge supplies DirectInput key bytes only. It does not write player
   coordinates, RNG state, manager timers, bullets, enemies, or replay data.
4. Bomb bit `0x02` is rejected at both protocol and key-mapping boundaries.
5. Pausing for search excludes the pause interval from the Linux virtual QPC
   and millisecond clocks seen by the game. Otherwise a correct logical step
   would still poison FPS samples, replay slowdown metadata, play time, and
   render scheduling.
6. Outside explicit bridge mode, Linux timing and input behavior are unchanged.
7. No headless/render skipping or faster-than-real stepping is promoted until
   the basic paused lockstep passes the replay differential.

The first implementation should therefore compensate only bridge wait time.
After releasing an action, the normal render loop still admits the next update
at its original 60 Hz cadence. A later fast mode may use an explicit virtual
clock, but only if it produces the identical ordered state fingerprints.

## Minimal bridge protocol

The runtime change is solver-only, Linux-only, and opt-in through an explicit
Unix-domain socket path. Normal interactive execution does not open a socket.
The game is the server and the solver is the client.

Protocol version 1 sends one fixed 32-byte little-endian request containing:

- protocol magic, version, and record size;
- a monotonically increasing 64-bit input-epoch number;
- current and previous logical input masks;
- the current 16-bit gameplay RNG seed;
- a replay-target-stamped flag; and
- cumulative milliseconds excluded from the game-visible clock.

The solver verifies the exact executable separately, reads full state through
the local process-memory adapter, computes, then returns one fixed 24-byte
record containing the exact epoch and one complete logical input mask. Both
ends reject a stale/non-contiguous epoch, unknown flags or input bits,
diagonal contradictions, and Bomb. There is deliberately no response-duration
timeout: solver search time may be arbitrarily long. EOF, protocol mismatch,
or peer death permanently changes the runtime bridge to neutral input rather
than falling back to SDL or holding the last direction.

The socket is synchronization, not the bulk state ABI. Keeping bulk sensing in
the solver repo lets existing decoded models and new semantic fingerprints
share one implementation while the runtime patch remains small and generic.

## Replay compatibility boundary

The shared replay recorder writes logical input and periodic synchronization
bytes, but `ReplayManager::AddedCallback` also copies
`g_Supervisor.exeSize` and `exeChecksum` into the replay. The Linux build's
`Supervisor::CheckVersion` intentionally bypasses retail executable identity;
the original does not. The authoritative v1.00d identity is:

- executable size: `840704` bytes;
- executable checksum: `2724749753`;
- SHA-256: `330fbdbf58a710829d65277b4f312cfbb38d5448b3df523e79350b879213d924`.

Bridge mode must explicitly stamp the canonical size/checksum before replay
recording or apply an audited replay post-process that recomputes all replay
integrity fields. This stamp means only “candidate intended for this target”;
it must never be reported as evidence that the Linux ELF is the retail binary.

## Determinism gate

Before solver-generated play receives authority:

1. Run one retained Windows-origin replay on Linux and the original executable
   with identical data/configuration.
2. At every logical input epoch, construct a semantic fingerprint rather than
   hashing raw structs, pointers, padding, renderer state, or allocator state.
3. Compare stage/phase clocks, input masks, RNG seed and generation count,
   player state and position, lives/Bombs/Power, and canonical slot-ordered
   active bullet, laser, enemy, and relevant ECL state.
4. Stop at the first difference and retain the preceding equal state, first
   unequal state, field-level delta, source revision, executable identity, and
   replay hash.
5. After Linux can record, replay a Linux-generated nontrivial candidate on a
   fresh Linux process and then on the original. The reverse-direction test is
   mandatory because accepting a Windows replay on Linux is not sufficient.

The most likely numerical risk is modern compiler/runtime behavior. The Linux
build uses GCC rather than VC7, and `TH08_MODERN_PORT` currently implements
some original x87 `fsincos` paths as separate `cosf`/`sinf` calls. Platform
timing, event, audio, and rendering paths also differ. These are hypotheses to
test at the earliest divergent epoch, not reasons to assume failure or success.

Numerical comparison has two deliberately different contracts. Discrete
semantics must remain exact: input masks, RNG seed and call count, ECL program
counter, pool occupancy and lifecycle, callback/transform selection,
collision/culling decisions, hit edges, and replay synchronization may not be
accepted under a tolerance. Continuous coordinates, velocities, and angles
may initially use a recorded absolute/ULP envelope to localize expected x87
versus modern-runtime drift. That envelope is diagnostic only and must be
derived from the operation chain and elapsed horizon; a global epsilon may not
hide a threshold crossing or the first discrete divergence. The eventual
compatibility target is therefore not necessarily byte-identical float state,
but an identical ordered discrete trajectory with bounded, measured
continuous error through the replay horizon.

The first live synchronization probe passes below this stronger gate.  On the
verified ELF, three consecutive requests were epochs 1, 2, and 3.  At each
blocked callback, request current/previous input and RNG seed exactly equalled
independent reads of the fixed-address globals, and the replay target flag was
set.  The first cold Xvfb callback took roughly 41 seconds to reach, but its
reported solver pause was only 1 ms; warm startup reached the three-epoch
probe in roughly 12 seconds.  This is observed socket/memory coherence, not a
gameplay, replay, numerical-equivalence, or NMNB result.

The next live probe now crosses the title-to-game transition.  Source-derived
cursor feedback selected Start, Easy, and Sakuya/Remilia with explicit
press/release edges; two independent launches completed gameplay loading at
epochs 140 and 138 and observed difficulty 0, shot type 2, and Stage-1 route
index 0.  This also found that `TitleScreen::DeletedCallback` leaves
`g_TitleScreen` dangling, so the release/handoff epoch no longer dereferences
that global.  The result establishes deterministic menu and lifecycle
integration, not replay or numerical authority.

## Relationship to the offline fuzzer

The source-stateful stage fuzzer remains the high-volume adversarial laboratory
for planner invariants, pool saturation, transition composition, and C-oracle
differentials. The Linux runtime adds a second lane: a complete shared-engine
transition oracle with real ECL/assets/replay behavior and exact input ordering.
Neither replaces original replay validation. A discrepancy among fuzzer,
Linux runtime, and original replay is a localization tool, not a vote.

## Ordered implementation

1. **Done:** verify the i386 fixed layout and add a read-only local-process
   adapter.
2. **Done:** add the opt-in backend socket, hard no-Bomb mapper, contiguous
   epoch checks, solver-wait clock compensation, and replay target stamp.
3. **Done for the title boundary:** verify exact-child ownership and match
   three live request witnesses against fixed-address input/RNG state.
4. **Done for route selection:** drive the source-observed Start, Easy, and
   Sakuya/Remilia menus and wait for completed Stage-1 gameplay loading.
5. **Next:** drive a short gameplay input sequence, save an ordinary replay,
   and build the semantic fingerprint at each epoch.
6. Differential a retained Windows-origin replay in both runtimes, then a
   Linux-generated replay in fresh Linux and original-Wine processes.
7. Only after that gate, connect the generic local planner epoch driver and
   solve Easy practice roots followed by the full Easy route.
8. Accept success only after the original Wine runtime completes that replay
   NMNB.

This architecture is generic across stages and spells. Specific policies may
still be investigated later, but no stage/spell branch belongs in the bridge,
clock, replay, or state-fingerprint layers.
