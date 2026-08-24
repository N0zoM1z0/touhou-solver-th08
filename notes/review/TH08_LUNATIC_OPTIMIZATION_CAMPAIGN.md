# TH08 Lunatic Optimization Campaign

Last updated: 2026-08-24.

This ledger tracks the active sequence of general solver optimizations after
the source/runtime audit.  The semantic reference at `../th08` is used to
simplify and check the model; the shipped Japanese TH08 1.00d executable and
retained physical traces remain the authority.  Source/runtime discrepancies
continue to live in `TH08_SOURCE_AND_RUNTIME_AUDIT.md`.

## Objective And Reference

- Physical target: Sakuya/Remilia, Lunatic, Route 2, Final-B, hard no-Bomb.
- Current integrated reference:
  `lunatic_route2_fullrun_unattended_20260823_183138`, 58 native hit edges,
  stage counts `4/6/5/13/9/21`, zero Bomb input, route complete.
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
| OPT-001 | sensing latency | Reuse one fixed 64-slot enemy-prefix RPM destination for planning and fresh issue recertification | low | FIXED-OFFLINE | pending |
| OPT-002 | sensing latency | Replace repeated scalar player/control reads with one explicitly bracketed compact root capture, preserving duplicate before/after observations | medium | QUEUED | pending |
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

Status: **FIXED-OFFLINE**

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
The implementation awaits its full-route physical timing gate.

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
