# Linux Online Immutable Root v1

Last updated: 2026-08-27.

Status: **implemented and deterministically verified; physical 60 Hz capacity
not yet observed**.

## Decision

The online route now uses a runtime-owned, leased, immutable packed
post-update root. It does not stop the game, wait for the solver, or subtract
solver time from any clock. The prior large live `/proc/<pid>/mem` transaction
is retired from route action authority.

The two scheduling tiers remain:

1. the immediate shield decodes active packed records directly and races the
   exact next input epoch;
2. runtime ECL identity, initial scale-source binding, future-source closure,
   and corridor work run in background workers over that same immutable root
   generation.

This checkpoint deliberately does not change lead, grid, beam, horizon, or
objective parameters.

## Physical contract

- Objective: Easy Sakuya/Remilia Route-2 Final-B NMNB, then Lunatic Route-2.
- Hard constraints: continuous original cadence, hard no-Bomb, no stale
  action, no stopped or compensated time, and survival before objectives.
- Observation: one complete runtime publication with generation, source input
  epoch, manager frame, update serial, exact fixed/dynamic ranges, and typed
  active records.
- Action: one complete no-Bomb mask for `source_input_epoch + 1`. Selecting the
  held complete mask is no-write.
- Transition and horizon: immediate action authority remains one physical
  frame; background policy time remains manager-frame based only inside the
  existing dual-clock certificate.
- Uncertainty: a missing/corrupt/dropped root, stale context/clock generation,
  unsupported source, or timeout withholds the corresponding authority.
- Resources: Power, lives, and Bomb count are observed in the immutable root;
  they are not allowed to relax survival. Bomb output remains forbidden.
- Deadline: the next native input sample. Every packing, process-copy, decode,
  and planning cost remains ordinary wall time.
- Fallback: a miss repeats a complete mask only under a finite, exact-root
  runtime lease whose context still matches. Otherwise it selects neutral
  Shot+Focus and remains unresolved. The current route publishes no lease:
  local two-frame clearance alone does not prove that the repeated action is
  a predecessor of the second global viability layer.
- Falsifier: game-thread wait, clock subtraction, slot overwrite while leased,
  a mismatched certificate, any later live-state read entering immediate or
  background model authority, wrong-epoch action, or Bomb.

## Runtime publication

Protocol v4 publishes a 104-byte `T8RQ` record. Two 32 MiB runtime-owned slots
carry `T8SN` v1 roots. A root has an 80-byte header, bounded range directory,
and copied bytes. It binds:

- `generation` and source input epoch;
- manager frame and FRScreen update serial;
- total size, range count, complete flag, and typed record counts;
- exact player/global/resource/spell/timeline/ECL/SHT ranges;
- active bullet, laser, enemy, and item records at their original addresses;
- active auxiliary ECL contexts and exact indexed-enemy fields needed even
  when a registry points at an inactive slot.

The runtime packs at the authored post-update seam on the game thread. It
never waits for a free slot. If both slots are leased or the bounded builder
cannot complete, it increments `dropped_snapshots` and still publishes the
input deadline notification without snapshot authority.

The solver copies one leased slot through one logical process-memory read,
validates the request/header generation, epoch, size, entry count, bounds,
types, counts, completion flag, and reserved fields, then queues an exact
`T8RL(generation, slot)` release. The action packet is sent before release
traffic. A slot is never overwritten until that exact lease is released or
the client disconnects.

This is a version/bounds certificate, not a cryptographic authenticity claim.
The lease supplies immutability while the copy is in progress; the solver's
local `bytes` owns the root afterward.

## Consumer boundary

The immediate decoder enumerates typed active records directly. It does not
zero, copy, or scan the 1,536-bullet, 256-laser, 2,096-item, or 480-enemy full
slabs. Original slot numbers are preserved through compact bullet, laser,
item, and enemy decoders.

The legacy future-source implementation still requests contiguous slabs. Its
reader synthesizes those slabs locally from the immutable packed bytes with
zero-filled inactive slots. This compatibility cost is confined to the
background worker and cannot observe a later native epoch. It is retained to
connect action authority first; replacing that background representation is a
later performance change, not part of this checkpoint.

Runtime ECL hashing and the first complete scale-source inventory are also
background tasks. Workers capture their binding/context at submission; stale
completion is rejected. A stale scale worker resets the exact authority object
it owned, so work from an old stage/spell cannot mutate a new context.

## Evidence and confidence

**Observed:** physical Gate 1 on the preceding protocol completed 3,600 Easy
observations with zero Bomb, but 574/574 future captures failed and global
publication/query/constraint counts were zero. It recorded 1,205 stale
captures, 2,424 stale plans, and 4,341 deadline misses. CE-0273 retains that
evidence.

**Observed:** authored source checkpoint `a548b9d` builds as i386 with SHA-256
`f10a0222cd000ac50f933ec8e2ebcf7ff97431aaa094faebc003aa21c2eb43ee`;
the fixed-layout verifier and target-independent CI pass. Complete solver
discovery passes 1,698 tests with five conditional skips. Focused tests cover
bounded parsing, immutable-copy ownership, sparse compatibility
reconstruction, compact active decoding, action-before-release ordering, no
foreground full-pool read, and background identity/scale/future use of the
submitted root reader.

**Observed:** the Linux route now fails closed unless the native hazard and
beam-reducer kernels are loadable. A no-item structure-of-arrays expansion
removes per-draft Python objects while preserving the existing 8/12/8 action,
reducer, and objective contracts. Across deterministic same-root synthetic
roots, actions and hard labels matched the legacy path; at 800 bullets p95
planning fell from 17.545 to 10.362 ms, and at 1,536 from 23.101 to 14.979 ms.
An 8 MiB `/proc/self/mem` copy benchmark fell from 3.943 to 2.360 ms p95 after
returning the owned immutable `pread` bytes directly. These numbers exclude
runtime packing and are not physical-route evidence.

**Inferred:** because packing runs on the same game thread immediately after
the complete calc chain, and leased bytes are not overwritten, every accepted
range belongs to one post-update root without an unchanged-frame read bracket.
This inference depends on the authored publication seam and lease lifecycle,
not on manager-frame quiescence.

**Hypothesized:** active packing plus one compact copy and direct active decode
will materially reduce stale captures and permit future/global completion at
continuous 60 Hz. No gameplay was run for this checkpoint, so 60 Hz capacity,
hit reduction, NMNB, and Wine replay equivalence remain unobserved.

## Rejected alternatives

- stopping or pausing the game for solve/capture;
- subtracting solver time from QPC, `timeGetTime`, or replay time;
- retaining the large unchanged-frame live `/proc` bracket;
- publishing an overwrite-on-next-frame buffer without a lease;
- copying the whole address space or treating a Linux ELF as original-v1.00d
  identity.

## Next evidence gate

First measure packed size, active counts, runtime pack/copy/decode/decision
latency, slot drops, exact future failure reasons, and consecutive neutral
fallbacks without changing planner parameters. Before route leases may be
enabled, the repeated action must also pass a same-version second-layer global
predecessor query; a local collision witness is insufficient. A later
explicitly authorized physical run must
show nonzero future completion, corridor publication, policy query, and
constrained issued action before this producer is called physically connected.
Original-Wine `.rpy` playback remains the final equivalence gate.
