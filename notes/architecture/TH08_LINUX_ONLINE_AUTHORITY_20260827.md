# Native-Linux Online Solver Authority

## Status

This is the active Linux execution contract. The former input-callback wait
and virtual-clock compensation are forbidden for route solving. Lockstep may
be used only by an explicitly bounded semantic differential test and cannot
produce route-search or performance authority.

Physical Gate 1 on 2026-08-27 validated the non-blocking wire and cadence gate
but falsified the protocol-v2 `/proc` future/source producer: 574/574 future
submissions failed and no corridor, query, or constrained action existed.
CE-0273 remains the physical authority. Protocol v4 now implements the packed
immutable runtime publication below. It is build/test observed and has not yet
received a physical delivery or 60 Hz performance claim.

## Physical objective and hard constraints

- Sakuya/Remilia Easy Route-2 Final-B NMNB, followed by Lunatic Route-2.
- Original logical input cadence; the game thread never waits for the solver.
- Hard no-Bomb at every publication and native sample.
- Survival is hard. Objectives rank only actions inside the certified viable
  set.
- A Linux replay is a candidate trajectory. The original Japanese v1.00d
  executable under Wine remains the cross-runtime playback authority.

## Epoch and observation contract

The runtime owns a contiguous `input_epoch` incremented for every
`Controller::GetInput` sample. It is not `enemy_manager_frame`; the manager
clock may freeze while held input still moves the player.

After a completed logical update, the runtime scans native active flags and
packs the exact state needed by current and future consumers into a free
runtime-owned slot. The protocol publication binds slot, generation, source
epoch, packed size, and range count. The solver performs one logical `/proc`
copy while the slot is leased, validates the inner certificate, queues an
exact release, and never reads native gameplay state for model authority from
that publication again. A policy may use only that immutable root and older
retained artifacts.

The immediate tier enumerates packed active bullet/laser/item/enemy records
directly and preserves original slot indices. Runtime ECL identity, first
scale-source binding, and future/global work receive the same root reader in
background workers. The historical future decoder may synthesize complete
zero-filled inactive slabs locally, but no such full-pool reconstruction or
large live scan remains in the foreground action path. Small live bootstrap,
result-screen, and final input-epoch deadline reads are lifecycle/delivery
checks, not model roots. See `TH08_LINUX_IMMUTABLE_ROOT_20260827.md`.

### Dual-clock admission decision

`enemy_manager_frame` remains the authored ECL/hazard coordinate, but it is
not allowed to stand in for the physical input clock by default. The online
action join now requires a fail-closed unit-cadence certificate:

1. the coherent root carries its exact source `input_epoch`, dialogue state,
   scripted-update-freeze byte, player phase/Bomb state, and GameManager
   flags;
2. two safe roots in the same stage/spell context must establish
   `delta(input_epoch) == delta(enemy_manager_frame) > 0`;
3. the resulting affine offset binds each corridor `source_frame` to a
   separate `source_input_epoch`;
4. every pending activation and active query rechecks that binding; and
5. a context change, unequal delta, dialogue, scripted freeze, manager
   skip-update flag, uncontrollable player phase, Bomb state, or unknown gate
   revokes the policy and every asynchronous result from its clock generation.

This is **implemented and test-observed**. The authored source separately
shows why the gate is necessary: `EnemyManager::OnUpdate` can return on the
GameManager bit-10 skip flag before incrementing its manager timer, while the
ECL scripted-freeze byte suppresses enemy timers and bullet motion even though
the manager callback can still reach its timer increment. Those are opposite
clock failures, so neither counter can silently substitute for the other.

The complete future-source interpreter fails closed on reached unsupported
immediate callbacks; callback index 26, which writes the scripted-freeze byte,
is not among its modeled callback indices. This prevents a complete projection
from knowingly crossing that callback. It does not yet prove every impending
dialogue/scene clock transition. One action at the transition into a newly
observed freeze is therefore still a promotion boundary for the shared exact
transition kernel, not something the cadence certificate hides.

## Action and deadline contract

Inside the solver, an action record is a complete no-Bomb mask tagged with:

- source snapshot epoch;
- exact target input epoch;
- content/model/policy version;
- publication timestamp and expiry;
- authority source and fallback provenance.

Protocol v4 sends source epoch, target epoch, the complete mask, and an
optional exact-generation finite continuation lease back to the
game. Content/model/policy versions are checked before that send and retained
in solver telemetry; the runtime enforces epoch and mask validity but does not
independently decode those solver versions. A separate `T8RL` record releases
only the exact `(slot, generation)` lease. The client sends the action packet
before release traffic.

At an input sample the runtime performs one non-blocking mailbox lookup. An
exact-target valid action is sampled. On a miss it repeats the complete mask
only while a finite source-generation lease and runtime context still match;
otherwise it uses neutral Shot+Focus. Late or skipped-epoch actions are
discarded permanently; there is no delayed pending command. Disconnect,
invalid-packet, and bridge-failure handling are also neutral and never emit Bomb.

The runtime fallback mechanism is bounded, but the live route publishes no
lease yet. Its local two-frame clearance witness does not prove that repeating
the action remains in the second global viability layer. Present misses are
neutral and unresolved; a miss-bearing trace is delivery telemetry rather than
hard-safety promotion.

## Planner authority

The foreground layer attempts every observed target epoch and certifies its
immediate/short-horizon signed clearance under the declared observation age
and one-frame action contract. Future-source projection incrementally
publishes time-indexed hazard coverage. The global layer publishes a viability
policy far enough ahead that its solve completes before the first queryable
layer. Once a future policy is
pending, the producer preserves that earliest source epoch and submits no
replacement until it activates; otherwise fast rolling solves can postpone
authority indefinitely.

Hard online viability has exactly one physical frame per control layer. The
generic recurrence holds the selected action for its complete layer; an
eight-frame layer is therefore a macro-action and cannot constrain only one
frame while allowing an unrelated choice on the next. Longer layers may
remain soft far-horizon guidance but have no hard online action authority.

The action transaction may consume global authority only when root/content,
future projection, geometry, policy, epoch interval, and action-conditioned
state all match. Manager-frame policy time must additionally carry the exact
input-epoch binding and current unit-cadence generation above. It intersects
the global winning action set with the fresh local safe set. A missing or stale
global result cannot widen local safety and cannot be reported as a global
decision. The physical integration gate requires nonzero complete future joins,
fresh global queries, globally constrained issued actions, and nonzero
clock-certified observations in an online trace. The protocol-v2 trace produced
2,866 certified roots but zero joins/queries/constraints, so this planner
authority remains code-only and failed physical admission. Protocol v4 closes
the known immutable-observation wiring defect in code; it does not
retroactively promote that trace.

This future/corridor composition is the connected transition baseline, not a
presumption that its world representation is optimal. Authored source shows
that aimed births and damage/phase transitions depend on the candidate player
path. The target shared-kernel architecture and its falsifiers are recorded in
`TH08_SOURCE_DRIVEN_ONLINE_SOLVER_20260827.md`.

## Timing evidence and falsifiers

Retain snapshot-publication, solver-start/end, action-publication, input-sample,
and game-frame timestamps from a monotonic clock. Report p50/p95/p99/max,
deadline misses, discarded late actions, certified/neutral fallbacks, consecutive misses,
policy age/lead, and actual sampled-mask echo.

Any of the following invalidates a route run:

- the game thread waits for solver work;
- solver time is removed from a game-visible clock;
- a stale or wrong-epoch action is sampled;
- a Bomb bit appears;
- future/global authority is claimed without complete matching coverage;
- a manager-frame policy is queried without its matching input-epoch binding;
- online cadence/deadline evidence is missing.

For policy promotion, a repeated fallback beyond its explicitly certified
horizon also invalidates the run. The current route lease horizon is zero, so
every miss remains unresolved. The first diagnostic recorded a 4,341
deadline-miss delta but omitted maximum consecutive hold, final resources, and
exact future/scale failure subreasons. Those telemetry fields are mandatory
before the next gate.

Wine replay validates the realized trajectory against the original program. It
does not prove that the Linux solver met its online deadline; both evidence
axes are required.
