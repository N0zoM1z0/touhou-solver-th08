# Touhou Solver Current Handoff

Last updated: 2026-08-25.

This is the only volatile entrypoint. Read `AGENTS.md`, `GOAL.MD`, then this
file, `STRATEGY.md`, and the focused task card in
`notes/review/TH08_LUNATIC_NMNB_RESEARCH_TASKBOOK.md`.

Historical material removed from the active tree is recoverable through
`ARCHIVE_INDEX.md` and tag `pre-workspace-prune-20260731`. It has no current
authority.

## Active Scope Override

The active completion target is a fresh full-game Sakuya/Remilia **Lunatic
Route-2 Final-B NMNB**. The user explicitly restored this scope on 2026-08-23
and authorized isolated Wine gameplay on the current VPS. Extra remains
deferred. Fixed-root wind tunnels remain diagnostic; original-engine Lunatic
evidence leads iteration.

The 2026-08-01 Hard/pause state is historical. Preserve its useful physical
and authority evidence, but do not let its stale scope override the current
user request. New source/runtime discrepancies are tracked in
`notes/review/TH08_SOURCE_AND_RUNTIME_AUDIT.md`; the current architecture and
ordered implementation plan are in
`notes/review/TH08_SOURCE_AUTHORITATIVE_SOLVER_AUDIT.md`.

## Checkpoint

- Branch: `codex/th08-lunatic-source-audit`.
- **Current offline source-stateful checkpoint:** the solver repo now contains
  a replayable complete-stage IR/runtime/generator, closed-loop hard-no-Bomb
  campaign, source/C lockstep, geometry differential, and failure shrinker.
  The independent reduced C is tracked under `native/th08_source_oracle/`;
  the reference repo remains unmodified and was current at `57ee34f` after
  `git pull --ff-only`. Profiles span 480 to 12,000 frames. Seed `0xce0132`
  completed the extreme 12,000-frame runtime, saturated all 1,536 bullet
  slots, and exercised 156,186 transforms. This is a source-closed stress
  result after resolved producer events, not arbitrary ECL or route-hit
  authority. The retained 3,600-frame gate artifact
  `artifacts/benchmarks/th08_source_stage_fuzzer_gate_20260825.json` passes
  complete C lockstep, 180 NumPy/native geometry comparisons, 120 real local
  planner calls, hard no-Bomb, and exact RNG/collision membership. The latest
  repository suite passes 1,433 tests with 5 conditional skips. Read
  `notes/review/TH08_SOURCE_STATEFUL_STAGE_FUZZER.md` before extending it.
- **Current Lunatic physical checkpoint:**
  `lunatic_route2_fullrun_unattended_20260824_051944` completed Sakuya/Remilia
  Route 2 through Final-B at frame 230561 with 60 native hit edges, stage
  counts `1/4/8/15/14/18`, zero Bomb input, and exact Wine-prefix cleanup. It
  physically validates OPT-002A: ten issue-deadline misses all recovered, none
  is on a hit's causal row, and the former 32-decision Stage-4A self-lock did
  not recur. It does **not** validate a hit-rate improvement: OPT-001 had 61
  hits on a different RNG root. Fifty-seven of 60 residual hits follow robust
  action-set exhaustion, and the global corridor recorded zero submissions or
  queries across all 57,553 decisions. Do not run another route or change
  focus/boundary scoring before reading
  `notes/review/TH08_SOURCE_AUTHORITATIVE_SOLVER_AUDIT.md`.
- Historical Hard checkpoint:
  `hard_route2_stage4a_unattended_20260801_191508`. It completed Hard Stage
  4A with 18 hits, first hit 1975, zero Bombs, accepted replay, and complete
  cleanup. Twelve hits were boundary-associated and eleven used fast
  movement. This is a regression/falsifier, not a promoted outcome.
- **Observed no-scale-writer mechanism pass:** Stage-4A `184903` bound the
  exact runtime/static ECL identity, coherent unit root, stage/difficulty/
  route context, and complete installed-callback inventory. It restored
  3,599 constrained decisions from zero in `183730`; spell-56/60/64/68/72
  received 872/547/164/566/529 constraints, and recovery/distant-recovery was
  selected 319/809 times. The run completed 12 hits, first hit 1209, and zero
  Bombs. Different-RNG outcome counts remain observational; action-authority
  activation is observed.
- **Observed hard-authority seam:** `184903` also relaxed 57 exact-corridor
  constraints through the coarse terminal-threat fallback. Exact corridor,
  ordinary predecessor, held, delayed, and continuation-lease authorities
  are now non-relaxable. `191508` recorded zero such relaxations.
- **Observed continuous-position falsifier:** the old 16px global corridor
  represented only cell centers with zero sampling-radius clearance. The
  current lower bound consumes the complete cell half-diagonal
  `sqrt(2)*8 = 11.3137px`. On `191508`, queryable rows increased 5,104 to
  5,775 and median solve time fell 131.5 to 78.7 ms, but empty action sets
  increased 1,723 to 2,927, constrained decisions fell 3,599 to 3,001, and
  hits rose 12 to 18 on a different RNG root. The semantic hardening is
  retained; a uniform 16px lower kernel is physically ineffective and must
  not be called a solution.
- **Observed Hard regression:** historical checkpoint `709e858` completed a
  different-RNG Hard Stage 4A trial `20260726_212756` with six hits, one
  nonspell hit, 13,203 queryable global-policy rows, 8,073 constrained
  decisions, 725 selected recovery rows, 2,845 selected distant-recovery
  rows, decision cadence median/p95 2/3 frames, and local planning
  median/p95/max 11.686/20.830/38.136 ms. Current `175112` had only 4,737
  queryable rows, 847 constrained decisions, zero selected recovery/distant
  recovery rows, cadence 3/4, and local planning
  17.953/32.725/250.616 ms. Different-RNG hit totals are observational; the
  missing authority, zero selections, and latency tails are direct repeated
  delivery mechanisms.
- **Observed primary cause:** all 4,150 current spell policy queries had zero
  constrained decisions. The solver computed viable spell actions, but the
  schedule provenance was
  `diagnostic_constant_current_root_unknown_direction_no_authority`, so
  `time_scale.hard_authority` and corridor `action_authority` were false.
  Later SEM-SCALE work correctly revoked the old unsound constant-root
  assumption, but no sound Stage 1–5 replacement was installed. Work then
  concentrated on the sparse ordinary exact lane while most Hard hits were in
  spells.
- **Observed/inferred replacement boundary:** shipped native dataflow has
  gameplay scale writes in ECL callbacks 18/28/29; other writes reset scale at
  game/stage initialization. Exact decoded ECL for Stages 1–5 contains no
  literal or dynamic invoke/install of callbacks 18/28/29. Stage 6 and Final
  do contain callback 18 and therefore cannot use the same certificate. The
  next implementation is a runtime-ECL-identity-bound, unit-root,
  no-scale-writer schedule authority that fails closed on content, context,
  root, or callback-inventory mismatch.
- **Observed source-v15 physical result:** 519/1,065 source roots completed,
  436 were truncated, and 83 carried the full H268. The v15-targeted dynamic
  type/color, `0x19`, `0x25`, `0x35`, `0x6F`, and supported-transform failure
  reasons disappeared. Exact prepublication/delayed/lease authority was
  effective on 229/17/16 issues, with ten lease creates and seven renewals.
  Source v15 therefore passes its named semantic gate but does not improve
  the different-RNG hit total.
- **Observed canonical computation-gap falsifier:** the first hit's prior
  240-frame window contained 13 full-H268 source roots and exact
  prepublication authority on 43/50 decisions. Thus source publication was
  no longer absent before this hit. At the last safe issue f565, `down_left`
  was certified only through terminal f571 and no continuation lease was
  created. The next f566 capture launched a 394.522 ms synchronous delayed
  scan; input was not revisited until f594, 28 physical frames later.
  Retained bullet slot 1 crosses the held `down_left` path at f587
  (signed clearance -0.432), so the generated `sensor_gap` label is false:
  the bullet was observed, but the finite terminal proof expired during
  computation. The next correction is a hard held-action computation guard
  plus viable-kernel-informed exact probe ordering, not another ECL opcode.
- **Implemented computation guard, awaiting physical falsifier:** the former
  held-only H80 exact certificate is now a prerequisite for a synchronous
  delayed scan whenever no compatible lease exists. It consumes the complete
  native bullet/laser/body slab, future-source projection, no-write semantics,
  and the full effective issue-age/pickup support. An unsafe or unavailable
  held certificate blocks the scan and returns immediately to the bounded
  issue path; it grants no replacement action. The three-action terminal
  probe now orders current-kernel repair-volume candidates before fixed
  compass defaults, but each candidate still requires its independent exact
  prefix and terminal membership. The retained f566 slot-1 certificate is
  losing and therefore blocks the former 394.522 ms scan. Focused Linux and
  Windows gates pass 33/33. Rotate the physical falsifier to Stage 4A; do not
  infer success from aggregate hits alone.
- **Observed source-v14 physical result:** 801/1,275 source roots completed
  versus 645/1,235 in source-v13 `155718`; 58 versus 47 carried the full
  H268. The targeted main `0x05`/`0x06` and captured movement-state-2
  failures disappeared. Exact prepublication/delayed/lease authority was
  effective on 316/7/5 issues, with three lease creates and four renewals.
  This physically validates the v14 semantic correction, not route
  improvement.
- **Observed remaining latency/coverage mismatch:** all three ordinary hits
  still had zero exact authority in their prior 240-frame windows. Before
  canonical hit f1253, the first full-H268 root was f1223 and was submitted
  at f1230, but its 2352.884 ms solve completed at f1371, after the hit and
  after expiry. Closing reached main/auxiliary semantics must move complete
  coverage more than the observed roughly 141-frame publication delay. The
  next concrete blockers are main float-add `0x19`, main/auxiliary transform
  definition `0x6F`, auxiliary return `0x35`, dynamic type/color, auxiliary
  `0x25`, and the resulting active transform programs.
- **Implemented source semantics v15; physical semantic gate passed:** shipped
  code confirms direct-fire type/color are independent dynamic i16 operands,
  `0x25` normalizes one float lvalue, depth-zero auxiliary `0x35` terminates
  without a saved-frame restore, and `0x6F` writes one exact 24-byte transform
  record. Reached main `0x19/0x1A` now share the bounded auxiliary arithmetic.
  Active vector/angular acceleration, re-aim, and reflection use a conservative
  full-disc path bound; template replacement consumes the maximum reached
  template hitbox. Unsupported stack state, set-valued transform fields, and
  other transform kinds remain UNKNOWN. A real Stage-3 time-65 wave now closes
  through six fires, including active angular-velocity geometry. 93 Linux and
  93 Windows focused tests pass. Physical `171249` removed the named failure
  reasons and delivered exact authority in the canonical pre-hit window; its
  new blocker is unsafe synchronous computation after a finite terminal
  certificate, not missing source lead.
- **Observed lease-v4 physical result:** one lease was created and one
  renewed; 31 decisions captured it, 30 selected it, and 29 exact no-write
  issues were effective from f1725 through f1783. All retained the certified
  `down_left_fast` movement, emitted no physical input transition, passed the
  contact-body seam, and ended only at terminal expiry. Lease v4 therefore
  passes its narrow persistence/mechanism gate. It does not pass the global
  outcome gate: the run had five ordinary hits, and every ordinary hit's
  prior 240-frame window had zero effective prepublication, delayed, or lease
  authority.
- **Observed next source blocker:** the common pre-hit status was
  `future_policy_unavailable`. Source roots frequently reported a complete
  causal prefix but were truncated below H268 by reached main ECL opcode
  `0x05`/`0x06` or captured hostile movement state 2. Before canonical hit
  f1263, the first nontruncated full-H268 root appeared only at f1249, too late
  to solve and publish. Exact closure of these reached source states is now
  the next general gate; local ranking and stage waypoints remain behind it.
- **Implemented source semantics v14; physical semantic gate passed:**
  shipped `enemy_ecl_vm_step` confirms main opcodes `0x05` and `0x06` share
  the already-bounded local loop/set semantics. Shipped
  `enemy_motion_update` confirms state 2 requires stored displacement
  `+0x2DC4`, start `+0x2DD0`, easing bits 14..16, Th08Timer fraction/current
  at `+0x2DE0/+0x2DE4`, and duration `+0x2DE8`. Native projection v14 captures
  those fields and corrects the former `+0x2DDC` previous/current timer
  confusion, which also affected state 3. Missing or malformed timed state
  remains UNKNOWN. Linux focused and 147 Windows tests pass. Old retained
  state-2/3 roots cannot be uplifted. Physical `163434` confirms more complete
  and full-H268 roots, but not enough pre-hit lead for publication.
- **Observed Stage-3 first mismatch:** 701/1,214 source attempts failed because
  timeline 2 retained a nonzero fractional timer component; 465 crossed the
  native clock bracket. Every one of the 49 source attempts in the f7695..7935
  pressure window failed on the fraction, leaving no global submission before
  the hit. Native unit-scale timer advance at `0x00447421` preserves that
  fraction while incrementing the integer clock, and timeline instruction
  eligibility observes only the integer component. Source semantics v12 now
  validates finite timer state and discards the causally inert fraction only
  after exact unit scale is proved. Nonunit scale and nonfinite state remain
  fail closed. Focused Linux and 88 Windows tests pass.
- **Observed physical activation and remaining discontinuity:** the corrected
  run produced 692/1,261 complete source projections, 596 submissions, 595
  completed policies, and 265 effective ordinary exact-authority issues.
  Four delayed predecessors were effective and created four leases, but no
  lease was consumed: every lease was revoked by an uncontained fresh-body
  envelope. Before first hit f3181, exact authority ended at f1406; all 103
  decisions in f2941..3181 were `future_policy_unavailable` despite 14
  complete source captures in that window. The fraction correction is
  physically validated as source delivery, not as hit reduction or persistent
  recursive viability. Parent checkpoint `5fc6d92` then completed Stage 4A
  with 18 hits/10 nonspell versus its direct 21/12 baseline, but first hit was
  nearly unchanged at 833 versus 819; Stage 5 repeated exactly 18/10 versus
  its direct baseline. Both are different-RNG observations. Across Stage
  3/4A/5, every created lease remained ineffective and fresh-geometry
  revocation dominated. The next gate is therefore the common active-hostile
  trajectory/lease recertification seam, not another aggregate rerun.
- **Observed physical latency correction:** the ordinary fallback now builds
  an action-conditioned H80 predecessor indexed by final observed issue age,
  including computation, old pending evolution, held no-write, replacement,
  pickup delay 0..6, complete future births, and a fresh hostile-body slab.
  Packed player paths are bitwise equal to native-order scalar movement.
  Incremental action evaluation is ordered by a no-authority local proposal
  and reuses that immutable proposal after the scan. In `115838`, 11/21 scans
  physically acquired exact authority; median issue age was 25 frames versus
  43 before proposal reuse. CE-0250's zero-transition blocker is closed.
- **Implemented after cross-stage physical falsification, awaiting v13
  physical rotation:** an effective delayed action creates an immutable H80
  terminal-continuation lease.
  Each compatible fallback root first renews the held no-write action; only
  if that predecessor is unsafe may independent recovery directions be
  evaluated. Exact float32 position, active/held/pending support, epoch,
  stage, phase, unit scale, remaining horizon, fresh geometry, and the full
  content-addressed projection version are fail-closed. Spell-active and
  stage-route are reread at final issue, so computation may not carry an
  ordinary lease across a phase/context transition. A new complete mask
  requires a new exact delayed
  predecessor. Stage-4A f3191→f3192 exposed a native phase bug: priority-17
  current-input publication precedes its first priority-9 movement by one
  physical frame. Lease v3 retains that input-phase correction and requires
  source semantics v13, which adds every contact-enabled active hostile body
  to the exact ECL/native-motion trajectory from the projection root. Fresh
  geometry now conditions only the native observation seam at its own frame;
  it cannot replace the old causal proof with a restarted linear H80 future.
  Unstable observations, uncontained current bodies, older source semantics,
  and incomplete topology still fail closed. Rotated Stage-3 physical
  validation is next; scalar reserve remains rejected and local ranking is not
  safety authority.
- Native H=32 wind-tunnel checkpoint: `3d15953`; it is historical evidence,
  not the live ordinary horizon.
- Workspace-prune checkpoint: `be3e583` (`Prune TH08 active research
  workspace`). It removed dormant supplemental, candidate, prewarm, G5,
  priority-17, and old focused Final-B lanes while preserving the promoted
  baseline/pre-loss live path, native snapshot executor, exact pipeline
  workspace, and Final-B scale authority.
- Affected Linux focused gates and 186 Windows focused tests pass, including
  input-phase, continuation-lease geometry, enemy-mode, issue-stage,
  preexhaustion, prepublication, controller, and retained-source tests.
  Complete Linux
  discovery ran 1,284 tests in 10.659 seconds and exposed five unrelated
  workspace failures: four pre-existing native ABI header/binary-versus-
  manifest mismatches and the preserved user-edited factorized report's
  worker count 8 versus the old test expectation 16. Do not rewrite that user
  artifact or rebuild unrelated native outputs as part of this checkpoint.
- **Implemented, factorized hard lower authority:** default-off
  `--ordinary-preexhaustion-authority` no longer uses scalar reserve or the
  coarse signed terminal tensor. Ordinary nonspells build a 4px Boolean
  viability kernel with the 2.828px cell radius consumed as required
  clearance. At every issue, the active/held/pending predecessor holds the
  selected complete mask with no further writes across every pickup branch
  into the next active-policy layer. A still-pending command must be a member
  of that layer's exact action set.
- **Implemented, deterministic hard gate passed:** collision-control
  projection v14 now captures the manager singleton and every active ordinary
  ECL/timeline source, auxiliary VM, installed callback gate, emission
  descriptor, phase state, and reconstructable motion state. Legacy timed
  roots are not uplifted.
  Reachable timeline spawns and ECL emissions are lowered fail-closed into
  consumed annular-sector bullet and hostile-body AABB trajectories for 268
  frames. Unsupported opcodes, callbacks, timeline gates, motion, content
  identity, spell state, or nonunit scale remain `UNKNOWN`.
- The exact future projection is retained with the asynchronously published
  policy. Its geometry is now consumed twice under one version: every
  physical frame in the active/held/pending root-to-publication certificate,
  then every frame of the future corridor policy. Coverage metadata alone
  cannot authorize an action.
- In the physical gate, all 7,202 nonspell decisions were incorrectly
  rejected by the `player_transition_or_predeath` eligibility check, so the
  filter and early-kill preference each affected zero decisions. Native
  evidence shows player `+0xE2A68` retains a deathbomb-window limit and is not
  zero while alive. More importantly, an offline counterfactual with only
  that check removed still permits the canonical `down_left` action and
  degenerates to all 17 actions under an uncontrollable prefix and at a
  clamped boundary. Scalar boundary reserve is not equivalent to global
  viability; do not rerun this design.
- **Observed correction:** forcing the real 80-frame horizon makes the former
  16px signed predecessor empty at all five retained roots. Its earlier
  eight-action f817 result used H=32 and is not live authority.
- **Observed deterministic replacement:** the same immutable
  f817/833/835/850/910 chain has complete source/version coverage under the
  4px cell-radius lower kernel. Native exact recurrence and the actual live
  adapter independently agree that f817 permits only
  `left_fast/down_left_fast`, excluding active `up_fast` and issued
  `up_left_fast`. f833/f835/f850/f910 are already empty and remain fail
  closed. Windows measured f817 kernel/certificate at 1412/21 ms; the five
  roots have no unresolved action. This is finite-model evidence, not a
  physical outcome.
- **Observed physical integration falsifier:** Stage-4A run
  `20260731_220830` completed with 23 hits, first hit 939, and zero Bombs. Its
  different-RNG aggregate does not falsify the f817 directional result.
  Decisively, none of 1,754 live future-source projections completed: 1,726
  crossed the manager-frame bracket. All 10,016 ordinary-authority records
  therefore failed closed and zero actions were constrained. This falsified
  live source capture/delivery, not the finite-model predecessor.
- **Implemented after that run:** manager singleton plus all 480 ordinary
  slots are now captured in one contiguous 9.8 MiB read instead of at least
  481 sparse process reads. Source semantics v3 also lowers the reached
  dynamic direct-fire count, auxiliary subtraction, indexed-enemy
  `+0x2D30`, and set-valued FRScreen gate cases. Reached unsupported events
  still fail closed.
- **Implemented exact delivery acceleration:** the Boolean native kernel now
  rejects branches by next-layer terminal membership before walking hazard
  samples and publishes an exact all-action kernel when the whole clearance
  slab/layer proves every clamped transition safe. Hard membership no longer
  computes soft repair/recovery scans eagerly; directional recovery remains
  available when the Boolean predecessor is empty. Windows no-hazard
  viability fell from the physical 2,996 ms bootstrap solve to 282 ms cold
  and about 9 ms warm. The retained dense-root worst case is still 2,104 ms
  and remains fail-closed on expiry.
- **Observed contiguous-capture falsifier:** correctly configured Stage-4A
  run `20260731_231944` completed with 35 hits, first hit 498, and zero Bombs,
  but only 1/1,859 source projections completed; 1,836 crossed the manager
  frame and zero decisions received hard authority. The earlier
  `20260731_230657` replay omitted the runtime ECL identity flags and is an
  invalid authority experiment, not an 18-hit improvement.
- **Implemented after that run:** the dedicated source worker now allocates
  its 10.32 MiB destination before the frame bracket, reads directly into it,
  and exposes manager/pool memoryviews. This removes about 10.6 ms of Windows
  allocation/`.raw`/slice copies without relaxing exact frame equality or
  future-source coverage.
- **Observed physical authority activation:** Stage-4A run
  `20260731_233856` completed with 24 hits, first hit 845, zero Bombs, an
  accepted replay, and full cleanup. Stable capture produced 119/1,914
  complete roots; 196 ordinary decisions were constrained and 193 remained
  effective at issue. This proves the exact authority is physically live.
  It does not promote the outcome: all 98 pre-first-hit applicable roots were
  early all-17 safe sets, while the pressure wave had 295 unavailable roots.
  No nonempty effective authority appeared within 80 frames of a hit.
- **Observed semantic starvation:** the dominant complete-root blockers were
  699 manager-frame crossings, 476 legal auxiliary timer roots, 237 dynamic
  float variable `10069`, and 181 armed phase successors. The first two
  semantic classes plus generic auxiliary opcode-`0x02` wait scheduling are
  now lowered from shipped-code evidence in source semantics v4/projection
  v13. Armed phase successor coverage remains fail closed.
- **Observed source-v4 delivery falsifier and implemented correction:**
  Stage-4A `20260801_002006` completed 24/1205/no-Bomb. It produced 159/1,942
  complete projections, but exact authority was effective on 135/6,146
  nonspell decisions and 0/383 decisions in the 80-frame nonspell hit windows.
  Complete roots 1137..1200 were stranded behind an UNKNOWN-source future
  publication. Ordinary mode now spends no solver slot on incomplete source
  coverage and exposes a completed exact pending policy to the causal
  pre-publication predecessor before its epoch. The next gate tests this
  delivery fix; phase/transform/opcode/callback/movement closure remains open.
- **Observed pending-delivery activation and next correction:** Stage-4A
  `20260801_004533` completed 22/1837/no-Bomb. Exact ordinary authority was
  effective on 287/7,275 nonspell decisions; 110 effective roots used a
  completed pending policy and 43 did so before the first hit. This validates
  the CE-0244 delivery correction. Authority was nevertheless effective on
  0/287 decisions in the 80-frame windows before 11 nonspell hits. Complete
  sources carried up to 750 future sectors, and representative 6.9/19.8/23.5
  second solves spent 6.1/19.5/23.2 seconds building clearance but only
  0.81/0.24/0.23 seconds in viability.
- **Implemented exact sector-volume acceleration:** native geometry now
  groups identical origin/radial/inflation samples, evaluates their exact
  circular angular union once per lattice point, and parallelizes disjoint
  frame slabs over at most 16 workers. A synthetic 750-trajectory, 81-frame,
  4px regression completed in about 198 ms and matched the independent Python
  signed-clearance oracle exactly at sampled frames; 80 randomized angular
  unions also had zero observed error. Linux/Windows focused native parity and
  the retained f817/833/835/850/910 semantic chain pass.
- **Observed sector win and newly isolated recurrence deadline:** Stage-4A
  `20260801_011902` completed 26/796/no-Bomb with an accepted replay and full
  cleanup. Different-RNG hit count is observational. Exact sector clearance
  fell from the preceding physical maximum 23.2 seconds to 0.993 seconds,
  while authority was effective on 399/7,162 nonspell decisions. It was still
  effective on 0/380 decisions in the 80-frame nonspell hit windows. At the
  canonical hit, source 639 spent 478 ms in clearance and 918 ms in Boolean
  viability; it arrived after the corridor's last nonnegative gate at frame
  714 and the predecessor was empty by frame 716. Future-source failures,
  especially 1,195 armed phase transitions, dominate later aggregate gaps but
  do not explain this first hit.
- **Implemented exact interior recurrence acceleration:** each Boolean layer
  now proves an all-action state in one set-valued reachable box only when
  every covered signed-clearance cell and every terminal action is safe. All
  unproved states use the unchanged branch recurrence. On Windows the retained
  f817/833/835/850/910 chain keeps exactly the same action sets and no
  unresolved action while maximum solve time falls from 2,071 to 775 ms. A
  fresh Stage-4A physical gate is next; Stage 5 remains withheld.
- **Observed recurrence win and coverage handoff:** Stage-4A
  `20260801_015631` completed 20/2009/no-Bomb with accepted replay and cleanup.
  Different-RNG hits are observational. Nonspell exact solve maximum fell from
  3,050 to 1,338 ms and viability maximum/p95 from 3,026/1,664 to
  1,038/926 ms. Before the first hit, 278 decisions had exact applicable
  authority and 102 of those were directional, but authority was still 0/238
  in the 80-frame windows before nine nonspell hits. Every first-hit-window
  decision was `future_policy_unavailable`; roots 1915..2007 chiefly failed
  on nonzero transform programs, with opcode-`0x19` interleaved.
- **Implemented bounded transform/addition closure:** shipped-code recheck
  confirms only transform records whose kind intersects the bullet's original
  flags execute. Active `0x80` stop/re-aim is lowered as a full-direction
  path-length disc using the maximum emitted/resume speed, without predicting
  the future player. Barrier, culling-suppression, and sound records are
  movement-neutral; every other active kind remains UNKNOWN. Auxiliary
  opcode-`0x19` now performs exact interval addition. The retained Windows
  chain keeps identical action sets/no unresolved action. Physical
  revalidation is next; Stage 5 remains withheld.
- **Observed transform closure and issue-time miss:** Stage-4A
  `20260801_022228` completed 19/1833/no-Bomb with accepted replay and cleanup.
  Transform and opcode-`0x19` projection failures disappeared. For the first
  time, three decisions in a nonspell 80-frame hit window had directional
  exact sets of 5/8/6 actions. All three missed issue deadline, however, so
  effective pressure-window authority remained zero. At frames
  3501/3518/3532 the held `up_right` input was outside or not selected from
  the exact set, but 12..16 frames elapsed after capture against pickup-support
  high 6 and the deadline guard correctly held the old input.
- **Implemented causal delivery QoS and next reached flow:** ordinary exact
  solves now run below-normal on their background owner and use eight native
  workers, leaving capacity for TH08/sensing/issue control. The Windows
  retained-chain maximum rises from 804 to 1,095 ms but remains within the
  80-frame initial lead; exact action sets and unresolved status are unchanged.
  Reached auxiliary `0x05` loop-jump and `0x2E` integer-LE jump are also
  advanced exactly; other flow remains fail closed. Revalidate Stage 4A;
  Stage 5 remains withheld until effective pressure-window authority appears.
- **Observed QoS falsifier and bounded phase correction:** Stage-4A
  `20260801_024419` completed 22/1291/no-Bomb with accepted replay and cleanup.
  Eight-worker/background-low-priority execution was active; solve p95 changed
  230→218 ms, but a 5,290-ms tail remained and hit-window effective
  directional authority stayed zero. `0x05`/`0x2E` failures disappeared;
  ordinary slot-0 armed phase transition became 1,243/1,714 incomplete roots.
  Source v6 captures health successors and the exact phase timer and ignores
  only a timeout proved beyond `elapsed + horizon`; health or reachable
  timeout transitions still fail closed. Linux/Windows tests and the retained
  exact action sets pass. Revalidate Stage 4A before any Stage-5 run.
- `--kill-before-saturation` now uses observed ordinary bodies only. The
  falsified timeline spawn forecast is withheld from live input.
  Observed-body alignment/unfocus remains a proposed objective, but the
  rejected reserve set is no longer an eligibility source; exact ordinary
  viable membership and fresh issue safety are required before another live
  gate.
- `audits/` and `archive/` are untracked/local. Never stage them.

## Current Outcome

### Physical baselines

Latest user-authorized Lunatic Route-2 practice ring:

| Workload | Run | Hits | First hit | Bombs | Replay |
| --- | --- | ---: | ---: | ---: | --- |
| Stage 3 lease-v4 persistence gate | `20260801_155718` | 7 | 1263 | 0 | accepted |
| Stage 3 source-v14 delivery gate | `20260801_163434` | 4 | 1253 | 0 | accepted |
| Stage 3 | `20260731_091104` | 5 | 2150 | 0 | accepted |
| Stage 4A | `20260731_091925` | 13 | 2555 | 0 | accepted |
| Stage 5 | `20260731_093027` | 12 | 2124 | 0 | accepted |
| Stage 5 early-kill gate | `20260731_122855` | 13 | 6981 | 0 | accepted |
| Stage 4A global/early-kill gate | `20260731_130103` | 16 | 1827 | 0 | accepted |
| Stage 4A pre-exhaustion early-kill gate | `20260731_133852` | 11 | 4148 | 0 | accepted |
| Stage 4A forecast/global investigation | `20260731_142342` | 18 | 1915 | 0 | accepted |
| Stage 4A reserve-authority falsifier | `20260731_152921` | 17 | 914 | 0 | accepted |
| Stage 4A live-source/delivery falsifier | `20260731_220830` | 23 | 939 | 0 | accepted |
| Stage 4A ECL-config-invalid replay | `20260731_230657` | 18 | 499 | 0 | invalid gate |
| Stage 4A contiguous-capture falsifier | `20260731_231944` | 35 | 498 | 0 | accepted |
| Stage 4A exact-authority activation | `20260731_233856` | 24 | 845 | 0 | accepted |
| Stage 4A source-v4/delivery falsifier | `20260801_002006` | 24 | 1205 | 0 | accepted |
| Stage 4A pending-delivery/clearance falsifier | `20260801_004533` | 22 | 1837 | 0 | accepted |
| Stage 4A sector/viability deadline falsifier | `20260801_011902` | 26 | 796 | 0 | accepted |
| Stage 4A recurrence/coverage handoff | `20260801_015631` | 20 | 2009 | 0 | accepted |
| Stage 4A transform/delivery falsifier | `20260801_022228` | 19 | 1833 | 0 | accepted |
| Stage 4A delivery/phase falsifier | `20260801_024419` | 22 | 1291 | 0 | accepted |

The automatic older-root comparisons were 15→5, 10→13, and 19→12. They are
observational only: RNG roots differ and the proposed WS-H strategies were
disabled in the original ring. The later early-kill gate is also
different-RNG: it physically applied 27 certified unfocus preferences,
delayed first hit by 4857 frames relative to the listed Stage-5 baseline, but
worsened total hits by one.

Stage-4A run `20260731_152921` is different-RNG and its 17/914 aggregate is
observational. Its experiment activation is decisive: the flag was present
on all 12,029 decisions but yielded zero eligible, applicable, or effective
constraints and zero early-kill applications. All 7,202 nonspell decisions
failed on a stale native-field interpretation. The canonical hit also
falsifies a gate-only repair. Contact bullet slot 455 first entered the
retained nearby set at decision 817; the snapshot-801 global policy still
certified `down_left` through frame 833, while the snapshot-818 policy
delivered an empty set at 835. The compact trace cannot attribute that version
flip to slot 455 alone. Counterfactual reserve evaluation still allowed
`down_left` there and allowed all 17 actions at frames 850 and 910. Robust
local prefixes exhausted only at 910, four frames before the hit.

The newer Stage-4A run `20260731_220830` is also different-RNG; its 23/939
aggregate is observational and must not erase the earlier local improvement.
Its exact failure is live integration: all 10,016 authority records had
incomplete coverage and no allowed set. Of 1,754 future-source attempts, zero
completed; 1,726 crossed `enemy_manager_frame`, 16 observed impossible
auxiliary depth from a torn root, four lacked the then-uncaptured indexed
timeline field, three reached a dynamic direct-fire count, two hit an
FRScreen message-clock boundary, and three reached the now-lowered auxiliary
`0x1A`. The worker also produced 3,610 expired-policy and 3,792 no-query
decisions. These are capture/publication counterexamples, not evidence that
`left_fast/down_left_fast` at retained f817 was wrong.

Stage-4A run `20260731_231944` supplied the correctly configured follow-up.
Only 1/1,859 projections completed and 1,836 crossed manager frames; all
4,499 state-eligible nonspell decisions remained `future_policy_unavailable`,
including all 332 before first hit 498. Its 35 hits are fallback-path evidence.
The preceding `20260731_230657` run had no runtime ECL image, emitted zero
source projections, and is retained only as a configuration counterexample.

Stage-4A run `20260731_233856` closes the capture/activation question:
119/1,914 source projections completed, 205 decisions were authority-eligible,
196 were constrained, and 193 were effective at issue. There were 24
nontrivial directional sets and nine exact empty predecessors; the early
applicable sets before hit 845 were all 17-action safe sets. The 24-hit
different-RNG aggregate is not a causal regression verdict. Its actionable
falsifier is pressure-wave semantic starvation, not authority wiring.

Stage-4A `20260801_002006` verifies that source v4 removed the earlier
`10069` and legal auxiliary-delay-root failures, but it did not deliver useful
authority near hits. Exact authority was effective on none of 383 decisions
inside the 80-frame windows before the 14 nonspell hits. At the first hit,
complete roots 1137..1200 existed while an UNKNOWN-source future publication
blocked the serial worker. This is now corrected by gating solve submission on
complete source coverage and treating a completed exact pending policy as the
pre-publication terminal kernel. Stage 5 was correctly skipped.

Stage-4A `20260801_004533` physically validates that correction: 110 effective
ordinary decisions used the exact pending terminal. It also isolates the next
deadline blocker. Dense complete future sources reached 750 sector
trajectories and spent up to 23.2 seconds in clearance-volume construction,
leaving zero effective authority in all nonspell hit windows. Native grouped
angular-union/frame-parallel clearance is now deterministic-parity validated;
its physical effect has not yet been measured.

The physical forecast gate also falsified the current timeline observer as a
general later-wave source. All 376 observations recycled the same timeline-0
startup birth at time 1, x=30, and only three affected input. Full-health
observed-body targeting remains useful, but zero-pointer timeline lifecycle
must be disambiguated before the birth forecast is trusted again. The live
forecaster is now disabled rather than used as an eligibility source.

Latest full game-start Lunatic Route-2 run:

- `lunatic_route2_fullrun_unattended_20260824_051944`
- 60 hits, zero Bomb inputs
- stage counts `1/4/8/15/14/18`
- reached `route_complete`
- physically validates OPT-002A deadline feedback and preserves OPT-001/002
  sensing improvements;
- 57/60 hits follow robust action-set exhaustion; causes are 41 modeled
  committed-prefix collisions, 16 observed bullets, two observed lasers, and
  one enemy body;
- 48 boundary and 43 fast-mode labels are correlational. Source audit found a
  2px planner radius versus the physical 1px half-extents, nonlethal bullet
  states admitted as hazards, and capsule-versus-rectangle laser mismatch;
- all 57,553 corridor submissions were hard-authority blocked, so worker and
  global query counts remained zero. The VPS did no strategic search.

The preceding OPT-001 and OPT-002 routes remain useful mechanism references:
`...022909` had 61 hits and `...034510` had 67. Their different native RNG and
post-hit cascades make all hit deltas observational.

The historical Windows run
`lunatic_route2_fullrun_unattended_20260730_222529` had 68 hits with stage
counts `2/3/5/20/15/23`, but used pretarget guidance that is not accepted as
source-authoritative under the current contract. Treat its lower latency and
guidance as diagnostic rather than promotion authority.

Retained dossiers are under `notes/runs/`. Compact reports and valid
practice replays remain under `artifacts/`.

### Native wind tunnel

Canonical Stage-5 replay first hit:

- manager frame 2136;
- root frame 2129;
- recorded mask `0x05`;
- hostile bullet slot 45;
- signed separation `-0.966766`.

The rolling executor replaces only the fixed native calculation-chain call,
holds the owner at the root, freezes unrelated threads, executes original
TH08 update code, and restores a verified same-session root. Parent replay is
bit/exact-state checked before branch authority.

Observed result:

- all 36 no-Bomb root masks were executed in original TH08;
- 324 causal branches were searched;
- a warm session executed 180 branches in 309.089 seconds with exact parent
  repeats;
- policy `0x94 -> 0x44 -> 0x10 -> 0xA4` at frames
  `2129/2137/2145/2153` stays unhit through frame 2161;
- an H=32 natural frame pump matches 32/32 native snapshot ticks.

This proves one exact fixed-root, fixed-horizon original-engine witness. It
does not prove a full spell, live delivery, or physical NMNB.

Primary evidence:

- `artifacts/runtime_reports/th08_native_snapshot_causal_policy_root2129_h32_20260730.json`
- `artifacts/runtime_reports/th08_native_model_trajectory_root2129_h32_20260730.json`
- `artifacts/runtime_reports/th08_native_model_consumable_h1_root2129_20260730.json`
- `artifacts/runtime_reports/th08_native_state2_lifecycle_root2129_h8_20260730.json`
- `artifacts/runtime_reports/th08_native_h1_ecl_source_differential_root2129_20260730.json`
- `notes/architecture/NATIVE_REPLAY_CAUSAL_WIND_TUNNEL_AND_REPLAY_SAVE_CONTRACT_20260730.md`

The old closed-form slot-45 forecast first differed by one x ULP. A corrected
per-update binary32 recurrence matches the retained native fixture. The
current source differential still returns `UNKNOWN` at the unresolved
pre-enemy/pre-aux producer; do not infer it from retrospective RNG alignment.

One mapping-epoch poison event is retained. A future persistent warm service
must use single-writer ownership, immutable session/root IDs, branch
validation, cooperative cancellation, idle TTL, poison cleanup, and automatic
rebootstrap. Do not weaken the epoch gate for speed.

### Combat/resource model

The active WS-H reconstruction now covers Route-2 normal shots,
supported native damage, enemy generations, defeat/cleanup distinction,
Boss transition identity, item allocation/pickup, Power/resources, and
mandatory timeline events. Its general combat model remains offline. The only
live combat experiment is the narrow default-off ordinary-enemy alignment
preference described above. It has no independent safety authority.

The immediate high-value hypothesis is not another schema:

- spells: survival first;
- ordinary enemies: inside the survival-feasible set, test whether earlier
  kills prevent later saturation;
- dynamically compare focused micro-control with unfocused fast movement and
  shot coverage;
- collect early Power only when a safe path produces a causal later benefit.

The first Stage-5 root-4300 test is complete. **Observed:** clearing Focus for
eight ticks defeated one 20-HP enemy, suppressed three later hostile bullets
per nine-frame emission cadence, and reduced the endpoint bullet count
548→539. **Observed:** the current offline global layer-0 viable masks and
safe-action masks remained exact-equal at frames 4314/4323/4332. That offline
result did not end the hypothesis; the physical gate below exercised the rule
27 times, but global live guidance still never published.

See `notes/CURRENT_COMBAT_RESOURCE_MODEL.md`.

## Live Authority

The physical policy is hard no-Bomb:

1. native state sensing and hazard projection;
2. native packed bullet decode;
3. robust Boolean viability;
4. baseline local beam plus promoted pre-loss continuation preference;
5. fresh issue-time collision certificate;
6. exact-version action transaction and fail-safe fallback.

The latest full route loads the pinned Final-B ECL image, but its transported
unit schedule remains
`experimental_pretarget_unit_transport_unknown_direction`. Under
authority-only corridor policy this is not a hard schedule: every due
submission was blocked and no global policy constrained input. The root-only
constant-scale continuation remains diagnostic and unknown-direction, never a
general hard-safety authority.

The rejected scalar pre-exhaustion experiment is no longer connected to live
input. The replacement remains default-off, but may now provide ordinary
action authority only when the exact source projection, fresh held-prefix
geometry, 4px lower kernel, active policy layer, interval, and version all
match. Any unsupported source, delivery gap, expired layer, or empty
predecessor still fails closed.

Removed lanes must not be re-enabled from archive without a new causal need
and explicit `STRATEGY.md` decision.

## Next Implementation Gate

TH08 work is active. The next promotion extends the new offline laboratory;
do not run another route merely to sample a different RNG root:

1. preserve the completed generic 21-type ANM lifecycle and source-order
   binary32 geometry differentials; do not replace them with a global age or
   fixed numeric guard;
2. lower child VM/timeline births and callback 14 incrementally, retaining an
   explicit `UNKNOWN` at every unsupported reached dependency;
3. join a complete action-conditioned future to the already-closed Stage-5
   scale/root/geometry/policy version and submit global work in offline shadow;
4. require a same-capsule losing-to-viable global-policy change, zero oracle
   disagreement, and bounded latency before one focused Practice gate. Run a
   full route only after that integrated gain.

Never unblock corridor action authority by provenance alone. The current
active-spell request can omit future births, so scale, complete reached-source
coverage, exact geometry, robust delay, and issue version must become one
certificate.

## Research Loop

Use this sequence:

`first hit/root -> exact parent repeat -> offline/native branches -> first mismatch -> one general change -> same-root win -> native replay confirmation -> rotated focused physical trial -> full route after a major integrated gain`

All-36 portfolios, long horizons, complete test suites, and full physical
routes are milestone gates, not mandatory per-edit checks.

## Commands

### Import smoke

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts python3 - <<'PY'
import th08_live.controller
import th08_runtime.native_snapshot
import th08_runtime.native_snapshot_projection
import tools.th08_native_snapshot_causal_search
import analysis.th08_native_combat_branch_report
import th08_automation.practice_supervisor
import th08_automation.full_route_supervisor
print("import smoke: ok")
PY
```

### Focused and complete Linux tests

```bash
PYTHONPATH=scripts python3 -m unittest discover -s tests \
  -p 'test_relevant_file.py'

PYTHONPATH=scripts python3 -m unittest discover -s tests -p 'test_*.py'
```

### Windows UNC discovery

Do not use `cmd.exe cd/pushd` or ordinary UNC discovery. Use:

```bash
/mnt/c/Users/21992/AppData/Local/Microsoft/WindowsApps/python.exe -c \
  'import sys,unittest; root=r"\\wsl.localhost\ubuntu\home\pentester\coding\codex_ida\th08"; sys.path.insert(0,root+r"\scripts"); tests=root+r"\tests"; suite=unittest.TestLoader().discover(tests,pattern="test_*.py",top_level_dir=tests); result=unittest.TextTestRunner(verbosity=1).run(suite); raise SystemExit(0 if result.wasSuccessful() else 1)'
```

Change only `pattern` for a focused Windows run. Do not run Linux and Windows
performance gates concurrently.

### Native build

```bash
python3 scripts/tools/build_native_planner.py --target linux
python3 scripts/tools/build_native_planner.py --target windows
python3 scripts/tools/build_native_planner.py --target windows-x86
```

`windows` preserves the existing x86-64 target. Use `windows-x86` for the
32-bit embeddable Python process that controls the PE32 TH08 executable under
Wine; the runtime loader selects between them from Python's pointer width.

Use `TOUHOU_DISABLE_NATIVE_PLANNER=1` only for an explicit rollback/ablation.

### Source-stateful complete-stage fuzzer

```bash
PYTHONPATH=scripts .venv/bin/python scripts/build_th08_source_oracle.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts .venv/bin/python \
  scripts/analysis/th08_source_stage_fuzzer.py \
  --profile gate --seed 0xce0132 --count 1 \
  --planner-stride 30 --geometry-oracle-stride 60 \
  --output artifacts/benchmarks/th08_source_stage_fuzzer_gate_20260825.json
```

The command runs to the program's full frame count; it has no duration-based
early kill. Use `--replay` for an exact stored program and
`--counterexample-dir --shrink-failures` to retain and reduce failures. Exact
coverage and nonclaims are in
`notes/review/TH08_SOURCE_STATEFUL_STAGE_FUZZER.md`.

### Physical trials

For this VPS's prefix-scoped Wine path, prepare and smoke-test via
[`notes/operations/TH08_WINE_VPS.md`](notes/operations/TH08_WINE_VPS.md)
before invoking the full-route supervisor.

Run only with explicit user authorization from Windows:

```bat
run_th08_practice_agent.bat --stage 3
run_th08_practice_agent.bat --stage 4a
run_th08_practice_agent.bat --stage 5
run_th08_practice_agent.bat --stage 6b
run_th08_full_route_agent.bat
```

The BAT wrappers add `--armed`. F8 starts, F9 stops, and F10 exits. Before
launch verify TH08 identity, foreground, route/difficulty, gameplay state,
no-life-decrement patch, and no-Bomb configuration. Monitor trace growth and
the exact interop process; always release keys and clean up.

## Common Traps

- Different-RNG hit totals are not controlled A/B evidence.
- A later hit is not independent after the first hit changed resources.
- A replay future cannot be reused after a different action.
- Native/Python parity is not model completeness.
- Static shot width, damage, item availability, or Power gain is not survival
  improvement.
- More tests, reports, schemas, or audited addresses are not solver progress
  unless they unblock a causal hit-reduction experiment.
- Do not restore retired code because an archived note mentions it.
