# TH08 Source And Runtime Audit

Last updated: 2026-08-25.

This ledger tracks discrepancies found while rebasing the live solver on the
exact Japanese TH08 1.00d executable, using the independently reconstructed
source tree at `../th08` only as a semantic reference. Rebuilding that source
tree is not part of this solver task. This ledger is intentionally separate
from historical run dossiers: entries remain open until the responsible solver
path is fixed and validated.

The ordered one-change-at-a-time implementation and physical experiment
sequence is tracked in `TH08_LUNATIC_OPTIMIZATION_CAMPAIGN.md`. The integrated
root-cause analysis and replacement architecture are tracked in
`TH08_SOURCE_AUTHORITATIVE_SOLVER_AUDIT.md`.

Evidence labels follow the repository contract:

- **Observed:** read directly from the exact executable, runtime, or retained
  trace.
- **Inferred:** follows from observed facts but has not yet received a direct
  physical falsifier.
- **Hypothesized:** a candidate explanation or improvement awaiting evidence.

Statuses include `OPEN`, `CONFIRMED-*`, `FIXED-OFFLINE`,
`VALIDATED-PHYSICAL`, `REJECTED`, and `RETRACTED`.

## Target And Scope

- Active target: Sakuya/Remilia, Lunatic, Route 2, Final-B, hard no-Bomb.
- Current integrated checkpoint:
  `lunatic_route2_fullrun_unattended_20260824_051944`, 60 native hit edges,
  stage counts `1/4/8/15/14/18`, zero Bomb input, route complete. It validates
  OPT-002A's deadline feedback mechanism but is not a same-root hit-rate win.
- Current VPS baseline: full route
  `lunatic_route2_fullrun_unattended_20260823_170206`, 85 native hit edges,
  stage counts `1/8/14/14/18/30`, zero Bomb input. Historical comparator
  `lunatic_route2_fullrun_unattended_20260730_222529` recorded 68 hits with
  stage counts `2/3/5/20/15/23`.
- Post-fix full route:
  `lunatic_route2_fullrun_unattended_20260823_183138`, 58 native hit edges,
  stage counts `4/6/5/13/9/21`, zero Bomb input. This is 27 fewer hits than
  the same-day 85-hit baseline, but remains a single non-seed-paired physical
  comparison.
- Exact executable: Japanese TH08 1.00d, 840,704 bytes, SHA-256
  `330fbdbf58a710829d65277b4f312cfbb38d5448b3df523e79350b879213d924`.
- The no-life-decrement patch is allowed for diagnostics. Native hit edges,
  not remaining lives, are the hit metric.

## Findings

### AUD-001 — Enemy lethal body half-extents are inflated by 2.25x

Status: **FIXED-OFFLINE**

**Observed:** ECL opcode 77 writes its two operands directly to enemy contact
size fields `+0x2D70/+0x2D74`. Exact target function `0x0042C290` passes that
vector through `Float3 / 1.5f` before calling player deadly-contact function
`0x0044A360`. That function constructs bounds as `center +/- size / 2`.
Therefore the lethal enemy-body half-extents are:

```text
raw ECL contact size / 1.5 / 2 = raw contact size / 3
```

The target instructions at `0x0042C333` push float bits `0x3FC00000`
(`1.5f`) into the division helper; `0x0044A386..0x0044A3D3` divides both
dimensions by the target's `2.0f` constant.

**Observed solver discrepancy:** both live enemy decoding and ordinary future
source projection use `0.75 * raw contact size` as each half-extent. The old
2026-07-23 note explicitly derived this from a mistaken multiply-by-1.5
interpretation.

Affected paths:

- `scripts/th08_live/enemy_sensor.py`
- `scripts/th08_ordinary_future_sources.py`
- enemy-body decoder and future-source regression fixtures

**Inferred impact:** body hazards are 2.25x too wide and high. This can create
false collisions, false empty viability sets, and unnecessary boundary-seeking
actions. It does not by itself explain every bullet/laser hit.

Acceptance:

1. one shared, source-cited conversion implements raw-size to lethal
   half-extent;
2. live and future paths use it;
3. focused decoder/future-source tests pass;
4. a physical trace confirms observed body geometry and records the effect on
   empty action sets and hits.

**Fixed offline:** `scripts/th08_enemy_collision.py` now preserves the target's
binary32 store between `/ 1.5f` and AABB halving. Live pool decoding, the
spell-owner guard, and ordinary ECL future projection share that conversion.
The spell guard separately retains raw contact dimensions for the unscaled
player-shot damage AABB. Focused collision/controller/future-source/trace
regression passed 156 tests. Acceptance item 4 remains pending, so this is not
yet `VALIDATED-PHYSICAL`.

### AUD-002 — Reconstruction build/comparator is outside solver scope

Status: **REJECTED**

**Observed:** `../th08/resources/th08.exe` is locally bound to the exact target,
but `../th08/scripts/prefix` is absent. The focused VC7 objdiff build therefore
produces no object. `th08run.bat` currently masks this command-not-found
failure because `%errorlevel%` is expanded before `%*` runs.

**Scope decision:** the user explicitly designated `../th08` as reference
material, not an artifact that this work needs to rebuild. The solver audit
therefore uses the exact shipped executable and physical traces as primary
evidence and does not provision or modify the reconstruction toolchain. No new
comparator pass is claimed.

### AUD-003 — Solver Python environment is missing its only declared dependency

Status: **FIXED-OFFLINE**

**Observed:** system Python 3.11 cannot import NumPy; `requirements.txt`
declares `numpy>=1.24`. Focused tests fail at import before executing solver
code.

**Fixed:** created ignored `.venv`, installed NumPy 2.4.6 under Python 3.11.2,
and passed the 131-test enemy-decoder/future-source baseline before changing
the model. The corrected model's post-change test evidence is recorded with
AUD-001.

### AUD-004 — Windows native planner assumes x86-64

Status: **VALIDATED-PHYSICAL**

**Observed:** the game is PE32. This host provides
`i686-w64-mingw32-g++` but not `x86_64-w64-mingw32-g++`. The build tool and
runtime loader nevertheless hard-code `windows-x86_64/touhou_viability.dll`.

**Fixed offline:** `build_native_planner.py --target windows-x86` now uses the
host's `i686-w64-mingw32-g++` and writes
`native/build/windows-x86/touhou_viability.dll`. The loader selects x86 or
x86-64 by the controlling Python process's pointer width while preserving the
existing Linux and `--target windows` paths. The host produced a PE32 i386 DLL
whose 45 exports match the checked-in manifest. The 2026-08-23 Wine smoke ran
under 32-bit Windows Python, loaded that exact DLL (SHA-256
`4c8c3a34485ec22437224d0fa8a5ad631d3d64f952d66bc9e621147cedf41603`),
and successfully applied its native worker-limit ABI call.

### AUD-007 — Native ABI manifest omits a shipped export

Status: **FIXED-OFFLINE**

**Observed:** the public header, implementation, Python binding, and built
Linux library all contain `touhou_annular_sector_frame_clearance_v1`, but
`native/abi_symbols_v1.txt` omitted it. The authoritative header/manifest test
therefore failed even before a Wine run.

**Fixed:** the symbol is now in the manifest, and Linux plus both Windows
architecture export checks consume the same 45-symbol list.

### AUD-008 — Three retained offline gates are internally stale

Status: **FIXED-OFFLINE**

**Observed:** both future-body differential JSON files differed from their
deterministic builders only in the recorded SHA-256 for the already-tracked
`scripts/th08_enemy_mode.py`. The factorized-prefix report records an applied
8-worker limit, while its test still asserted 16 after an older report update.

**Fixed:** refreshed only the two provenance hashes to the current tracked
source hash and aligned the worker assertion with the retained report. No
semantic output, authority flag, winning action, or timing record changed.

### AUD-009 — Supervisor parser rebuilds a foreign concrete Path class

Status: **FIXED-OFFLINE**

**Observed:** the Linux test that exercises the Windows-only supervisor path
temporarily changes `os.name` to `nt`. Both supervisors then wrapped their
already-created `PosixPath` default in a new generic `Path`, which attempts to
instantiate `WindowsPath` and fails before the mocked runtime starts.

**Fixed:** environment overrides now use the same concrete path class as the
import-time default, while the no-override path reuses that default directly.
This preserves real Windows behavior and makes the platform-boundary test
independent of global `pathlib` dispatch.

### AUD-012 — VPS/source-corrected full-route baseline is 85 hits

Status: **VALIDATED-PHYSICAL**

**Observed physical:** run
`lunatic_route2_fullrun_unattended_20260823_170206` completed all six Route-2
stages through Final-B at manager frame 231,289. It issued 51,411 decisions,
recorded 85 native hit edges and no Bomb input, and terminated by
`route_complete`. The isolated Wine host report passed with controller return
code zero, exact-prefix leftovers `[]`, no duration/stall termination, display
`:98`, CPU set `24-47`, and clean repository commit `1de7add`.

The historical exact full route recorded 68 hits, so the observed delta is
`+17`. This is not a paired-seed causal estimate: RNG path, code revision,
host, and cadence differ. It answers only that the source-corrected solver can
finish physically on this VPS; it does not establish that more cores alone
caused the improvement.

### AUD-013 — Global corridor compute has no authority before an exact scale schedule

Status: **VALIDATED-PHYSICAL**

**Observed:** the baseline produced 9,894 completed four-worker corridor
solutions and 50,760 query-bearing decisions, but
`global_constraint_applicable_count=0`. Every pre-target Final-B schedule was
tagged `experimental_pretarget_unit_transport_unknown_direction`; the hard
authority gate correctly stripped targets, allowed actions, repair volumes,
and recovery distances before local action selection. Median/p95 corridor
solve time was 122.08/283.18ms. Consequently, assigning more VPS cores to this
shadow calculation could not improve a single issued action in the observed
route.

**Fixed:** `--authority-only-corridor` now suppresses submissions while the
time-scale schedule is diagnostic-only, without weakening the existing hard
gate. A solve is still submitted once the exact source schedule grants hard
action authority. The isolated Wine full-route runner enables this policy by
default and records it in both host and controller telemetry; generic/manual
controller behavior remains opt-in compatible.

**Validated physical:** all 55,024 decisions in post-fix run `...183138`
reported `authority_blocked_submission=true`; hard submission authority was
available zero times, and submission/completion counts were both zero. The
route ended after spell 182, before the deliberately narrow spell-190 exact
source contract, so none of the removed work could have constrained a live
action in this run. Compared with the baseline, `observe_to_input` median/p95
fell from 50.99/78.37ms to 47.59/67.28ms, and action-lag median/p95/max fell
from `2/4/13` to `2/3/6` frames. Local-plan median rose from 28.29 to 30.35ms,
while p95 was nearly unchanged (46.46 versus 46.13ms), which distinguishes the
removed asynchronous/global load from the serial local planner.

### AUD-014 — Disabled item objectives still copy and decode 1.55MB per decision

Status: **VALIDATED-PHYSICAL**

**Observed:** `ITEM_OBJECTIVES_ENABLED=False`, and planner preparation reduces
the selected-item set to empty before any action scoring. Nevertheless every
baseline decision copied all `2096 * 0x2E4 = 1,551,040` item bytes through
Wine and decoded them solely for optional telemetry. Item-pool read time alone
had median 1.33ms; it had no control consumer.

**Fixed:** the live sensor can omit the item buffer/read, and the controller
does so unless item objectives are enabled or the new explicit
`--trace-items` diagnostic is requested. Planner-objective telemetry uses
`null`, rather than a false observed count, when item capture is disabled;
the serialized item list is empty by contract. Bullet and laser near-player
evidence under `--trace-radius` remains enabled.

**Physical integration correction:** the first attempted post-fix launch
exposed one stale unconditional decoder call (`index out of bounds on
dimension 1`) when the deliberately empty item buffer reached the controller.
`_decode_items_if_captured` now prevents that call, with a regression proving
the disabled branch never invokes the fixed-size decoder. In completed run
`...183138`, item read and decode median/p95/max were all exactly 0ms, versus
baseline medians 1.33ms and 0.35ms. Aggregate pool-read median/p95 fell from
12.15/15.43ms to 10.47/12.17ms.

### AUD-015 — Retained auditors misclassify deadline holds and schema evolution

Status: **VALIDATED-PHYSICAL**

**Observed:** the issue audit reported 104
`selected_action_guard_mismatch` violations. All 104 rows first selected the
fresh-recertified guard action correctly, then legitimately suppressed the
expired write and emitted the observed held command with the
`+deadline_hold` suffix. Separately, the corridor-priority audit aborted at
controller-config line 2 after the main and ordinary worker priority fields
were split.

**Fixed and replayed:** the issue audit now verifies the guard transaction and
post-guard deadline override as separate contracts, including label, mask,
and no-write dispatch. Replaying all 51,411 decisions yields 13,522
recertified transactions, 104 audited deadline holds, zero violations, and
zero Bomb violations. The priority audit treats the absent post-split main
field as an explicit disabled request while validating the distinct ordinary
field; it scans all 9,894 unique solutions instead of crashing.

**Second physical replay:** the post-fix trace initially produced one
`deadline_hold_dispatch_mismatch` at frame 163,552. The retained row proves the
deadline hold preserved movement/focus and a later auto-confirm release changed
only the `SHOT` bit (`0x05 -> 0x04`). The audit now admits only a correctly
labeled `press`/`release` transition whose mask delta is confined to `SHOT`;
movement changes still fail. Replaying all 55,024 decisions yields 14,326
recertified transactions, one audited deadline/auto-confirm overlap, zero
violations, and zero Bomb violations.

### AUD-016 — Wider local beams are slower without a safety signal

Status: **REJECTED**

**Observed offline replay:** on 1,024 baseline roots, widening the local beam
from 24 to 96 raised median/p95 planning time from 17.33/23.83ms to
37.01/58.57ms. In losing/pre-hit contexts the compared hard vector improved
three times and worsened eleven times. The 96-wide reference is a sensitivity
probe, not an oracle, but it supplies no evidence for promotion and would
increase the already-observed action lag. More VPS CPU is therefore not used
to widen this serial beam in the post-fix run.

### AUD-017 — Player and laser lethal geometry matches authoritative source

Status: **RETRACTED; SUPERSEDED BY AUD-025 AND AUD-027**

The source facts in the original cross-check were incomplete rather than
false: Sakuya/Remilia use one-unit lethal half-extents, and
`th08_laser_model.py` reproduces the native laser lifecycle and local-space
rectangle helper. The audit failed to follow those values through the live
consumer. `scripts/th08_live/movement.py` and
`scripts/th08_laser_runtime.py` both hardcode `PLAYER_RADIUS=2.0`; the live
laser packer then converts the native finite rotated rectangle to a
closest-point capsule. The complete live collision path therefore does not
match the source. The old conclusion that no correction was justified has no
authority.

### AUD-018 — Authority-only/item-skip full route records 58 hits

Status: **VALIDATED-PHYSICAL**

**Observed physical:** run
`lunatic_route2_fullrun_unattended_20260823_183138` completed Route 2 through
Final-B at manager frame 233,818, issued 55,024 decisions, recorded 58 native
hit edges, and passed the hard no-Bomb gate. Stage hit counts were
`4/6/5/13/9/21`; versus the same-day baseline the deltas were
`+3/-2/-9/-1/-9/-9`, totaling `-27` (31.8% fewer). Exact witnesses classify
17 bullet overlaps, two laser overlaps, zero enemy-body contacts, and 39
modeled committed-prefix collisions. Spell 170's baseline nine-hit cluster
fell to four hits in the post-fix route.

The trace terminated with the exact Final-B `terminal_unload` record and
`route_complete`; the dedicated Wine prefix had no leftover processes. Four
unrelated TH105 Wine workers on displays `:120..:123` remained outside the
TH08 prefix/display/cleanup scope.

**Interpretation limit:** this is a strong physical result, not a controlled
RNG/seed experiment. The two promoted changes had no intended policy authority
in either run: global guidance was already stripped before action selection,
and item objectives were disabled. Their measured effect is reduced compute
and latency. The 27-hit improvement is consistent with better cadence, but a
single run cannot assign the whole delta causally to either optimization or to
VPS compute capacity.

### AUD-019 — Full-route comparison assumes solver percentiles always exist

Status: **FIXED-OFFLINE**

**Observed physical trigger:** gameplay for `...183138` completed and its
dossier was generated, but postprocessing raised `TypeError: 'NoneType' object
is not subscriptable`. The authority-only run correctly represented absent
global-solver `solve_ms` and first-age distributions as `null`; the comparator
unconditionally indexed them. The host runner therefore returned 78 even
though the retained trace and Windows session had already accepted
`route_complete`. Exact-prefix cleanup still reported leftovers `[]`.

**Fixed and replayed:** percentile comparison now preserves each missing side
as `baseline/candidate/delta`, with `delta=null`, rather than fabricating a
zero or crashing. The real 85-hit and 58-hit dossiers now generate the compact
comparison successfully, and the pending session was recovered to
`status=completed` while retaining the original exception in an explicit
`artifact_recovery` record.

### AUD-020 — Local enemy-prefix reads allocate and copy twice per decision

Status: **VALIDATED-PHYSICAL**

**Observed:** local planning and fresh issue recertification each read the
64-slot enemy prefix through `ProcessReader.read()`. At stride `0x53D0`, each
read is 1,373,184 bytes. That API creates and zeroes a new ctypes destination,
performs `ReadProcessMemory`, and copies the full destination through
`buffer.raw`. The 58-hit reference made 55,024 decisions, so these two call
sites account for about 151 GB of repeatedly allocated destination bytes plus
about 151 GB of redundant Python byte copies. Retained decisions commonly
record each prefix capture near 3 ms.

**Fixed offline:** the controller now allocates one exact-size destination and
uses `read_into` for both sequential main-thread captures. Enemy bodies and
optional ECL/combat inventories are decoded before the destination can be
overwritten; no mutable view escapes in `EnemyPoolSnapshot`. Buffer size and
writability fail closed, the manager-frame brackets and retry order are
unchanged, and callers without a destination retain the old compatibility
path. `controller_config.enemy_prefix_sensor` records physical activation.

**Verification:** immutable-snapshot parity, two-read destination identity,
frame/read ordering, mode-capture forwarding, and invalid-buffer tests pass.
Affected tests pass 110/110, import smoke passes, and complete Linux discovery
passes 1,353 tests with five skips.

**Physical validation:** full Route-2 run
`lunatic_route2_fullrun_unattended_20260824_022909` recorded the exact
`persistent_read_into` activation marker, completed naturally at frame 224868,
issued zero Bomb inputs, and left no processes in the dedicated Wine prefix.
Against the retained 58-hit reference, planning-prefix median/p95 fell from
2.764/3.317 ms to 1.543/1.929 ms, issue-prefix median/p95 fell from
2.944/5.499 ms to 1.707/2.967 ms, and observe-to-input median fell from
47.590 ms to 45.084 ms. Pool-read medians improved in every stage. Action-lag
median/p95 remained 2/3 frames, so this closes the allocation/copy defect but
does not close the wider Wine-to-input latency problem.

The route recorded 61 hits versus 58 in the different-RNG reference. That
aggregate is observational, not a causal strategy result. Its 48
modeled-committed-prefix collisions and 53 boundary attributions show that the
remaining dominant failures lie after this narrow sensing fix. Compact CSV,
dossier, regression, summary, and rendered-note hit identities were also
cross-checked: all 61 native hit frames are unique and consistent.

### AUD-021 — Player-control root uses thirteen scalar RPM calls per attempt

Status: **VALIDATED-MECHANISM**

**Observed:** the fresh player/control root issued separate RPM calls for
three input fields and x/y position both before and after the scale read, plus
two manager-frame reads and one scale read: thirteen calls for every stable
attempt. This root runs once per decision and can retry once. The duplication
is required because input and player motion may advance while the manager
clock is frozen; only the scalar call granularity is redundant.

**Source evidence:** the authoritative global map places the consumed `u16`
inputs at `0x164D528`, `0x164D52C`, and `0x164D534`, inside one exact 14-byte
span. `Player.hpp` asserts the `Float3 position` member at `Player + 0x2B4`, so
its consumed x/y prefix is one exact eight-byte span. The distant manager
frame, time scale, and player spans are not merged.

**Fixed offline:** each input triplet is decoded from one 14-byte read and
each x/y pair from one eight-byte read. The exact order remains `frame /
input-before / position-before / scale / position-after / input-after /
frame`; all duplicate comparisons, scale bits, two-attempt behavior, and
unstable-root rejection are unchanged. A stable attempt now uses seven RPM
calls instead of thirteen. At 55,915 decisions this removes at least 335,490
RPM calls per full route.

**Verification:** exact offsets and order, stable values, frozen-clock input
and position changes, later coherent retry, and 14/8-byte short-read rejection
are covered. The trace exposes `read_player_control_root`, and controller
config records physical activation. Focused trace/dossier tests pass 17/17,
import smoke passes, and complete Linux discovery passes 1,358 tests with five
skips.

**Physical validation:** full Route-2 run
`lunatic_route2_fullrun_unattended_20260824_034510` recorded the exact
seven-call activation marker, completed naturally at frame 229967, issued
zero Bomb inputs, and left no process in the dedicated prefix. Stage read
medians improved by 0.720--1.204 ms in all six stages versus OPT-001; Stage 4A
fell from 9.840 to 8.676 ms and its player-root median/p95 was 0.275/0.368 ms.
Action-lag median/p95/max remained 2/3/5. Complete-route unstable-root events
fell from 15 to two, with no retry in a causal pre-hit window.

The route recorded 67 hits and stage counts `0/4/5/21/10/27`. This does not
establish a hit improvement over the different-RNG 61-hit reference. The
Stage 4A increase exposed the separate AUD-022 delay feedback defect, but no
evidence falsifies the coalesced source layout or capture semantics. The
mechanism is retained and its hit outcome is not promoted.

### AUD-022 — A deadline hold cannot teach the delay estimator that its support expired

Status: **FIXED-OFFLINE; PHYSICAL GATE PENDING**

**Observed physical:** after the Stage 4A scene reset in run `...034510`,
empty-scene samples narrowed `AdaptiveControlDelay` from its default `[2,3]`
support to `[1,2]` at frame 72547 and `[1]` at frame 72648. When the local
planner became expensive, frame 72949 reached action lag two outside `[1]`.
The deadline guard correctly retained the old action, but frames 72949--73042
then repeated that hold for 32 consecutive decisions. The player remained at
`(192,384)`, the estimator stayed at 49 end-to-end samples with zero overruns
and zero censored samples, and its guard remained false until the native hit
at 73042. Only `register_hit()` widened support at frame 73047.

**Root cause:** once any end-to-end samples exist, `estimate()` ignores the
newer computation-lag tail. A missed issue deadline does not register an
overrun or activate the estimator guard. The held old mask normally requires
no write, so it cannot create a later visible-input observation. This is a
closed feedback loop: underestimated support causes a no-write hold, and the
no-write hold prevents the evidence needed to correct underestimated support.

OPT-001 had no exact-`[1]` support decisions in any stage. OPT-002 produced
361 in Stage 2, 80 in Stage 3, and 331 in Stage 4A. The faster coalesced read
made legitimate one-frame low-load samples possible; it did not corrupt the
captured fields. Stage 4A alone combined the narrowed estimate, sustained
two-frame planning, and a lethal wave, making the defect directly causal for
the first hit.

**Required fix boundary:** a currently observed deadline miss must widen or
guard the *next* delay estimate even when no input is issued. The expired
proposal must remain held; the fix may not retroactively issue an action that
was planned for the wrong epoch. A regression must reproduce low-load `[1]`,
a later two-frame deadline, a no-write hold, immediate next-estimate widening,
and eventual recovery without requiring a hit.

**Fixed offline:** the current expired proposal is still held. Its proven
snapshot-to-issue lag now establishes a temporary next-estimate support floor,
plus the existing default pickup frame, under the existing 600-frame guard.
This is stored separately from visible-input samples and actuation overruns,
expires independently, respects the configured maximum, and clears on reset.
The controller config identifies
`th08-control-delay-deadline-feedback-v1`; decisions expose cumulative
`deadline_misses` for physical verification.

The retained failure is reproduced without Wine: twelve one-frame end-to-end
samples narrow support to `[1]`; registering the observed two-frame late issue
writes no input but makes the next support `[1,2,3]`. Expiry returns to `[1]`
and reset returns to the default `[2,3]`. Focused estimator, trace, iteration,
and issue-stage tests pass 18/18; complete Linux discovery passes 1,361 tests
with five skips, and import smoke passes. A full route must now show that
Stage 4A no longer repeats the frame-72949-style hold streak.

### AUD-023 — Hit-row hazard attribution can be later than the lethal collision

Status: **FIXED-OFFLINE**

**Observed physical:** Stage 4A frame 104767 in run `...034510` is reported as
`sensor_gap_or_unmodeled_hazard` because the phase-2 detection row has positive
pipeline clearance and no same-row bullet overlap. The last alive decision at
104764 already reports robust minimum clearance `-1.662` and
`worst_collisions=1` for the selected `right` action. The hit row's bullet
pool was captured at frames 104765--104766, player phase was observed at issue
frame 104767, and the stable post-detection contact capture occurred at 104768.
The collision can therefore precede the row used for primary attribution and
move clear before detection.

**Root cause:** `_classify_death` gives a positive hit-row pipeline clearance
precedence over the causal last-alive robust certificate. The ledger separately
and correctly classifies the planner failure as
`robust_action_set_exhausted_before_hit`, leaving its primary cause and planner
cause internally inconsistent.

**Required fix boundary:** exact same-epoch observed overlaps remain strongest.
When they are absent but the last alive selected-action robust certificate is
already unsafe, retain explicit evidence under the modeled committed/selected-
prefix collision class rather than an unknown-sensor class. Preserve
`sensor_gap_or_unmodeled_hazard` when
both the exact contact evidence and the causal model remain positive.

**Fixed and replayed:** the classifier now checks the causal last-alive
selected-action certificate after all exact same-epoch overlap classes but
before declaring an unknown hazard. The regression corpus retains whether the
unsafe evidence came from the hit-row pipeline, the last-alive certificate,
or both. Focused dossier tests pass 22/22. Replaying the untouched 2.046 GB
raw trace reclassified only frame 104767, changing the route taxonomy from
42 modeled / 24 bullet / one sensor gap to 43 modeled / 24 bullet / zero
sensor gaps. All 67 native hit frames, stage counts, spell attribution, and
no-Bomb evidence remain unchanged, and the regenerated regression corpus
passes its validator.

### AUD-024 — Native rank feedback is action-relevant but absent from retained traces

Status: **OPEN**

**Source evidence:** `GameManager.cpp` gives Lunatic difficulty index 3 rank
parameters `8/8/12` for initial/min/max rank. `Player.cpp` calls
`DecreaseSubrank(1600)` on death and either clears Power at 16 or below or
subtracts 16. `Player::FUN_00450f60` selects shot tables by current Power.
`EclDependencies.cpp` rank-scales bullet count and speed when no spell card is
active; spell-card emissions skip this rank scaling.

**Analysis consequence:** a hit changes later player damage and nonspell
patterns, so per-stage hit counts after the first divergent death are not
independent samples. Run `...034510` entered Stage 4A at Power 11 and its
AUD-022 hit immediately reset Power to zero; OPT-001 entered at Power 31 and
did not hit until much later. The traces retain Power but not `rank` or
`subRank`, so the exact native rank trajectory is unrecoverable after process
exit. Add source-checked, trace-only rank/subrank telemetry before making
rank-conditioned causal claims or changing action policy from it.

### AUD-025 — Live player lethal half-extents are inflated from 1px to 2px

Status: **PARTIALLY FIXED LIVE — LOCAL BULLET/BODY; LASER/GLOBAL PENDING**

**Source evidence:** `Player.cpp` initializes the lethal vector at `+0x3D4`
from the SHT width divided by two, updates its cached AABB after movement, and
uses that AABB in `Player::FUN_0044a230`. The matching ledger marks the latter
function 100% exact.

**Physical evidence:** all 60 stable OPT-002A hit-contact captures reconstruct
half-extents `(1,1)`; 58 are exact and two differ only by float subtraction
roundoff. The live solver instead imports `PLAYER_RADIUS=2.0` into local,
native-packed, semantic generation/shrink, controller safety, laser, and
enemy-body checks. This is duplicated conservatism because delay uncertainty
is modeled separately. Add a versioned runtime half-extent and shadow action-
set differential before promoting the correction.

GEO-001A now retains the cached AABB and `+0x3D4` half-extents in the same
bracketed control-root reads and emits their validity/cache coherence as
shadow-only trace data. It deliberately does not replace `PLAYER_RADIUS=2.0`;
the identical-root action-set differential remains the promotion gate.

GEO-001B's integer-pixel root-2129 differential removes 13,040 of the 32,893
legacy collision positions by correcting player extent alone, with zero
reverse additions on that bullet-only root. All 18 H=1 root-cohort actions
remain safe, while their minimum clearance increases by 1.0–1.414px. This is
a large geometry/risk-field error but not evidence of a safe-set or hit-count
change on every root.

The first authority promotion now gives the NumPy and native local
bullet/enemy-body kernels explicit Route-2 lethal half-extents `(1,1)` while
leaving the independent laser capsule and global corridor `PLAYER_RADIUS=2.0`
paths unchanged.  This split is intentional: replacing the laser capsule with
radius 1 would under-approximate a rotated 1x1 player AABB at diagonal angles.
The route dossier records semantics
`th08-live-local-v2-source-binary32-aabb-player1-state5-only`; a complete
isolated route is the next behavior gate.

### AUD-026 — Nonlethal bullet lifecycle states are included as lethal hazards

Status: **PARTIALLY FIXED LIVE — STATE 5 ONLY; FUTURE ANM/CALLBACK OPEN**

**Source evidence:** `BulletManager::OnUpdate` reaches
`Player::FUN_0044a230` only in native state 1, and skips that collision block
when callback aux byte `+0x10B4` is nonzero. States 2/3/4 perform spawn
animation/motion without a lethal player call; state 5 cancels/despawns.

**Solver divergence:** `planning_bullet_active_slots()` selects every nonzero
state. The decoder already retains native state, state timer, and callback aux
state, but the local hazard builder only special-cases state 2 motion and does
not filter collision eligibility. Compact nearby-bullet records omitted these
fields, so the current 60-hit trace cannot quantify the error. Retain them and
shadow-classify false hazards before changing authority.

GEO-001A now emits vectorized source-lethal versus legacy-candidate counts and
retains exceptional state/timer/callback-aux records in nearby-bullet traces.
The old 60-hit trace remains lifecycle-incomplete; a new Wine capture and the
same-root exact classifier are still required.

The old root retains 28 state-2 bullets; excluding only those source-proven
nonlethal states removes 351 additional collision-grid positions. Because the
v2 root omitted callback aux, state-1 records are conservatively kept lethal;
the result is a lower bound, not complete lifecycle impact. Future native
snapshot ledgers and live nearby-bullet traces now retain callback aux.

Re-reading the authoritative `BulletManager::OnUpdate` control flow closes an
important promotion trap: states 2, 3, and 4 all jump through
`activateBullet` to state 1 when their respective ANM VM completes.  State 1
with nonzero callback aux can likewise become lethal after callback state
changes.  Filtering those values over a 10–32-frame planner horizon without
executing the ANM/callback roots would be an unsafe false negative.  State 5,
by contrast, only advances its removal animation and deallocates; it cannot
reactivate.  Live local planning therefore filters only state 5 and retains
states 2/3/4 plus callback-suppressed state 1 conservatively until their future
steppers exist.

### AUD-027 — Live laser collision is a capsule, not the native rotated rectangle

Status: **CONFIRMED-SOURCE; SHADOW IMPACT PENDING**

**Source evidence:** `Player::CalcLaserHitbox` rotates the player center into
laser-local coordinates and performs inclusive AABB overlap against the
finite laser rectangle. **Solver divergence:** `pack_laser_frame()` lowers the
same lifecycle geometry to a centerline segment with
`half_width + PLAYER_RADIUS`; local/native consumers use Euclidean
closest-point capsule distance. End caps/corners differ and the player
half-size is inflated. Only two OPT-002A hits have a primary laser-contact
label, so this is confirmed geometry debt but not the dominant recorded hit
class.

The repository already contained a source-shaped `LaserCollisionBox` and
`laser_overlaps_player()` lifecycle model; the divergence occurs when live
packing lowers its effective rectangle to a capsule. GEO-001B retains exact
rectangle width/orientation alongside the unchanged seven-field capsule ABI
and tests a vectorized shadow predicate against the scalar source predicate.
Root 2129 has no lasers, so physical impact remains unquantified.

### AUD-028 — All OPT-002A global corridor submissions were authority-blocked

Status: **VALIDATED-PHYSICAL**

**Observed physical:** all 57,553 decisions had a numerically sufficient
time-scale horizon and a due corridor submission, but provenance remained
`experimental_pretarget_unit_transport_unknown_direction`, hard scale
authority was false, `authority_blocked_submission=true`, and
`submitted_this_decision=false`. The compact dossier records zero submitted
solutions, queries, available queries, viable queries, policy decisions, and
constrained decisions. Counts by stage are exactly
`5389/7217/7621/11487/10046/15793`.

**Consequence:** the VPS's four native corridor workers did no strategic work.
More CPU affected sensing/local cadence only. This is stricter than saying the
global planner was slow: it was never invoked.

### AUD-029 — Future-birth prototypes are unintegrated and spell authority lacks a coverage gate

Status: **CONFIRMED-ARCHITECTURE; FIX REQUIRED BEFORE GLOBAL PROMOTION**

`analyze_ecl_birth_intents()` explicitly classifies one literal main-VM path
without geometry, is referenced only by its tests, and stops at common timer,
control-flow, topology, emission-state, and callback behavior.
`ECL_BIRTH_LOOKAHEAD_FRAMES=80` has no consumer. The large ordinary-source
closure is disabled and rejects active spells.

More seriously, if hard scale authority were supplied, normal active-spell
corridor submission can proceed with `future_hazard_projection=None`; the
hard action gate checks scale authority but not complete future hostile-birth
coverage. Do not fix AUD-028 by flipping a provenance/config flag. Add a
source-complete producer projection and make its exact version/coverage part
of the hard action certificate. The complete architecture and staged plan are
tracked in `TH08_SOURCE_AUTHORITATIVE_SOLVER_AUDIT.md`.

### AUD-030 — Direct-fire fan parity and automatic player aim diverge from source

Status: **FIXED-OFFLINE; NOT YET LIVE ACTION AUTHORITY**

`BulletManager::FUN_0042f5f0` uses `descriptor->count1 & 1` to center fan
modes 0 and 1.  The future-birth envelope instead uses instruction flags.  A
58,752-case deterministic sweep over modes, indices, counts, and flags found
9,792 angle disagreements, confined to fan modes 0/1.  Of 83 statically
decoded Route-2 fan sites with literal count1, 42 have count/flag parity
disagreement; of the 45 fully literal sites, 22 are affected.

The same source function automatically adds `angleToPlayer` in modes 0, 2,
and 4.  The pre-fix ordinary source builder set `aim_angle=0.0` for every
event, and causal future conditioning consequently preserved a false zero
rather than recomputing aim from each candidate player path.  The versioned
spawn-semantics change is gated with an independent source transcription,
decoded-ECL atlas differential, and 1,536-bullet density stress.
Do not alter the signed-low-word count decoder: `BulletSpawnDescriptor`
stores count1/count2 as signed 16-bit fields, so that behavior is correct.

The versioned fix now uses count1 parity, computes native mode aim from the
descriptor origin (`enemy position + emission offset`), recomputes that
independent dependency for each causal player path, and uses the source
binary32 `ZUN_PI`/`ZUN_2PI` values.  The tracked
`th08_source_spawn_pattern_differential_20260824.json` independently
transcribes deterministic source modes 0..5.  It reproduces 9,792 legacy
failures in 58,752 synthetic samples and records zero corrected failures at a
`2e-6` tolerance; maximum corrected speed/angle errors are
`1.967e-7/8.600e-7`.  Across 64 fully literal deterministic Route-2 sites and
1,643 spawned samples it again records zero failures, with maximum errors
`3.725e-7/4.172e-7`.

The 80-frame pool stress lowers all 1,536 requested births to 1,536 unique,
finite sector envelopes and checks 122,880 active radial samples.  This closes
spawn-pattern math only.  Runtime ECL reachability, rank, RNG modes 6..8,
transforms, lifecycle, and live strategy remain outside its authority.

### AUD-031 — GEO-001B complete route exposes material Stage-5 false hazards

Status: **VALIDATED-PHYSICAL SHADOW; NO ACTION AUTHORITY**

Run `lunatic_route2_fullrun_unattended_20260824_074407` at exact clean commit
`8b1c3de4de4f5c776644aaebab68e18d649eba2b` naturally completed Sakuya/Remilia
Lunatic Final B at frame 226632 with 57 hits and stage counts
`3/7/4/15/10/18`.  It passed hard no-Bomb across 56,539 decisions and left no
process in its isolated Wine prefix.  Stage 4A remained exactly 15 hits versus
the 60-hit source-audit baseline, while its read/plan p95 improved from
`11.543/50.844 ms` to `10.370/49.044 ms`; there is no Stage-4 regression to
attribute to the shadow instrumentation.

The streamed lifecycle ledger covers 21,394,298 bullet-by-decision
observations.  The legacy selector included 2,689,327 source-nonlethal
observations (12.5703%).  Stage 5 contributed 1,125,175 of 4,973,810
(22.6220%), including 840,965 state-1 observations on 1,120 decision frames
whose callback aux byte suppressed collision.  Stage 4A was 11.4902% and had
no callback suppression.  These counts establish a large Stage-5 modeling
error, but do not establish which actions or hits would change after
promotion: the shadow never influenced input and route-wide geometry was not
retained outside the 160-pixel trace radius.

The same route recorded native state totals `1:19,545,936`, `2:1,345,200`,
`3:25,034`, `4:93,130`, `5:384,998`, plus 393,216 laser observations.  Future
activation of states 2/3/4 depends on ANM-script completion, and callback aux
can be toggled by the exact `ReisenFreezeBullets`/`FUN_00424c40` ECL paths.
Only current-frame eligibility is ready for exact promotion without retaining
and stepping those additional roots.

### AUD-032 — Collision booleans require binary32 storage and inclusive bounds

Status: **FIXED LIVE FOR LOCAL BULLET/BODY AABB; LASER SEPARATE**

The source player-bullet predicate compares inclusive Float3 AABB bounds.
The pre-v2 shadow topology computes a symmetric double-precision clearance,
which is mathematically similar but not executable-bit-exact at touching
edges.  An edge-focused two-million-case diagnostic found 135,386 boolean
disagreements (134,938 current-false/source-true and 448 in the reverse
direction).  This deliberately adversarial rate is not a live-route estimate;
it proves the authority kernel needs explicit binary32 stores and inclusive
comparisons.  Laser collision has the additional `sinf`/`cosf` and rotated-
Float3 boundary, so it must receive a separate oracle rather than inherit the
bullet result.

The source kernel is now versioned as
`th08-source-collision-v2-binary32-inclusive-aabb`.  It explicitly stores
player and hazard min/max bounds as binary32, applies the source separated-
axis comparisons, and aligns the sign of the continuous risk clearance with
that exact boolean.  The tracked independent report
`th08_source_aabb_binary32_differential_20260824.json` runs two million
edge-focused cases: the former double-center predicate disagrees 192,845
times, while the corrected scalar/vector kernel has zero oracle mismatches.
The rate is deliberately adversarial and is not a live-route estimate.

A separate full-pool stress compares 1,536 bullets against 4,096 player
positions (6,291,456 pairs), including 657 source-lifecycle-eligible bullets.
The corrected pair mask has zero oracle mismatches and the integrated
lifecycle-filtered collision count has zero mismatching positions.  Laser
rotation remains outside this result and retains its own pending `sinf`/`cosf`
oracle.

Regenerating the retained root-2129 differential under v2 leaves its
one-pixel grid counts and all 18 one-step safe actions unchanged.  Binary32
correctness closes an authority defect at exact edges; it does not manufacture
a route-level behavior effect where the retained root has no such edge case.

The same stored-bound predicate and sign alignment are now present in both
live NumPy and native C++ local kernels.  The promotion gate
`th08_live_source_aabb_promotion_differential_20260824.json` evaluates the
complete 1,536-slot bullet capacity against 4,096 adversarial candidate
positions (6,291,456 pairs).  Native and NumPy each match the independently
transcribed source collision counts at all positions.  The workload exercises
2,232 positions changed by the former radius-2 geometry, 1,401 positions
changed by state-5 removal, and 3,149 positions changed by their combination.
Native evaluation takes 60.51ms versus 155.44ms for NumPy on this deliberately
oversized one-call stress; these are a parity/throughput gate, not route-frame
latency estimates.

### AUD-033 — Player cancel regions precede the lethal AABB call

Status: **CONFIRMED-SOURCE; FUTURE ROOT/STEPPER MISSING**

`Player::FUN_0044a230` first calls the separately 100%-matching
`Player::FUN_00449ff0` over 192 `playerSlotsC` cancel regions.  A region hit
returns collision result 2 without calling `Player::Die`; the bullet update
then normally moves that bullet to state 5, except for its explicit transform-
flag exception.  These regions are created not only by Bomb code, but also by
the post-hit player-state cooldown and enemy-death/time-orb paths.  Hard
no-Bomb therefore does not prove that the region pool is always empty.

The current-frame lifecycle shadow observes the resulting bullet state after
native update and remains valid.  A future bullet stepper that ignores active
and future cancel regions can nonetheless preserve bullets that native code
would remove, especially after damage-dependent enemy deaths or a modeled
hit branch.  Retain the region pool and reached creation sources before
granting multi-frame current-entity or future-birth action authority.

### AUD-034 — The first live source promotion must remain a conservative subset

Status: **IMPLEMENTED-AND-DIFFERENTIAL-GATED; ROUTE RESULT PENDING**

The smallest source-backed behavior change is not the full shadow predicate.
The live local kernel now combines exact `(1,1)` player bullet/body AABBs,
binary32 stored bounds, inclusive comparisons, and irreversible state-5
removal.  It deliberately retains future-activating states 2/3/4, unknown
callback-aux transitions, the radius-2 laser capsule, and all global corridor
geometry.  Thus every removed local bullet hazard is backed either by the
Route-2 SHT/native root or by a lifecycle state that cannot return to lethal
state 1; no removal assumes an unimplemented future ANM/callback transition.

The tracked high-density gate has zero native/source, NumPy/source, and
native/NumPy collision-count mismatches across 6.29 million pairs.  It reports
7,797 promoted collision pairs versus 13,221 under the combined historical
radius-2/all-state predicate.  That difference is intentionally adversarial,
not a hit prediction.  Its canonical JSON SHA-256 is
`e6423338e7cee9feb426ac83e77ef98d1fd42c9afa16a34c02077a3f393b7c6a`.
A complete isolated Lunatic Route-2 run is required to
measure the actual stage/contact effect and to reject any latency or policy
regression.

### AUD-035 — Radius-2 geometry was hiding a retained hit-timing false negative

Status: **CONFIRMED-REGRESSION-FIXTURE; TIMING ROOT CAUSE OPEN**

The retained CE frame-3254 fixture was captured before a physical contact with
bullet slot 1136.  Under the historical radius-2 player geometry, its
three-frame control-delay projection was negative and requested a Bomb.  The
source-correct `(1,1)` player AABB instead selects `up_fast` with zero modeled
collisions and only `+0.2908877px` pipeline clearance.  Source inspection
confirms that `Player::FUN_0044a230` halves the bullet's full size and compares
it with the cached player AABB, so restoring radius 2 would reintroduce a known
geometry error rather than fix the physical discrepancy.

This fixture therefore isolates a second defect that the old inflated box was
masking: capture-epoch alignment, future bullet/player update order, or input
issue latency can still place the physical player inside a bullet that the
linear prefix leaves barely positive.  The regression test now preserves this
positive sub-pixel discrepancy explicitly.  Do not interpret the geometry
promotion as a complete safety proof; compare sub-pixel-positive hit precursors
and timing windows in the next route, then repair the timing/root projection
rather than padding all bullets by one pixel.

### AUD-036 — The first source-AABB route regressed from 57 to 93 hits

Status: **VALIDATED-PHYSICAL; CORRECT GEOMETRY RETAINED, POLICY PROMOTION REJECTED**

Run `lunatic_route2_fullrun_unattended_20260824_094658` completed the exact
Sakuya/Remilia Lunatic Route-2 target at manager frame 228477 with 50,669
decisions and 93 native hit edges.  Hard no-Bomb and isolated-prefix cleanup
passed.  Stage hits were `4/7/5/20/31/26`, compared with
`3/7/4/15/10/18` in the 57-hit GEO-001B shadow route.  Stage 5 is the dominant
regression, not Stage 4A.

The route-wide source ledger observed the stable native player half-extents
`(1,1)` on every decision.  Across 17,333,626 decoded nonzero bullet-state
observations, 2,296,938 (13.2513%) were legacy-only lifecycle candidates;
state 5 was the only irreversible class removed from live collision.  The
high-density binary32 differential remains exact.  Therefore the physical
geometry correction is retained; reverting to radius 2 would restore a proven
engine mismatch.  What is rejected is the claim that geometry promotion by
itself is a safe survival optimization.

### AUD-037 — Bullet-pool capture span is trace-only, but not the main regression

Status: **CONFIRMED-MODEL-GAP; SECONDARY IN THIS ROUTE**

`HazardEpochAlignment` records the manager frame before and after the bulk
bullet-pool read, but `bullet_capture_span` has no planning consumer.  A read
that crosses a frame can therefore contain records from different update
epochs while every bullet center is treated as the final epoch.  The packed
bullet path, used at high density, also has no per-axis trajectory-uncertainty
arrays.

The new streamed timing audit prevents this real defect from becoming a
catch-all explanation.  Only 2,429 of 50,669 decisions (4.7939%) crossed one
manager frame.  Eight of 93 hit rows did so; 30 of 93 four-decision hit windows
contained any crossing.  A conservative axis envelope
`abs(velocity_axis) * capture_span` changes a source-safe current overlap in
only one retained hit window.  Capture-epoch interval containment should be
implemented and fuzzed, but it cannot explain most of the 36 additional hits.

### AUD-038 — Stage-5 latency escaped the configured delay support

Status: **CONFIRMED-PHYSICAL ROOT CAUSE**

The 57-hit route's hit-row action lag had median/p95 `2/4` frames and no death
occurred beyond the modeled delay support.  The 93-hit route rose to `4/9`
overall; its Stage-5 hit rows rose from `2/4` to `7/10`.  Hit-row
observe-to-input median rose from 86.80ms to 125.43ms overall and from 87.98ms
to 160.75ms in Stage 5.  Twenty-three route hits, including sixteen of the 31
Stage-5 hits, missed the configured upper delay at the hit row.

Timing decomposition locates the cost in repeated geometry certificates, not
pool decoding.  Stage-5 initial-plan median/p95 changed from `29.93/44.92ms`
to `39.89/73.52ms`; hit-row issue recertification changed from
`6.29/13.00ms` to `28.74/51.28ms`.  The resulting hit-row total plan median is
97.45ms.  A fixed synthetic native geometry benchmark attributes only about a
6.6% beam-workload median increase to the exact AABB kernel itself.  The much
larger physical regression is therefore a route/workload and repeated-
certificate feedback: late local avoidance changes the root, hits lower
power, and later dense phases keep the issue path outside its own delay model.

The correction must bound local/recertification work and represent any
remaining realized delay; simply widening the delay set can increase compute
again and is not accepted without a latency gate.

### AUD-039 — Full-route runtime ECL identity was attempted once against the wrong stage

Status: **CONFIRMED-IMPLEMENTATION BUG**

The full-route host supplied only `ecldata7.ecl`.  At Stage-1 decision frame 1,
the one-shot identity service compared its 67,324-byte Final-B image
(`20b35d...`) with the 45,844-byte runtime Stage-1 image (`6b44a0...`) and
reported `byte_mismatch`.  It never retried on stages `(1,2,3,5,7)`.  In
addition, `NO_SCALE_WRITER_STAGE_ROUTE_INDICES = range(5)` excluded the real
Stage-5 index 5.  Runtime index 4 is a valid no-writer Stage-4B route/Practice-
Start image, but is not part of the Sakuya/Remilia Route-2 sequence.  Static no-writer
audits are complete for `ecldata1/2/3/4a/4b/5`; Final A and Final B remain
dynamic because their decoded programs reach callback 18.

The fix is a route-wide stage dispatcher over runtime indices
`(0,1,2,3,5,7)`, with a pinned static identity and independently versioned
scale authority per stage.  Final-B dynamic authority must not contaminate
the five earlier no-writer stages.

### AUD-040 — Global delivery needs future-birth and solution-version gates

Status: **CONFIRMED-HIDDEN AUTHORITY BUG; ZERO-JOB ROOT LOCATED**

All 50,669 decisions had a due global submission and a numerically sufficient
scale horizon, but hard scale authority was false, so submissions, completions,
queries, and publications were all zero.  Every local pipeline root also
reported future hazard coverage `model_unknown` beginning at the next frame.

The submission gate currently treats hard time-scale authority as sufficient
for active-spell action authority when the optional ordinary future projection
is absent.  A published solution stores `time_scale_identity`, but consumption
does not require it to equal the current schedule version.  Unblocking only
the scale gate could therefore make current-entity-only spell forecasts hard.
Every result must instead carry and match root, scale, future-birth, geometry,
and policy versions; incomplete future coverage may submit and solve in
shadow, but may not constrain action.  Background workers must also run below
the latency-sensitive Wine sensing/issue path.

### AUD-041 — Fresh-enemy recertification recomputed 17 independent actions unnecessarily

Status: **CONFIRMED-ROUTE-WORK ROOT; EXACT LAZY MECHANISM VALIDATED PHYSICALLY;
COMPLETE ROUTE PENDING**

The streamed audit
`lunatic_route2_fullrun_unattended_20260824_094658.issue_recertification_audit.json`
reprocessed the complete 1.902GB retained trace.  Fresh enemy geometry changed
on 12,499 of 50,669 decisions.  On 11,957 of those transactions (95.6637%),
the planned action's fresh certificate was still collision-free and the full
transaction preserved it.  Nevertheless, the old issue path always projected
and certified all 17 actions.  Those changed transactions alone accumulated
166.499 seconds of recertification work; this work ran on the latency-sensitive
controller thread before input publication.

The exact optimization is action-lazy, not geometry-lazy.  It first computes
the same robust certificate for the planned action and, when applicable, the
preferred action.  If the existing selection order can terminate on one of
those freshly safe actions, it commits immediately.  If neither is safe and
eligible, it recomputes the complete historical 17-action batch and executes
the historical full selection unchanged.  Action branches in the certificate kernel are
independent; no uncomputed action is inferred safe, and partial safe/intersection
sets are explicitly marked `fresh_action_set_complete=false`.  The post-issue
shadow also refuses a complete set comparison for such a subset.

The deterministic 1,200-bullet dense-safe differential retained in
`artifacts/benchmarks/th08_lazy_issue_recertification_dense1200_20260824.json`
requires the full and lazy selected certificates to compare equal.  Across 30
repeats, median issue certification fell from 30.339ms for 17 actions to
2.306ms for one action (13.16x), with an identical selected certificate on
that workload.  This is performance/mechanism evidence, not a hit claim.

The accepted isolated Stage-5 Practice gate
`lunatic_route2_stage5_unattended_20260824_115819` then completed all 45,254
frames with 7,792 decisions, 28 hit edges, and zero Bomb input. Of 2,995
changed-prefix transactions, 2,644 (88.28%) terminated on the exact lazy
proof. Their median/p95 recertification was `3.970/6.992ms` with median three
native pipeline branches. The 351 exact full fallbacks instead took
`62.454/76.416ms` with median 81 branches. Thus the physical mechanism is
real, but the aggregate p95 remains outside the desired issue budget. The
28-hit total is observational because Practice uses full Power, a diagnostic
root-only scale proxy, and a different RNG root. A complete isolated route is
still required for the survival disposition.

### AUD-042 — The prepared Wine score does not unlock arbitrary Practice stages

Status: **CONFIRMED BOOTSTRAP FAILURE; SOURCE-BOUNDED FIX OFFLINE-VALIDATED;
PHYSICAL RETRY PENDING**

- **Observed:** isolated Wine attempt `lunatic_route2_stage5_unattended_20260824_114355`
  reached the interactive Practice stage menu with exact EXE/patch, Lunatic,
  Route 2, and Sakuya/Remilia, but read availability `0x0001` and failed before
  gameplay. Cleanup left no exact-prefix process. The failed session is
  retained separately.
- **Source authority:** `TitleScreen::OnUpdatePracticeStageSelect` reads
  `Clrd::difficultiesClearedWithRetries` for the selected shot/team and
  configured difficulty; it makes only Stage 1 available when the value is
  zero. A filename or archive label cannot establish these per-selection
  bits.
- **Correction boundary:** Wine Practice explicitly enables only the requested
  bit after native route/difficulty/menu checks, writes the `u16` data field,
  and immediately rereads the same state. Full route, EXE bytes, Power, lives,
  Bomb stock, and action authority are unchanged. Focused tests pass 47/47;
  physical retry is the falsifier.

### AUD-043 — A local-only Practice gate still needs an explicit scale contract

Status: **STRICT FAIL-CLOSED CONFIRMED; EXACT STAGE-5 FIX OFFLINE-VALIDATED;
FINAL PHYSICAL GATE PENDING**

- **Observed:** `lunatic_route2_stage5_unattended_20260824_115523` proved the
  requested-stage unlock and native menu selection, then ended at frame 1 with
  `time_scale_authority_unknown`, zero decisions, and exact cleanup.
- **Root cause:** the new Wine Practice command supplied neither exact
  per-stage ECL schedule authority nor the existing diagnostic root-only
  continuation. The agent's refusal was correct, not a planner crash.
- **Correction boundary:** the runner now accepts the explicit Practice-only
  `--diagnostic-continue-root-only-scale` flag. Default remains fail-closed;
  the proxy is never represented as exact/global authority. It may gate
  local-planner and issue-time latency only. The raw five-record trace is kept
  ignored with SHA-256
  `c5faf0f1fba9d79e205d5012735f1189a463bcd122cc5b4a2900cd2ec963f50e`.
- **Exact replacement:** Wine Practice now selects a pinned decoded ECL image
  and SHA-256 from the requested native stage, rather than relying on the
  diagnostic proxy. Stage 5 is bound to `ecldata5.ecl` digest `3148f45f...`;
  its complete static callback audit and coherent active-VM inventory publish
  a finite unit schedule. The diagnostic flag remains available only for
  deliberate nonbinding observation.

### AUD-044 — Spell 107 concentrates the remaining exact fallback latency

Status: **CONFIRMED PHYSICAL WORK CONCENTRATION; GENERIC LATENCY ROOT**

The v2 issue audit groups the accepted Stage-5 trace by native spell state and
recorded certificate mode. Spell 107 accounts for 300 of all 351 full
fallbacks (85.47%). Within that spell, only 130/430 changed-prefix
transactions preserve the planned action; the other 300 must execute the
historical complete selection. Those fallbacks consume 18.873 of the run's
20.418 seconds of full-fallback work, at `64.236/76.886ms` median/p95. The
spell also records 12/28 hits, decision-cadence p95 13 frames, and initial-plan
p95 122.495ms. This is not evidence for a hand-authored spell policy: it is a
generic failure mode in which a genuinely unsafe selected action expands one
fresh transaction from a few pipeline branches to 81 and delays the next
observation. The next correction must bound or share the complete exact
fallback and initial beam work without inferring uncomputed actions safe.

The canonical first hit at frame 4,163 is a separate policy counterexample.
It is a source-AABB bullet overlap at the bottom boundary after the robust set
became empty ten frames earlier; global viability was already empty 237 frames
earlier. Its issue lag was four, within configured support, so that first
failure is not a deadline miss. Later spell-107 hits demonstrate the latency
feedback after Power loss, not 27 independent fresh-stock trials.

### AUD-045 — Live background search is thread-parallel, not process-parallel

Status: **CONFIRMED IMPLEMENTATION GAP; PHYSICAL CONTENTION MAGNITUDE PENDING**

`LiveServiceResources` creates the corridor, viability-audit, enemy-sensor,
and future-source services as `ThreadPoolExecutor` workers in the controller's
Win32 Python process; there is no process executor. The VPS therefore cannot
automatically isolate Python portions of global work from the latency-sensitive
local controller, although native/NumPy calls may release the GIL. In the
focused trace the shadow rolling corridor produced 1,787 policies while local
beam time was already 41.901ms on an early row with zero active bullets; this
co-occurrence is a benchmark target, not yet causal proof of GIL contention.
A controlled foreground-only versus thread/process-background latency gate is
required before changing ownership or affinity.

### AUD-046 — Runtime identity and scale inventory were ordered after their own gate

Status: **CONFIRMED CAUSAL IMPLEMENTATION BUG; OFFLINE FIX VALIDATED**

The no-scale-writer authority required an accepted runtime ECL version before
it could publish a complete schedule. The controller, however, performed its
only runtime byte-identity observation after action issue. An exact Stage-5
Practice transaction reached the scale check first, constructed only a
root-observed schedule, and terminated on `time_scale_authority_unknown`; it
could never reach the later identity observation that would unlock the next
transaction. This makes the old order a causal cycle, not a transient Wine
failure.

The same path also passed the FRScreen decision frame as
`expected_manager_frame` to the active-ECL-VM inventory capture. Those clocks
are distinct: a time-scale schedule is rooted at the current player-control
decision frame, while ECL source coherence is bracketed by the stage-local
enemy-manager frame. Comparing either clock against the other's root could
spuriously accept or reject a capture.

The identity read is now action-neutral and occurs at the stable pre-plan root.
The no-writer resolver separately receives and checks the decision frame and
enemy-manager frame. A deterministic Stage-5 integration uses the real
decoded image and pinned digest, injects an exact normalized runtime identity
at decision/manager frames `120/75`, captures the complete VM inventory
specifically at manager frame 75, and publishes a 269-frame complete unit
schedule rooted at decision frame 120 on that same first transaction. All
mismatched stage, digest, root-scale, callback, Bomb, epoch, or either-clock
cases remain fail-closed. This establishes the scale prerequisite only; it
does not grant global action authority without complete future-birth and
solution-version coverage from AUD-040.

### AUD-047 — Spell global authority omitted future births and a complete version join

Status: **CONFIRMED ACTION-AUTHORITY BUG; OFFLINE FIX VALIDATED; PRODUCER
COVERAGE OPEN**

The old consumer initialized `corridor_action_authority` directly from hard
time-scale authority. It added a future-hazard check only for the optional
ordinary nonspell predecessor. Consequently, an active-spell solution could
constrain input after planning only the entities present in its snapshot; no
future-birth projection, ECL identity, geometry version, or policy version was
required. Submission and solution metadata separately carried some of those
facts, but no single immutable object joined them and no consumer checked the
whole join. This is a structural false-authority path, independent of whether
one particular spell happened to collide.

Every solved corridor artifact now retains a content-addressed authority
version over its exact input root, runtime ECL identity, time-scale schedule,
future-hazard version, geometry semantics, and policy/configuration semantics.
The root digest includes player state, current bullets/lasers/contact bodies,
delay support, active action, frames, context, and gate constraint. Pipeline
workspaces include the joined digest in their stale-version key.

The live consumer is now unconditionally fail-closed. It requires the current
runtime ECL identity and stage/epoch context, a semantically compatible
re-rooted hard unit schedule, complete source closure covering the complete
policy horizon, one projection version shared by the artifact, retained
geometry, coverage slabs, and authority join, and matching geometry/policy
versions. A current-entity-only spell job may still run in shadow so producer
coverage can be measured, but it cannot provide a target or allowed action.

The deterministic offline gate proves the positive case and independent
falsifiers: an exact complete join accepts a re-rooted Stage-5-style unit
schedule, while missing future births, a legacy artifact, stale ECL/context,
changed scale provenance, changed projection, changed geometry, or changed
policy config each withholds authority. The affected 40 focused tests pass.
This closes publication correctness, not future-birth coverage or hit
reduction; Stage-5 retained-root producer differentials are next and Wine
remains deferred.

### AUD-048 — Practice runtime identity was pinned to the route ECL image

Status: **RETRACTED 2026-08-25; CONFUSED PRACTICE START WITH SPELL PRACTICE;
CORRECTED BY AUD-060**

This finding interpreted game-manager bit 14 as the ordinary Practice flag.
`GameManager.hpp` names bit 0 `isPracticeMode` and bit 14
`isSpellPractice`. The ECL branch in `EnemyManager::AddedCallback` tests only
bit 14. Ordinary Practice Start therefore loads the same route `*.ecl` image;
`*sp.ecl` belongs to Spell Practice for cards below 205. The exact runtime
identity gate physically falsified the old claim before it could grant scale,
future-source, or action authority.

The retained 28-hit Practice trace also narrows the next producer work. Its
existing callback-12 lookahead was complete for every recorded decision in
spells 103 (647/647), 107 (623/623), and 111 (716/716). Spell 115 was complete
for only 11/732 decisions; 721 stopped fail-closed at unsupported control flow,
consistent with its callback-14 program. Therefore callback-12 sensing is not
the main missing global input for the first three cards. Their remaining
structural omission is future births/child producers; spell 115 additionally
requires callback-14 lowering. These are retained-trace diagnostics, not a
survival or runtime-image-identity acceptance claim.

The follow-up static contract remains valid after relabelling its second image
as Spell Practice. Corrected schema v2 is retained as
`th08_stage5_spell_producer_contract_20260825.json`. It decodes opcode `0x7A`
with the native `enemyFace`/`spellCardNumber` half-word layout, closes literal
call/interrupt/auxiliary/child edges, and normalizes subroutine numbers and
phase-exit targets. All five route Stage-5 spell programs (103, 107, 111, 115,
118) have bit-for-bit-equivalent normalized producer graphs in Spell-Practice
`ecldata5sp.ecl`; the different root and successor indices are packaging, not
pattern differences. The observed four cards contain no dynamic subroutine
target in that static closure.

This proves topology, not reached futures. The exact census shows why a single
direct-fire patch is insufficient: spell 103 has six direct-fire sites;
spell 107 has three direct-fire, three transform, and three child-spawn sites;
spell 111 has three direct-fire sites behind 13 child-spawn sites; and spell
115 has six direct-fire, three transform, two child-spawn, and six immediate
callback-14 sites. Every card also reaches the shared callback-13 visual
auxiliary. Runtime VM locals/control/RNG still select the causal prefix, so the
contract is an offline oracle and coverage denominator only, never action
authority by itself.

### AUD-049 — Active-spell future-source execution was rejected before semantics

Status: **CONFIRMED MODEL/DELIVERY BUG; FIRST FAIL-CLOSED PREFIX VALIDATED
OFFLINE; CALLBACK-TAGGED BIRTHS REMAIN UNKNOWN**

The shared future-source VM previously rejected every snapshot whose compact
root carried a non-null spell ID, before inspecting any reached ECL operation.
The controller duplicated that artificial boundary by neither capturing nor
submitting this source projection during a spell. This was not a
source-derived limitation: spell and nonspell enemies use the same ECL VM and
the same bullet constructor. It guaranteed zero spell producer coverage even
when the reached prefix used only already-lowered semantics.

That metadata rejection is removed. Capture now runs in every stable player
phase when the legacy authority flag is enabled, and the corridor submission
lane requires a complete projection covering its whole policy horizon. The
consumer also compares the captured compact spell ID with the currently
observed spell ID exactly. A result from spell 103 is therefore rejected after
transition to spell 107 or to a nonspell, even if its frame interval would
otherwise overlap. The isolated Practice command now propagates the same flag;
this checkpoint deliberately performs no Wine run.

The first reached Stage-5 root exposed a second, small but definite source
model omission. `EclOperandsFloat.cpp` operand `0x2762` returns
`GetRandomF32InRange(6.2831855f) - 3.1415927f`. It is now represented by the
complete native float32 interval, including the RNG conversion's rounded
endpoint, rather than UNKNOWN or the slightly narrower Python `math.pi`
interval. On a source-exact route spell-103 VM fixture rooted at ECL offset
`0x6420`, the offline executor now proves an exact 80-frame source prefix with
no births. A 139-frame request advances to a complete 90-frame causal prefix
and then stops before future frame 91 on bullet flags `0x104010`; it no longer
stops on dynamic operand 10082. This fixture isolates VM semantics; it is not a
retained physical capture.

That new stop is intentional. The high tag bits cannot be declared inert:
callback 12 later selects and transforms those tagged bullets. No tagged birth
is emitted into action authority until its callback-aware future trajectory is
lowered. The next resumable unit is therefore narrow and source-defined:
model spell-103 tagged future births together with callback 12, then use the
static producer contract to extend the same kernel to child VMs and callback
14. Physical Practice remains withheld until an offline retained root yields
a complete matching policy slab and changes a same-root global viability
result.

### AUD-050 — Callback-12 collision state was omitted and aliased across futures

Status: **CONFIRMED MODEL BUG; FIXED AND DIFFERENTIALLY TESTED OFFLINE**

The source callback-12 path changes both bullet phase/motion and an auxiliary
collision gate. The existing future projection transported the motion change
but kept every selected bullet lethal. Source `BulletManager::OnUpdate` does
not enter the player AABB path while that auxiliary field is nonzero. This was
a systematic false-hazard source for callback-tagged bullets, including the
first currently blocked spell-103 birth family.

The callback model now emits an explicit collision-state transition, and the
live decoder, trace replay, local projection, and corridor projection retain
and apply it. A second error appeared during the correction: projected frames
stored references to one mutable NumPy auxiliary-state array. A later callback
therefore retroactively changed earlier frames. Each frame now owns an
immutable copy. Native piecewise geometry fails over to the exact Python path
when a collision-state transition is present because the current native ABI
has no channel for it; it does not silently drop the gate.

### AUD-051 — Gameplay RNG F32 conversion used the wrong precision order

Status: **CONFIRMED MODEL BUG; ALL 65,536 FIRST-SEED VALUES ENUMERATED; FIXED**

Recovered `Rng::GetRandomF32` converts the generated U32 numerator to
binary32 before division. `Th08Rng.next_unit()` previously performed the
division in Python double precision and rounded only the result. Across every
16-bit starting state, 62,784 of 65,536 first values differed, with maximum
absolute error about $2.98\times10^{-8}$. This is small geometrically but
causally important: random fire modes feed the value into speed and angle and
then accumulate it over long stages.

`next_unit`, `next_signed_unit`, and `next_scaled` now preserve the source
binary32 operation order. A separately compiled C oracle in this repository
checks U16/U32/F32 state and call counts. The oracle is source-level Linux C;
the shipped Win32 executable remains the final x87/libm numeric authority.

### AUD-052 — Pool exhaustion consumed RNG before allocation

Status: **CONFIRMED UPDATE-ORDER BUG; FIXED WITH FULL-POOL CAUSAL TEST**

The first complete-stage runtime evaluated mode-6/7/8 random parameters before
searching for a free bullet slot. Source `BulletManager::FUN_0042f5f0` obtains
the pool object first and stops the nested pattern loops at the first failed
allocation. A saturated pool must therefore suppress the remaining scheduled
tail without consuming its RNG. The wrong order would shift every later
random producer after a pressure event.

Allocation now precedes pattern sampling. The regression fills all 1,536
slots, verifies the exact random-mode call count for allocated bullets, then
submits another random pattern and proves that it changes neither RNG state
nor call count. Metrics distinguish producer-requested births, actual
allocation calls, allocated births, and the schedule tail suppressed by the
pool.

### AUD-053 — Snapshot fuzzing could not preserve legal long transitions

Status: **CONFIRMED INFRASTRUCTURE LIMIT; SOURCE-STATEFUL REPLACEMENT IMPLEMENTED**

The old stateful/snapshot generators could create dense local arrays but did
not make the shared RNG, finite pools, callback selection, queued transforms,
phase clears, laser lifecycle, sensing latency, and input latency one causal
history. They could neither cover realistic long transitions nor distinguish
an engine-model failure from an impossible mutated snapshot.

`th08-source-stateful-stage-v1` replaces that path for source-supported
stress testing. A canonical stage program covers contiguous phases from frame
zero to completion and is content-addressed for exact replay. Seeded profiles
span 480 to 12,000 frames and compose all nine direct-fire modes, parity,
moving resolved origins, callback-12 events, eight transform handlers, lasers,
clears, and real pool pressure. The closed loop drives the existing
Sakuya/Remilia local planner with explicit sensing and issue delay and asserts
hard no-Bomb. Periodic independent geometry comparison and complete-stage C
lockstep make failures retainable and shrinkable.

The extreme seed `0xce0132` completed all 12,000 frames, reached the real
1,536-bullet capacity, spent 1,655 frames saturated, and executed more than
156,000 transform activations. This establishes a workload denser than
shipped Lunatic and exercises long state, but does not establish arbitrary ECL
or shipped-stage equivalence. Exactness begins at resolved producer events;
ANM states 2/3/4, arbitrary ECL/child/timeline execution, callback 14, and
unsupported transforms remain explicit next work. The complete contract is
tracked in `TH08_SOURCE_STATEFUL_STAGE_FUZZER.md`.

### AUD-054 — Native source-oracle builds could be stale

Status: **CONFIRMED TEST-INFRA BUG; FIXED**

The first C oracle loader rebuilt only when the shared object did not exist.
Changing the tracked C or header could therefore leave tests green against an
old binary. The build helper now hashes the source, header, and compile flags
and writes a sidecar stamp under ignored `native/build/`; the loader rebuilds
on any mismatch. This does not enlarge semantic coverage, but it restores the
independence required for meaningful Python/C differentials.

### AUD-055 — The complete-stage oracle is source-closed only after producer resolution

Status: **BOUNDARY EXPLICIT; GLOBAL FUTURE-BIRTH AUTHORITY REMAINS OPEN**

The generated moving origins and schedules are resolved descriptor producers,
not decoded ECL programs. Calling the whole generated workload
source-authoritative without this boundary would repeat the previous hidden
modeling error in a larger simulator. Stage execution after each resolved
event is source-closed for the enumerated subset; producer reachability,
locals/control flow, child VMs, timeline enemies, action-conditioned damage,
and unsupported callback/ANM effects remain `UNKNOWN` until lowered.

Accordingly this infrastructure can already falsify RNG, allocation,
callback, transform, geometry, planner, and latency assumptions offline. It
cannot yet authorize the live global planner for spell 190 or any other card.
That promotion still requires a retained coherent VM/emitter root and complete
versioned future coverage over the exact policy horizon.

### AUD-056 — Empirical age tolerance rejected valid source/C float histories

Status: **CONFIRMED DIFFERENTIAL-INFRA BUG; REPLACED BY FORWARD ERROR BUDGET**

The first 3,600-frame gate stopped at frame 65 although every discrete field
and the gameplay RNG still agreed. The reported position difference was one
binary32 coordinate ULP (`6.1035e-5`) and velocity differed by only
`2.38e-7`. A threshold of `2e-5 + age * 1e-6` had been chosen empirically and
was not a valid bound for repeated binary32 additions after Python double-libm
`sin`/`cos` and C `sinf`/`cosf` choose adjacent velocities.

The differential now carries a per-slot forward budget: the previous admitted
position error plus the actual current velocity disagreement plus at most one
binary32 coordinate ULP for the next stored addition. Slot reuse resets the
budget. Velocity, speed, and angle limits remain strict; pool/lifecycle/RNG
state and bullet/laser collision membership must still match exactly. An
unbounded diagnostic over the whole gate established zero discrete, RNG, or
collision disagreement. The accepted maximum position drift was
`0.0005874634 px` and maximum velocity drift was `4.7683716e-7`.

### AUD-057 — The dense source-AABB oracle omitted callback collision state

Status: **CONFIRMED STALE-ORACLE BUG; THREE-WAY DIFFERENTIAL RESTORED**

The complete suite initially failed after AUD-050 with 566
NumPy-versus-oracle collision-count mismatches. The live NumPy and native
kernels agreed with each other. The supposedly independent dense source-AABB
oracle still filtered only native state 5 and included every nonzero callback
aux bullet, so the test encoded the old model rather than the source.

The workload now defines source collision eligibility as both `state != 5`
and `callback_aux == 0`. Its effect decomposition separately counts physical
geometry, retired state-5, and callback-aux changes. On the retained
1,024-position by 512-bullet workload, source oracle, NumPy, and native
collision counts have zero mismatch; 566 positions exercise the callback-aux
difference. This is a reminder that an oracle must have separate code, but it
must also carry the same declared semantic version and coverage inventory.

### AUD-058 — Spell direct fire incorrectly inherited ordinary rank uncertainty

Status: **CONFIRMED SOURCE-MODEL BUG; FIXED OFFLINE**

The future-source executor applied each enemy's captured rank count/speed
interval to every direct-fire instruction, including active spells. The
matching `DispatchShotInstruction @ 0x00422720` source puts all four count and
both speed adjustments inside `if (!g_Spellcard.IsActive())`. An active spell
does not read those fields at all.

This was strategically significant even when the conservative interval still
contained the native value: it converted otherwise point-valued spell speeds
into sets, preventing a resolved retained spell birth from entering the exact
event stream. Semantics version v19 now branches on the coherently captured
spell ID, preserves the existing conservative ordinary-nonspell rank envelope,
and does not validate dormant rank fields on the source-unreached spell path.
Focused tests distinguish ordinary and spell speeds and prove that malformed
dormant rank fields cannot fail a spell closure. No physical or arbitrary-ECL
authority is claimed by this fix.

### AUD-059 — No real retained Stage-5 producer root existed

Status: **EVIDENCE GAP CLOSED PHYSICALLY; FOUR CONTENT-ADDRESSED ROOTS RETAINED**

The source-exact spell-103 fixture was synthetic. The retained 2026-08-24
Stage-5 trace predates full future-source capture and contains neither a
coherent enemy/VM slab nor RNG/emitter/timeline roots; older native-root
directories referenced by Stage-4 gates are not present in this workspace.
Treating any of those summaries as a resolved physical producer would be an
evidence fabrication.

The controller now has an explicit spell-filtered retention lane. It requires
exact runtime ECL identity, captures on the existing dedicated worker, writes
canonical deterministic-gzip capsules named by the SHA-256 of their
uncompressed content, deduplicates identical roots, and records the capsule
locator in the trace. Observer timing is excluded from root identity. The
Practice supervisor assigns each run an ignored `*.root/` sink, and the
prefix-scoped Wine runner forwards only explicitly selected spell IDs and a
positive per-spell limit.

Most importantly, capture-only completion never populates the controller's
future-source action result. It cannot enter a corridor submission, prefix
certificate, or input filter; its only effects are diagnostic read/CPU/I/O
load and trace metadata. The complete offline suite passes 1,443 tests with 5
platform skips. Corrected physical capture
`lunatic_route2_stage5_unattended_20260825_011207` subsequently retained four
integrity-checked capsules; their eligibility and first semantic boundaries
are audited in AUD-061.

### AUD-060 — Practice Start and Spell Practice were conflated

Status: **CONFIRMED BY SOURCE AND PHYSICAL IDENTITY; FIXED OFFLINE; ROOT RETRY PENDING**

The first physical retained-root attempt
`lunatic_route2_stage5_unattended_20260825_010248` selected Lunatic,
Sakuya/Remilia, and Stage 5 under the isolated TH08 prefix. It used an
86,400-second agent budget and 86,700-second trial timeout, hard no-Bomb, and a
capture-only root sink. The controller expected `ecldata5sp.ecl` (31,184
bytes, SHA-256 `d9140821...`) but captured a 47,224-byte runtime image whose
normalized SHA-256 was `3148f45f...`, exactly the pinned `ecldata5.ecl` route
image. It failed closed at `time_scale_authority_unknown`, emitted no decision
or retained-root record, and exited after about 17 seconds. Thus duration did
not terminate the attempt. Prefix cleanup found no remaining process and did
not signal another Wine prefix.

The root cause is explicit in the authoritative source. `GameManagerFlags`
assigns bit 0 to `isPracticeMode` and bit 14 to `isSpellPractice`.
`EnemyManager::AddedCallback` selects `g_StageEclFiles[currentStage]` whenever
bit 14 is clear, selects an individual `g_SpellEclFiles` entry for Spell
Practice cards at least 205, and otherwise selects
`g_StageSpellEclFiles[currentStage]`. The runtime catalog now maps Practice
Start to the ordinary route identities and exposes the `*sp.ecl` family under
the unambiguous `STAGE_SPELL_PRACTICE_ECL_IDENTITIES` name. The Wine runner
therefore pins `ecldata5.ecl`; the static producer contract uses the separately
named Spell-Practice table and schema v2. Fifty-six focused catalog,
identity/scale, producer-contract, Wine-command, and Practice-supervisor tests
pass. This fixes acquisition identity only; it does not itself add a producer
event or global-planner authority.

### AUD-061 — Asynchronous transition roots consumed the per-spell quota

Status: **CONFIRMED PHYSICALLY; FIXED OFFLINE; ROOT CORPUS RETAINED**

The corrected isolated Stage-5 capture completed at manager frame 43,173 with
termination `route_complete`. It ran from clean commit `b771d31` on private
display `:98`, CPU set `24-47`, used the 86,400/86,700-second limits, and left
no process in the exact prefix. Runtime ECL identity was an exact
`ecldata5.ecl` match and the no-scale-writer schedule was complete. Four
capsules were retained for physically observed cards 103, 107, 111, and 115;
card 118 was not part of the Sakuya/Remilia Stage-5 Practice sequence. The raw
trace SHA-256 is `c8a35929...`; the ignored host report SHA-256 is
`31e442f6...`.

Capsules 103 and 115 have player phase 0. The initial projections stop,
respectively, at an address-specific singleton auxiliary callback and at
future frame 87 where bullet type 16 lacks unique template geometry. Capsules
107 and 111 were captured at player phase 3 while an earlier phase-0 request
was still executing on the worker. The old controller counted any returned
non-null spell ID, so those transition samples consumed the one-root quota.
This was harmless to action authority—the lane is capture-only and their
closures remained fail-closed—but it biased the retained corpus away from
planner-eligible roots.

Retention submissions now carry an immutable expectation over route,
difficulty, stage, spell, player phase 0, and bomb-inactive state. The worker
checks its own coherent snapshot against that expectation before persistence;
an asynchronous context/phase change writes no capsule, records an exact
rejection reason, and consumes no quota. The initial live submit gate also
requires phase 0 and bomb inactive. Dedicated tests reproduce both the
phase-3 transition and a 103-to-107 spell change. The four physical capsules
remain tracked: the two transition roots are valuable stateful-fuzzer inputs,
but are explicitly not planner-root samples. This run's 22 hits are not an
algorithm comparison because root capture added observer work and no new
future projection received action authority.

### AUD-062 — Retained producer roots had no resolved event-stream adapter

Status: **CONFIRMED ARCHITECTURE GAP; EXACT PREFIX ADAPTER FIXED OFFLINE;
ACTION AUTHORITY WITHHELD**

The retained-root lane and ordinary future-source executor ended at two
different representations. The executor could return resolved
`FutureDirectFire` records, while the source-stateful long-stage runtime began
at `BulletEmitter` records. No integrity-checked path connected a physical
capsule to that runtime, so retained roots could test source closure but could
not exercise the downstream finite-pool, transform, geometry, or planner
laboratory. Treating an UNKNOWN projection's requested slab width as a proven
prefix would also have overstated coverage.

The new adapter is generic and fail-closed. It verifies the content-addressed
capsule and exact runtime ECL SHA-256, requires a coherent phase-0,
bomb-inactive root, replays the ordinary source executor, and lowers only
point-valued direct-fire operands. Every activation becomes one immutable
one-shot emitter. The already-resolved native aim angle is retained explicitly
instead of being recomputed from an unrelated offline player position. An
interval operand is never replaced by its midpoint. Any unresolved bullet
flag, ANM/lifecycle state, transform program, callback effect, or whole-root
UNKNOWN rejects the program; a causal truncation may publish only the prefix
strictly before its first unsupported dependency. Existing generated-stage
payloads omit the optional resolved-aim field and remain schema v1, preserving
their canonical identities. Programs carrying the new field use schema v2, so
an older reader cannot silently ignore it; an attempted v2-to-v1 downgrade
fails closed.

There is no stage or spell dispatch in this production path. The four physical
Stage-5 capsules are corpus counterexamples only. The phase-3 transition roots
are rejected by the common eligibility predicate. The phase-0 callback root
has no proven prefix, while the phase-0 template-geometry root produces an
empty 86-frame causal prefix before type-16 geometry becomes UNKNOWN. Thus the
adapter is exercised on physical state, but the present corpus still supplies
zero resolved births and cannot change a global winning set. Synthetic exact
events prove aim preservation, activation timing, StageProgram round-trip,
finite-pool execution, midpoint refusal, and lifecycle-flag rejection. The
subsequent AUD-063--AUD-065 checkpoints close the generic template and bounded
spawn-lifecycle parts of that boundary. Child/timeline producers and callback
semantics remain typed UNKNOWNs; no card-specific exception was introduced.

### AUD-063 — Template capture truncated the source-initialized type table

Status: **CONFIRMED SOURCE/ASSET BUG; FIXED OFFLINE; PHYSICAL ROOT REPLAYED**

`BulletManager::AddedCallback` initializes 21 rows from the fixed
`g_BulletSpriteScripts[21]` table. Direct fire selects those rows by its
descriptor type, and `FUN_0042f5f0` copies the selected collision x/y without
clamping. The snapshot projection nevertheless read only 16 rows. The first
unsupported type in the retained phase-0 Stage-5 corpus was therefore an
observer truncation, not an intrinsically unknown game mechanic.

The new generic template contract combines source commit
`57ee34f45eb36a0eb1ad47bea8165274da8ee34f` with decoded `etama.anm`
SHA-256 `c3d19370...`, size 613,780. It parses the native ANM entry, sprite,
script, and instruction layouts; applies the source initializer's generic
sprite-size/script classes; and regenerates geometry plus lifecycle-script
terminal ages for all 21 bullet types. Runtime capture now reads all 21
initialized rows. Old immutable 16-row capsules may use the five absent static
rows only after their schema, manager base, stride, uniqueness, and every
observed type-0--15 value exactly match the source+asset contract. Sparse
fixtures, duplicate rows, altered overlap, and types outside 0--20 still fail
closed. This is type-indexed native mechanism data, not stage/spell policy.

Replaying the same retained root that exposed type 16 removes the geometry
error. Its first unsupported dependency remains at future frame 87, but is now
the real callback-14-family tag `0x100000`. The proven prefix therefore remains
86 frames and contains zero producer events; no global winning set, live
action, or hit count changed. The correction is nevertheless decisive: it
prevents a capture bug from being misdiagnosed as missing producer semantics
and locates the next exact boundary without a physical rerun.

### AUD-064 — Spawn lifecycle used one completion age for different ANM rows

Status: **CONFIRMED SOURCE/ASSET MODEL BUG; FIXED AND DIFFERENTIALED OFFLINE**

`th08_future_birth_envelope.py` used one global state-2 completion age of 10
updates and rejected states 3/4. The source instead selects one of
three spawn scripts from the descriptor's bullet type and prioritizes flags
`0x02`, `0x04`, then `0x08`. The decoded asset proves that the state-2 terminal
age is 10, 24, or 30 depending on that type; state 3 uses 15, 24, or 30, and
state 4 uses 24 or 30. `BulletManager::OnUpdate` also moves the pre-activation
state by velocity divided by 2, 2.5, or 3, then enters the full state-1 update
in the same manager call when the ANM script completes. Thus the old global
10-frame coefficient can place many generic future bullets incorrectly.

The event IR now carries the validated native bullet type through causal
conditioning, and both AABB and annular-sector lowerings select the lifecycle
from type plus the source's flag-priority chain. A pre-activation bullet is
absent from the lethal field; on its asset-derived terminal update the model
performs the divided motion, activates it, and performs the full state-1
motion in that same manager call. This is one generic mechanism table for all
21 initialized types, with no stage or spell dispatch.

The tracked C oracle independently transcribes the state selection, divided
motion, same-update activation, and binary32 position writes. A deterministic
sweep covers all 21 types, the three singleton flag classes, no lifecycle,
and the mixed classes `0x06`, `0x0c`, and `0x0e`, including samples immediately
before, at, and after each terminal age. Every discrete state and lethal gate
matches, and every C position is contained by both solver representations.
Callback tag `0x100000` remains UNKNOWN and is neither cleared nor treated as
a harmless flag. The physical retained root therefore still stops at frame
87 with an empty 86-frame prefix; this correction has no action or hit-count
authority yet.

### AUD-065 — A fixed numeric guard did not enclose repeated binary32 motion

Status: **CONFIRMED DIFFERENTIAL GEOMETRY BUG; FIXED OFFLINE**

The old future geometry evaluated an ideal binary64 expression and added a
fixed `2e-5` positional guard. That is not a bound on source execution: every
binary32 add/divide/store can round, and its accumulated displacement depends
on velocity, origin, lifecycle divisor, activation age, and horizon. In the
fixed-seed C-oracle lifecycle sweep, 392 of 420 lethal samples escaped that
guard. The largest axis error was about `8.17512e-4`, or `7.97512e-4` beyond
the claimed guard. The witness was a generic type/flag/age tuple, not a
particular stage or spell.

The replacement replays the source operation order with outward-rounded
binary32 intervals after every scale, divide, and add. AABB lowering consumes
those intervals directly. The compact sector representation keeps the common
speed/angle parameter correlated and analytically accumulates one explicit
error term for every native float32 operation. Its initial `sinf`/`cosf`
component guard scales with speed and is propagated through every later
update; it is not a fixed final-position constant. The point sweep and a
second 256-root random speed/angle sweep now contain every C-authoritative
sample. Removing per-bullet interval-trajectory materialization also reduces
the joint 1,536-birth 16/269-frame stress from 4.84 s to 0.61 s (about 7.9x)
at roughly 67 MiB peak RSS, without writing a report artifact.

### AUD-066 — Future projection identity omitted lifecycle-selecting type

Status: **CONFIRMED VERSION-JOIN BUG; FIXED OFFLINE**

After `bullet_type` became a causal lifecycle operand, the event survived
conditioning and geometry lowering but was absent from the canonical future-
projection identity payload. Two otherwise identical events could therefore
share a digest when their currently selected flag-free trajectories happened
to match, even though a valid later lifecycle flag would give them different
terminal ages. A cached global result must never alias across such an operand.

Projection schema/version v6 records `bullet_type` explicitly. A regression
constructs type-2 and type-7 events with identical supplied geometry and no
lifecycle flag, proves their trajectories are equal, and nevertheless requires
different digests and `VersionIdentity` values. A second case applies state-2
and proves their lethal terminal frames diverge. This is an identity/integrity
repair only; action authority remains withheld.

### AUD-067 — Long-stage stateful execution omitted native spawn lifecycle

Status: **CONFIRMED COVERAGE/IR GAP; FIXED AND DIFFERENTIALED OFFLINE**

The source-authoritative lifecycle and C oracle introduced by AUD-064 existed
only in the bounded future-envelope path. `StageProgram` could not retain the
native bullet type or spawn flags, and its full-stage runtime consequently
exercised only immediately active state-1 births. Long transition histories
therefore could not expose lifecycle interactions, pool pressure around
activation, or a same-update collision at the state-1 boundary.

Schema v3 adds the exact `[bullet_type, spawn_flags]` pair while preserving the
canonical v1/v2 readers and digests. The payload boundary accepts only a
two-integer canonical pair; flags outside the source lifecycle mask fail
closed. The retained-root adapter now admits the generic lifecycle-only bits
`0x02/0x04/0x08` and continues to reject any unresolved flag. Allocation uses
the source's four-velocity spawn offset; updates apply the type-selected
divided motion, suppress culling/collision before activation, and continue
through the ordinary state-1 move and collision in the terminal manager call.
Native lifecycle state/timer are separate runtime fields from callback-12
phase/auxiliary state. This prevents the two unrelated source fields from
silently aliasing.

Lifecycle composition with a callback tag or transform queue is deliberately
rejected until its source update order is closed. The generator nevertheless
covers all 21 types and all three lifecycle flag classes while independently
retaining callback and transform histories. There is no stage/spell switch or
handwritten trajectory in the implementation.

A 3,600-frame gate (`gate:0000000000ce0132:eca88861c592de79`) completed with
57,871 allocations, 132,455 finite-pool suppressions, 85 saturated frames,
18,665 lifecycle activations, and 120 real local-planner calls. Every one of
1,412,926 reached lifecycle samples matched the independent C state and
position exactly; RNG state/call count, collision membership, hard no-Bomb,
and periodic geometry checks also passed. The report SHA-256 was
`16176920feeee82024d81d0ee96acc99b533beaaf8119124d737ad7322c994de`.
Only its compact metrics and hash are retained; the 103,397-byte temporary
report was removed. The synthetic normalized-collision count is not a native
route hit count. Child/timeline births, lifecycle composition, and callback 14
still block a complete Stage-5 future and global action authority.

### AUD-068 — Local hazard projection retained a one-type lifecycle shortcut

Status: **CONFIRMED SOURCE MODEL BUG; FIXED AND C-DIFFERENTIALED OFFLINE**

Connecting lifecycle bullets to the real local planner exposed a second,
independent implementation. `_build_bullet_frames()` recognized only state 2,
used one fixed completion timer 9 (the observed type-0/type-1-class witness),
and treated every other native state as ordinary full-speed motion. Its hazard
filter removed only state 5, so states 2/3/4 became immediate false lethal
walls; state 3/4 never activated in the projection, and type-7/type-10 state-2
positions used the wrong 10-update schedule. This was conservative in lethal
membership but geometrically false and could collapse the local action set.

No new Wine read is required. Every bullet already contains the copied normal
ANM VM, whose `scriptIndex` is at bullet offset `+0x21a`. The source's 21
initialized rows use 21 distinct normal scripts, giving a generic one-to-one
type recovery. Both sparse Python and packed native decoders now retain that
type. The local projector selects the source/asset terminal age and divisor by
observed type plus native state, performs divided motion and same-update
activation in binary32 order, and exposes a collision hazard only in state 1
with callback aux zero. Missing type or an impossible preactivation timer fails
closed. Collision semantics version v3 includes this change, preventing a
cached older solution from aliasing it.

The lifecycle trace schema is v2 and retains the type. Existing v1 rows remain
readable, but a v1 preactivation row cannot receive exact future authority
because it lacks the discriminating operand. A raw-pool regression recovers all
21 types through both decoder paths. A separate oracle gate starts before the
terminal boundary for every type and each state 2/3/4 class, then compares four
future frames: position, native state, and lethal membership match C exactly.

Rerunning the complete 3,600-frame closed loop after this correction passed
all gates and retained the same final player position and 152 synthetic
normalized collisions as the pre-correction run. Planner p95 was 27.28 ms
versus 27.49 ms, but one timing sample is not a performance claim. Thus this is
a source-correctness and false-wall repair with no same-seed policy gain yet;
it does not justify Wine or a route-hit claim.

### AUD-069 — Enemy constructor drafts conflated parent, template, and child-bootstrap state

Status: **CONFIRMED SOURCE-ORDER MODEL BUG; FIXED IN GENERIC ORACLE, RUNTIME INTEGRATION OPEN**

The next child-birth draft initially treated the copied manager template's
bit 10 as the linked-child suppress guard and derived the post-link child
position directly from the constructor operand. Both assumptions are false.
`SpawnChildStandard0041F110` and `SpawnChildAlternate0041F280` test the
parent's HP and flag word before entering `EnemyManager::SpawnEnemy2`.
`SpawnEnemy2` copies the manager template, installs the requested base
position and copied ECL locals, and synchronously calls `RunEcl`. That child
root may change its position and flags or terminate before the parent opcode
continues.

The three low-dispatch cases `0x5A`--`0x5C` perform their linked-child,
youkai, and contact-gate writes only after a successful bootstrap. Case
`0x5C` additionally replaces the *bootstrapped* child relative position with
the parent base position and recomputes child world position before setting
the follow flag. Cases `0x5D`/`0x5E` use the same constructor without the
linked-child mutation; the alternate forms `0x5B`/`0x5E` add the parent world
position to the resolved operand before construction. Pool exhaustion or a
failed synchronous ECL return leaves no entity eligible for post-link writes.

The solver now tracks these five opcode classes in one stage/spell-neutral
Python kernel. Its input explicitly separates parent flags, copied-template
state, and arbitrary post-bootstrap child state. A separately compiled C
transcription exposes the same phase boundary. A 320-case product over all
five opcodes, parent suppression, positive/nonpositive HP, player type, pool
availability, and bootstrap success matches every integer, flag, and
binary32 position exactly; focused cases pin the `0x5C` after-bootstrap
overwrite and prove that template bit 10 does not suppress a child.

This closes only the pure constructor contract. The retained-source executor
still stops before allocating and synchronously executing arbitrary child
roots, and manager-slot scheduling/same-frame second updates remain to be
integrated. No global-policy or physical-hit result is claimed.

### AUD-070 — The retained ``manager template`` address is actually enemy slot zero

Status: **CONFIRMED SOURCE/LAYOUT BUG; FIXED OFFLINE**

The retained v14 payload key ``enemy_manager_template_source`` and the live
constant ``ENEMY_MANAGER_TEMPLATE_BASE`` name address `0x0057D2F0` as the
spawn template.  Authoritative layout and update code prove that this address
is instead `EnemyManager::enemies[0]`: `g_EnemyManager` begins at
`0x00577F20`, `firstEnemy` occupies its first `0x53D0` bytes, and
`EnemyManager::OnUpdate` starts its 480-entry scan at manager `+0x53D0`.
The historical ordinary range at `0x005826C0` consequently begins at native
slot 1 and extends through the unscanned `enemies[480]` failure sentinel.

This explains why retained spell roots show an active ``manager template``
VM even when the legacy ordinary range is empty: the row is the live boss in
slot zero, not an active copy template.  More importantly, the future-source
executor selected that mutated boss as `template = sources[0]` for timeline
births.  Any later birth could therefore inherit the boss's current emission
descriptor, motion, auxiliary contexts, flags, and body state instead of the
zeroed/source-initialized `firstEnemy` state copied by `SpawnEnemy1/2`.

The compatibility addresses and v14 payload key cannot be silently renamed,
so the live layout now exposes explicit `ENEMY_SLOT_ZERO_BASE` and
`ENEMY_SPAWN_TEMPLATE_BASE` names while retaining the old aliases for capsule
replay.  New captures label the decoded row as native slot zero.  The executor
now normalizes the legacy local indices to native slots 0--479 and constructs
births from the source-authoritative `EnemyManager::Initialize` template; it
never clones the retained slot-zero source.  No stage or spell identifier is
involved in this correction.

### AUD-071 — Native child scheduling needed the complete copied VM ABI

Status: **CONFIRMED SOURCE/CAPTURE/CAUSAL-METADATA BUGS; FIXED OFFLINE THROUGH THE CALLBACK-14 BOUNDARY**

The old timeline draft copied a live slot-zero enemy and the old child draft
stopped at constructor order.  Neither represents the executable.  Timeline
lanes run before `EnemyManager::OnUpdate`; `SpawnEnemy1/2` choose the first
inactive entry in the fixed 480-slot array, install the copy before calling
`RunEcl`, and may recursively allocate more entries.  The later ascending
manager scan gives a newly born higher-slot enemy a second update in its birth
frame, but cannot revisit a lower slot that was already scanned.  The generic
executor now reproduces this ownership and ordering for all five constructor
opcodes.  A synthetic bidirectional slot test pins both cases: a higher-slot
child receives bootstrap plus scan, while a child that reuses a terminated
lower slot receives bootstrap only.

Source comparison found three additional state errors while integrating that
scheduler.  First, `SpawnEnemy2` copies VM bytes `+0x18..+0x8f`, but retained
captures ended at `+0x67`; the missing two spawn floats, four call integers,
and four call floats are real dynamic operands in child roots.  The capture is
now a versioned `0x90`-byte projection.  Historical capsules remain readable
but carry explicit absent values and fail closed if execution reaches them.
The main-only inventory path also retains the current v3 layout instead of
mislabeling a 12-field row as historical v1.

Second, movement state zero does not clear a velocity left by an expired
state-1/state-3 segment: `FUN_00422c40` has no state-zero case and the manager
integrator continues to apply the residual vector.  The former rejection and
implicit zeroing were removed.  Reached movement writes now also follow the
dispatcher resolvers: opcode `0x41` normalizes its angle and clears the native
motion timer, `0x42`/`0x4A` resolve dynamic durations, and `0x47` resolves its
dynamic float.  No stage or spell selector participates.

Third, solver-only affine angle-to-player metadata was allowed to survive a
VM frame boundary and a parent-to-child VM copy.  The stored value interval is
still valid, but its dependency belongs to the old frame or the parent's
different source origin.  Reusing that coefficient lets global causal
conditioning substitute the wrong player geometry and can understate future
angles.  The executor now preserves the interval while forgetting obsolete
correlation at both boundaries; same-update assignments and emissions retain
their valid correlation.

The shipped Stage-5 corpus supplies an end-to-end non-synthetic gate:
subroutine 63 reaches an actual opcode-`0x5A` constructor, the pool installs
and synchronously executes subroutine 64, copied variables `10094/10095`
receive its world coordinates, and the child advances to the real auxiliary
producer.  Closure then stops at unsupported future bullet flag `0x100000`,
the known callback-14 boundary, rather than at allocation, VM state, or child
topology.  Other reached children currently expose transform-composition
boundaries.  This checkpoint therefore closes birth scheduling, not callback
14, arbitrary ECL, global-planner authority, or physical route hits.  No Wine
run is claimed.

### AUD-072 — Callback tags were rejected as motion before their ordered consumer

Status: **CONFIRMED SOURCE/IR/IDENTITY BUGS; FIXED WITH A CONSERVATIVE OFFLINE CALLBACK CLOSURE**

The first native child producer emitted descriptor flags `0x100202`, and the
old future-birth validator rejected `0x100000` as an unsupported movement flag.
That classification is false. `BulletManager::FUN_0042f5f0` copies the
descriptor word into bullet `+0xDB0`; `FUN_00430e10` uses `0x200` only to play
the spawn sound. The zero-based `g_EclExInsn` table maps immediate ECL opcode
`0x88` index 12 to `ReisenFreezeBullets`, index 13 to a background-tint-only
function, and index 14 to `FUN_00424c40`. Callbacks 12 and 14 scan all 1,536
active bullet slots and act only when `bullet.flags & vm.integer_locals[0]` is
nonzero. Thus a tag has no motion or collision effect until a later reached
callback consumes it.

Future execution now emits a single ordered action stream for direct-fire
allocation and callbacks 12/14. Reverse causal composition attaches only
matching callbacks that occur after each allocation, including native
same-frame enemy-slot order; a callback before a birth cannot mutate that
birth. Callback 13 is erased only after source proof that it changes the
background tint. Unknown callback indices still fail closed, and no
stage/spell selector participates.

The exact callback-14 scalar transition is now a shared source primitive
rather than an inferred variant of callback 12. It preserves the native
three-way phase branch: phase 1 selects callback speed and disables collision,
phase 0 advances to phase 2 without changing velocity or the auxiliary byte,
and every other phase restores base velocity and collision. A separately
compiled C transcription agrees with the Python candidate for matching and
nonmatching tag masks across ordinary and out-of-domain phase values. This
closes the scalar transition only; scheduled composition with the sensed live
pool remains gated below.

The first geometry consumer deliberately uses a conservative composition
rather than an invented exact phase history. Any matched callback widens the
birth to a full-direction disc whose speed bound is the maximum absolute base
or callback speed. Spawn-ANM nonlethal time is preserved, while all later
callback states are treated as lethal even when the native auxiliary byte
temporarily disables collision. This is a safe superset for future births but
can be broad. Callback angle, speed, mask, frame, and source are part of the
versioned causal identity and survive player-path rebasing.

A second identity bug was found during review: a callback with no future birth
was being discarded after attachment, even though it can mutate bullets
already present in the retained root pool. The projection now retains the
complete standalone callback action stream and explicitly reports that
current-pool callback composition is incomplete whenever it is nonempty. The
narrow complete-stage bridge rejects such a stream instead of silently
dropping it. Corridor submission, publication-prefix certification, and
delayed causal certification also require that gate. Therefore this checkpoint
does not authorize the global planner until the sensed live pool is stepped
through these actions.

On the physical spell-115 root, source closure now admits the real type-16
tagged birth at future frame 87 and advances from the former 86-frame boundary
to a 136-frame causal prefix. It next stops at genuinely unsupported auxiliary
opcode `0x0B`. The resolved-stage bridge still rejects the birth because its
angle is an interval, not because of its tag; no midpoint is substituted. The
complete Linux suite passes 1,493 tests with five conditional skips. No Wine
run, global action authority, or hit-count improvement is claimed.

### AUD-073 — Current-pool callbacks lacked a source-ordered hazard composer

Status: **CONFIRMED ARCHITECTURE GAP; EXACT BOUNDED COMPOSER ADDED OFFLINE,
LIVE CLOCK JOIN STILL GATED**

The retained callback stream is rooted at the future-source snapshot, whereas
the local hazard field begins at a separately captured bullet-pool state. The
old main-VM callback-12 adapter could not consume child callbacks or callback
14 and could not establish that these two clocks were the same. Merely
clearing the projection's callback-composition bit would therefore have
granted authority across an unproved temporal join.

A generic bounded composer now accepts an explicit projection-to-bullet
offset and schedules only callbacks strictly after the observed bullet state.
Callbacks at or before the offset are required to be reflected in that state;
later frames are rebased exactly. Equal-frame callbacks retain action-stream
order and collapse to the final phase, velocity, and collision auxiliary state
before that frame's native bullet movement. Callback 12 and callback 14 both
use the C-differential source primitives. The local hazard integration tests
also show that a callback replacement precedes the divided state-2 spawn-ANM
movement, rather than being applied one update late.

Authority remains deliberately narrow. A callback operand must be a point, its
event-to-bullet alignment uncertainty must be zero, and every matching bullet
must have finite base state with neither an active transform runtime nor a
pre-existing trajectory schedule. Set-valued operands are harmless only when
no sensed bullet tag matches their mask. These cases return a typed incomplete
result without midpointing or partial mutation. Packed and materialized pool
inputs produce identical schedules, and no stage or spell identifier appears
in the implementation.

This checkpoint proves an offline motion/collision composer, not the live
clock join. The controller continues to reject nonempty projection callbacks
until its coherent root, offset, horizon, and uncertainty evidence is passed
through this API and the result is joined to the exact hazard snapshot. No
Wine run or hit-count claim follows. A full 1,536-slot pool with sixteen
ordered callbacks also composes without partial output. The complete Linux
suite passes 1,500 tests with five conditional skips.

### AUD-074 — Global corridor lowering ignored native bullet spawn lifecycle

Status: **CONFIRMED GLOBAL GEOMETRY BUG; FIXED WITH SPARSE SOURCE-LIFECYCLE
COMPOSITION**

The local hazard projector already modeled bullet states 2/3/4, but the global
corridor adapter's `BulletSnapshot` protocol did not even carry native state,
state timer, or source template type. Every unscheduled preactivation bullet
therefore entered `lower_bullets` as an immediately lethal, ordinary
constant-velocity AABB. A callback-scheduled preactivation bullet instead
entered the piecewise path, which still applied callback velocity as full
ordinary motion and ignored ANM activation. Neither center trajectory is a
conservative enclosure of the native divided-motion path, so the former
global authority identity could certify the wrong geometry.

Global lowering now selects the 21-row source/asset terminal age for each
observed state and type, applies divisors 2, 2.5, or 3, and represents the
terminal manager call as a one-update divided-plus-full displacement followed
by ordinary motion. Callback velocity replacements are merged before the
same update's lifecycle multiplier. Collision remains disabled until native
state 1 and also respects the callback auxiliary schedule. The resulting
trajectory is sparse: it adds boundaries only at callback changes,
activation, and the post-activation restoration rather than materializing a
bullet object per frame.

All 21 types and all three lifecycle states were compared at preterminal,
terminal, and post-terminal updates against the local recurrence already
differentially locked to the independent C oracle. A further 256 seeded cases
randomized type, state, timer, position, velocity, and up to four paired
velocity/collision changes over twenty updates. Lethal membership matched and
the source binary32 centers stayed inside the explicit corridor uncertainty.
Forecast rebasing consumes activation and prior callbacks before policy frame
zero. Missing type, impossible timer, and unknown native state fail closed.

The global geometry authority version is now v2 and includes the corridor
bullet semantics identity, invalidating policies built under the old
lifecycle-free geometry. Transform dynamics remain a separate audited
boundary; this repair neither enables the callback clock join nor claims a
route-hit improvement. The complete Linux suite passes 1,506 tests with five
conditional skips, and the seven-page paper builds. No Wine run was performed.

### AUD-075 — Callback composition had no projection/bullet/policy clock certificate

Status: **CONFIRMED AUTHORITY-JOIN GAP; VERSIONED OFFLINE CERTIFICATE ADDED,
SOLUTION BINDING CLOSED BY AUD-076**

An exact callback transition and even an exact bullet schedule are
insufficient unless they are bound to the projection that produced the
callbacks, the bullet snapshot that receives them, and the policy interval
that consumes them. The earlier APIs carried these values independently. A
caller could therefore reuse a schedule with a different projection digest or
compute the right schedule over a horizon shorter than the global policy.

The new join binds the complete projection digest and version, projection
root, point-valued bullet root, policy source, policy horizon, required
bullet-relative horizon, and the actual composed bullet output. It requires
`projection_root <= bullet_root <= policy_source` and complete projection
coverage through the policy horizon. A nonzero bullet capture span is
incomplete whenever the projection contains a callback, including when the
callback lies at the apparent past boundary: the code may not assume every
pool slot observed the same side of that transition. Reconstructed or changed
projection identity does not match the certificate.

The final global authority assessment also now independently rejects any
projection with nonempty current-pool callbacks. This closes a defense-in-depth
gap: controller submission and prefix gates already rejected them, but a
manually constructed or future alternate solution path could otherwise reach
the authority assessor. At this checkpoint the rejection remained until
`CorridorSolution` stored and validated the new join identity. AUD-076 closes
that successor integration; this entry by itself made no worker, Wine, or
hit-count claim. The complete Linux suite passed 1,509 tests with five
conditional skips, and the seven-page paper built.

### AUD-076 — The callback clock certificate was not carried by the solved policy

Status: **CONFIRMED ARTIFACT/INTEGRATION GAP; FIXED OFFLINE AND WIRED
DEFAULT-FAIL-CLOSED, PHYSICAL EFFECT UNTESTED**

AUD-075 produced the required clock join, but the corridor worker accepted no
such input and `CorridorSolution` retained neither its immutable identity nor
the live certificate. The global assessor therefore could only reject every
callback-bearing projection. Clearing that rejection without changing the
artifact would have allowed a policy computed from one bullet pool to be
reported under a different projection or policy epoch.

The generic corridor artifact now stores the join `VersionIdentity`, while a
separate runtime handle stores the concrete certificate. The TH08 root hashes
that identity alongside the actual composed bullet pool. Before solve, the
runtime requires the projection identity, the same composed pool object, the
exact bullet root `snapshot_frame - snapshot_lag`, the binary32 unit scale,
the policy source, and the complete configured horizon to agree. Geometry
authority is v3 and includes both callback-composition and join semantics. The
independent action assessor then rechecks completeness, projection identity,
policy clock, artifact
version, and root digest before accepting a callback-bearing future.

The controller performs this join only from the raw decoded 1,536-slot pool,
not the older main-VM callback-12-only schedule. It requires an exact unit
time-scale schedule and a zero-span bullet capture, passes the composed pool
to the worker, and records only a compact identity digest, counts, and failure
reason per decision. The 1,536-slot composition is deferred until the worker
slot is free, no publication is pending, and submission is actually due; a
non-submission decision records `corridor_submission_not_ready` without
scanning the pool. Incomplete joins consume no worker slot. The production
mechanism has no stage or spell branch and remains behind the existing
default-off ordinary exact-authority lane.

Integration exposed two further structural defects. First, importing the
live composer from global infrastructure formed a semantic-package/live-
controller cycle; the shared dependency is now a value-only top-level
protocol, and the controller loads the concrete live implementation only at
the use site. Second, a solved global callback join is rooted at the worker's
older bullet snapshot and cannot certify a later local-prefix query over newly
sensed bullets. Local prefix and delayed certificates therefore continue to
reject such projections until they perform a fresh current-frame join. A
regression proves that the global certificate cannot leak across this layer
boundary.

Import smoke and the complete Linux discovery pass 1,511 tests with five
conditional skips. This proves that a callback-bearing projection can be
submitted, solved, and granted action authority offline only under its exact
certificate. It does not prove retained Stage-5 producer closure, a
losing-to-viable global-policy change, deadline delivery under Wine, or any
hit-count improvement. No Wine process was started.

### AUD-077 — Callback join identity omitted the scale used to build velocity

Status: **CONFIRMED AUTHORITY-IDENTITY BUG; FIXED BEFORE PHYSICAL USE**

The callback primitives multiply their reconstructed velocity by
`time_scale`, but the first callback-composition result and join version did
not retain that input. The live controller happened to pass exactly 1.0, yet
the public join API accepted any positive scale. An alternate caller could
therefore compose at 0.5, submit under a complete unit-scale corridor
schedule, and receive an otherwise valid projection/bullet/policy clock
certificate for the wrong velocity.

Composition and join semantics are now v2. The input is first rounded to the
native binary32 representation, stored as `time_scale_bits` in both values,
included in the join `VersionIdentity` and compact trace digest, and checked
for equality between the composition and its join. The TH08 corridor runtime
requires exact unit bits before solve; the independent action assessor repeats
that check. A regression proves that identical projection and clocks at 0.5
and 1.0 have different join identities and that the nonunit result cannot enter
the unit-scale worker.

The focused callback/global/runtime suite passes 61 tests. This repairs an
offline authority hole and changes no physical result; the full 1,511-test
checkpoint and no-Wine nonclaim remain unchanged.

### AUD-078 — Retained producer roots omitted their same-clock current hazards

Status: **CONFIRMED PHYSICAL-ROOT CONTRACT GAP; FIXED FOR NEW CAPTURES,
OLD ROOTS REMAIN FUTURE-ONLY**

The four retained Stage-5 capsules from physical run
`lunatic_route2_stage5_unattended_20260825_011207` contain the coherent enemy,
ECL, timeline, and producer state needed to rebuild future births, but their v1
schema never stored the current 1,536-slot bullet pool or 64-slot laser pool.
The raw trace that once accompanied those capsules was deliberately cleaned,
so current hazards cannot be reconstructed at the same manager clock. In
particular, the eligible spell-115 root at frame 39,998 is not an honest
same-root global-planner input. It must not be combined with an unrelated
current pool or used for a physical-policy claim.

The future-only half is nevertheless a useful non-vacuity check. Projecting
that root through H136 produces 144 annular sectors, one hostile-body AABB,
and one direct-fire event with complete source closure. With an empty current
pool, the H80 global solve remains reachable and retains 17 initial safe
actions; adding the future geometry changes the viable-state count from
11,016 to 10,615. Thus the future stream materially changes the solved
geometry, but this is not a same-root action result.

New explicit-retention captures now emit v2 capsules. Inside the existing
manager-frame/update-serial bracket they read both native hazard pools with
two persistent buffers; decoding happens only after the bracket closes and
only for a coherent attempt. The ordinary high-rate non-retention path is
unchanged. The capsule stores only canonical active planner slots, including
bullet lifecycle, callback schedules, current transform program/active handler
state, and complete laser phase state. A reader reconstructs the ordinary `Bullet`
and `Laser` inputs and rejects malformed capacities, slots, order, nonfinite
values, or schema. The v2 writer and reader also require exact agreement among
capture-before, capture-after, compact-state, future-projection, root-identity,
and current-hazard clocks, plus equal update serials. Existing v1 capsules
remain readable but explicitly lack current hazards.

A source-stateful 120-frame quick-stage root exercises 319 bullets, two
lasers, and 92 active transforms. Original versus serialized/reconstructed
inputs produce identical H16 global reachability, initial actions, action
masks, and the complete viability tensor. A 64-bullet/16-laser regression
keeps the compressed capsule below 64 KiB. AUD-080 subsequently extends that
compact root from the one pending record to the complete 18-record program and
meaningful active handler blocks. This proves compact offline planner replay,
not full native game-state replay or exact transform execution.

The VPS also has a measured rather than assumed parallel boundary. Five fair
repetitions of the same spell-115 future-only solve produced identical 10,615
viable states and approximately 171/62/41/35/39/48 ms at 1/4/8/16/24/32
geometry workers. Scaling through 16 is real; 24 and 32 regress from overhead
on this workload. An experimental native maximum-32 change was therefore
reverted. Production geometry retains its historical 16-worker maximum and
the live controller remains at eight workers because prior live 16-worker
tests increased action latency. More CPU is useful for offline parallel roots,
not as an unconditional per-root speedup.

No Wine process was started. The next physical artifact must be a fresh v2
Stage-5 root; only then can current hazards and future births be solved at one
real clock.

### AUD-079 — Active bullet transforms escape the global growth heuristic

Status: **CONFIRMED UNSOUND GLOBAL-GEOMETRY HEURISTIC; ACTION AUTHORITY
REVOKED, EXACT STEPPER OPEN**

The global corridor historically represented a current bullet with any
nonzero transform flag as constant root velocity plus 3 px of base uncertainty
and 0.35 px of additional uncertainty per future frame. No authoritative
source argument established that enclosure. The new source-stateful stage
laboratory provides a direct generic falsifier without any stage/spell branch:
quick profile seed `0xCE0132`, root frame 20, and H80.

At that root, 28 bullets have active transforms. Tracking the same runtime
objects rather than merely matching reused pool slots yields 1,969 survivor
samples. Of those, 1,069 leave the old per-axis envelope, beginning by frame
30. The worst survivor is slot 13 with active angular velocity (`0x20`) at
H80: its x center is 97.060802 px away from the constant-velocity forecast,
while the claimed bound is 31 px, a 3.13099-fold escape. This is now an exact
automated regression, not a retained exploratory number.

Global geometry semantics are therefore v4. Its immutable identity records
whether current-bullet transform geometry is complete. Packed and tuple
snapshots are inspected without materializing the 1,536-slot pool; any
contact-relevant current bullet with nonzero active transform flags marks the
solution incomplete. The shadow solve may still run for performance and
diagnostics, but the independent assessor returns
`current_bullet_transform_geometry_incomplete` and cannot grant action
authority. Native lifecycle state 5 remains correctly nonlethal and is
excluded from this gate.

This is a safety repair, not the desired geometry implementation. AUD-080 now
retains the complete ordered program and meaningful active handler state in
the compact diagnostic root, while the fast live snapshot and global
recurrence remain unchanged. A queued transform whose active flags are still
zero is therefore observable but not yet executed. The next general task is a
source/C-differential current-transform stepper. Only that exact path may set
the completeness component true for transformed current bullets.

The focused global authority suite passes nine tests, including the full
stateful falsifier. Complete Linux discovery passes 1,522 tests with five
conditional skips, and the updated paper builds to eight pages. No input
behavior, Wine run, route result, or hit-count claim follows from fail-closing
this previously unsound authority.

### AUD-080 — The retained transform runtime was only the stop-handler union

Status: **CONFIRMED ROOT-STATE BUG; COMPLETE PROGRAM/HANDLER ROOT ADDED
OFFLINE, EXACT EXECUTION STILL OPEN**

The v2 current-hazard root described its `BulletTransformRuntime` as native
queue state, but every mutable field after `next_record` came from only the
shared stop/turn block at bullet offsets `+0x1004..+0x102c`. A vector,
angular, reflection, barrier, or wrap transform could therefore round-trip its
active flag and next record while losing the timer and parameters that
determine its next update. Records before or after the cursor were also absent.
The root was planner-replay-stable only because global geometry v4 ignored
those values and remained shadow-only; it was not a resumable transform root.

Authoritative `Bullet::FUN_0042ffc0` copies and consumes a fixed 18-record
program at `+0xdd0`, 24 bytes per record. `BulletManager::OnUpdate` then runs
the active blocks in source order: deceleration, vector acceleration, angular
velocity, the three shared stop variants, the shared reflection variants,
horizontal/vertical wrap, and the timed barrier before movement and culling.
The diagnostic decoder now retains the exact 432 program bytes, queue cursor,
offscreen-suppression/count state, full `ZunTimer` triples, and only those
handler blocks whose active flag makes their union bytes meaningful. Inactive
uninitialized floats are never promoted to root state. The legacy stop-only
record remains readable for old traces and is explicitly named as incomplete.

Current-hazard schema v2 serializes the raw program as one base64 field plus
typed active blocks, validates the 18-record size, cursor, flag/block agreement,
finite operands, slot order, and original-flag identity, and continues to read
v1 roots without fabricating missing state. The source-stateful long runtime
emits the same representation and now combines original flags with bitwise OR
rather than integer addition. A 120-frame generated root, raw-slot all-handler
fixture, ABI bit round-trip, malformed-root cases, and future-root retention
pass 57 focused tests. The ordinary packed decoder is unchanged.

This is deliberately outside the 16 ms local decision path. Full-program
decoding occurs only after a retained capture bracket closes or when a due and
free global submission requests diagnostic objects. The next falsifier is a
source-order program stepper differential against an expanded C oracle,
followed by a 1/32/128/512/1,536-bullet batch benchmark. Python reference code
or any native batch that misses its measured budget remains offline/shadow.
No transform authority, Wine action, policy win, or hit-count improvement is
claimed by this root-state correction.

### AUD-081 — Reflection and culling reused the collision hitbox geometry

Status: **CONFIRMED SOURCE/ASSET GEOMETRY BUG; OFFLINE FUZZER AND C ORACLE
FIXED**

The stateful runtime and its C handler oracle used the bullet collision
half-extents for `Bullet::FUN_00432830` reflection and for the manager's
offscreen test. Authoritative source uses two different fields. Player
collision receives the full dimensions stored at bullet `+0xd34`; reflection
and offscreen culling instead dereference the current normal ANM sprite and
pass its visual width and height to `GameManager::IsWithinPlayfield`, which
halves them internally.

The distinction is material and generic. In the exact shipped `etama.anm`,
type 10 has a 12 px collision half-extent but a 32 px visual/culling
half-extent. Type 2 is also anisotropic for culling (7 by 8 px) while its
collision half-extents are 2 by 2 px. Near a boundary the old fuzzer could
therefore reflect or retire a legal bullet at the wrong frame even when its
motion-handler equations matched C.

`BulletTemplateProfile` now carries both geometries for all 21 source-
initialized rows. The culling values are regenerated from each normal
script's time-zero sprite in the hash-pinned decoded asset, so the existing
shipped-archive test checks every pin. `RuntimeBullet._inside_playfield` and
the independent C transform oracle now name and use the visual extents; the
lethal AABB continues to use the collision extents. A boundary regression
places a type-10-shaped bullet at x=-20: it remains visually inside at a 32 px
radius and retires only past x=-32.

The stage IR is now schema v4 for newly generated/source-closed programs. Each
ordinary emitter selects one of the 21 real template rows rather than
inventing arbitrary collision geometry, and serializes both collision and
culling half-extents. Older v1-v3 programs remain hash-verifiable and
parseable, but a program missing explicit culling geometry is no longer
reported source-closed or executable by the authoritative runtime.

This correction improves offline transition fidelity only. It does not yet
promote transformed current hazards, alter live input, run Wine, or establish
a hit-count change. The complete source-order transform stepper was the next
gate and is recorded in AUD-082 below.

### AUD-082 — Retained transform programs had no executable source-order kernel

Status: **CONFIRMED COVERAGE GAP; PYTHON REFERENCE AND BATCHED C ORACLE
IMPLEMENTED OFFLINE**

The v2 retained root was finally sufficient to resume a bullet, but no
consumer executed it. The only older C differential called one isolated
handler at a time; it could not falsify queue admission, immediate-record
chaining, shared handler blocks, handler order, movement, or retirement. A
global artifact therefore still had to reject every active transform even
when all required bytes were present.

The new scalar reference executes one complete source prefix: native queue
admission and skip rules, cull-suppression and sound immediates, all eight
motion handlers in `BulletManager::OnUpdate` order, shared stop/reflection/wrap
state, timed barriers, movement, visual-geometry culling, and retirement.
Template replacement (`0x4000`) and derived child emission (`0x1000000`) have
typed fail-closed exits because their color/geometry mutation and finite-pool
child allocation are not yet carried through this kernel. Fade is retained as
the post-frame native state; collision/lifecycle work after this transform and
culling prefix is not silently claimed.

The separately compiled C oracle now accepts the same flat 640-byte state and
can advance a persistent array in one call. Long independent Python/C
histories cover a sequential queue through fade, six reflections, fractional
and forced shared timers, 48 deterministic mixed eight-record programs, typed
unsupported births, and batch-versus-scalar equivalence. Integer state,
program bytes, flags, cursors, timers, and retirement agree; only a bounded
Linux `sinf`/`cosf` versus Python-libm tolerance is admitted for floats.
Fade is a stable nonlethal terminal for this prefix so a persistent batch can
continue advancing other entries; its later ANM/pool-slot lifetime remains
outside the claim. Any batch error poisons the wrapper because the native loop
may already have advanced earlier entries, preventing a partial frame from
being decoded or reused as coherent state.

This differential found a real scalar boundary error before integration.
Python compared a native binary32 time scale against the binary64 literal
`0.99`; `float32(0.99)` could consequently choose the full-rate branch while C
chose the fractional-timer branch. Frame operands and the `0.99f` and
`0.0001f` thresholds are now canonical binary32 values, with the exact
threshold path locked in regression.

The VPS pool benchmark separates useful compute from object-boundary cost:

| States | Python scalar | Native prepare | Native kernel | Native decode | Native end-to-end |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | 5.838 ms | 0.753 ms | 0.00365 ms | 1.029 ms | 1.818 ms |
| 512 | 23.493 ms | 3.075 ms | 0.00935 ms | 4.187 ms | 7.301 ms |
| 1,536 | 70.778 ms | 9.275 ms | 0.02446 ms | 12.766 ms | 22.233 ms |

At full native pool size the transition kernel sustains about 62.8 million
state-frames/s; an H80 rollout is roughly 1.96 ms of kernel work. The complete
Python-object wrapper still exceeds a 16 ms issue budget because encoding and
decoding dominate. This is direct architectural evidence: keep a persistent
flat batch in the offline/global worker and eventually populate it from packed
sensing, rather than materializing 1,536 Python dataclasses on each projected
frame. The kernel is not yet connected to global geometry v4 and grants no
live authority or route claim.

### AUD-083 — Final-B scale authority encoded Lunatic identity as mechanics

Status: **CONFIRMED LIVE AUTHORITY BUG; FIXED OFFLINE, PHYSICAL EASY
VALIDATION PENDING**

The isolated Wine wrapper could only request Lunatic, and four independent
live gates rejected exact Final-B scale authority unless the difficulty index
was exactly 3. More seriously, whole-route controller construction passed its
stage-0 launch sentinel into the Final-B source service as the expected
physical stage. The service therefore required the impossible conjunction
``stage == 0`` and terminal Final-B spell 190; it could never capture at the
actual stage-route index 7. This is a concrete instance of the route-wide
identity/dispatch defect already described by AUD-039.

The decoded authoritative ``ecldata7.ecl`` makes the correction mechanical.
Its terminal records are spell IDs 187, 188, 189, and 190 with difficulty
masks ``0xf1``, ``0xf2``, ``0xf4``, and ``0xf8`` in shared subroutine 87.
Their slow-time transition is shared all-difficulty subroutine 44: every
instruction has mask ``0xff``, callback 18 writes reciprocal 1/4 at offset
``0x5c44``, and callback 18 restores 1/1 at ``0x6018``. Difficulty therefore
selects the shipped spell-family member ``187 + difficulty_index``; it does
not select a different scale algorithm.

The source trace now derives and validates that family member for main
difficulties 0..3, while retaining exact route 2, stage 7, ECL digest,
complete-source capture, no-Bomb, and continuation gates. The live delivery
target uses the same derivation. Whole-route setup always binds the source
service to physical stage 7 even though the launch supervisor still uses
expected-stage 0 as its whole-route sentinel. Agent, hotkey, Practice, and
full-route gates now admit all four main difficulties; Extra remains rejected.
The isolated Wine wrapper exposes one difficulty argument and propagates it
to the Windows supervisor and compact host report without changing the
86,400/86,700-second budgets.

Focused regression executes the same complete 300-frame source capture for
all four difficulty/spell pairs and verifies Easy live delivery at spell 187.
This grants no hit-count claim yet. The next evidence is one clean-checkpoint
Easy Sakuya/Remilia Route-2 hard-no-Bomb run through terminal unload.

## Offline Verification Record

After the fixes above, the latest complete repository suite passed on this
VPS: 1,547 tests run, 5 conditionally skipped, zero failures or errors. The
Win32 planner build separately produced a PE32 i386 DLL with all
45 manifest exports. These offline/build gates are supplemented by the Wine
smoke record below; full-route policy validation remains separate.

### AUD-005 — TH08 lacks a prefix-scoped Wine host runner

Status: **VALIDATED-PHYSICAL**

**Observed:** the existing full-route supervisor is Windows-native and its BAT
wrapper assumes WindowsApps Python. The TH06 workspace has the required host
isolation pattern: refuse a live target prefix/display, set a dedicated
`WINEPREFIX` and X display, and run cleanup through only that prefix's
`wineserver`.

**Fixed offline:** `scripts/tools/run_th08_wine.py` now refuses a busy or
unmarked prefix, allocates a free private X display, confines the Wine tree to
an explicit CPU list, and sends cleanup only with its exact `WINEPREFIX`. The
Windows-side smoke verifies 32-bit Python/NumPy, the PE32 native planner, exact
game identity, patch byte, window focus, and native title state. The preparer
pins all binary inputs and refuses replacement of unrecognized runtime data.
The host supplies the console-subsystem controller with its own PTY, required
by Wine 8, while the launched game remains redirected away from that PTY.
Cleanup authority is the exact-prefix `/proc` scan: Wine 8 can return status 1
from `wineserver -k` merely because the prefix server already exited.

**Validated physical:** ignored host report
`artifacts/wine-th08/smoke-20260823T165134Z/report.json`, bound to commit
`0ab24f830cd3c03f76624fe0f53b98dc7ab1b03f`, passed on Wine 8.0. The
Windows record proved 32-bit Python 3.11.9, NumPy 1.26.4, the PE32 native ABI,
exact executable identity, patch address `0x0044D0FA` byte `0x00`, one focused
game window, and native title state. The exact target was terminated and the
host observed zero processes for the dedicated prefix. `wineserver -k`
returned the documented idle-prefix status 1; no other Wine prefix was
signalled or mutated.

The later 85-hit complete Route-2 baseline also passed this isolation contract
with exact-prefix leftovers `[]`.

### AUD-006 — Query-local adaptive refinement is implemented but not live

Status: **OPEN**

**Observed:** `scripts/touhou_control/corridor/dual_refinement/` and its scalar
and vectorized tests exist, but no live controller or corridor adapter imports
the refinement entry points. The retained 16px whole-cell lower kernel is
sound but physically produced many empty queried sets.

**Hypothesized next use:** invoke bounded query-local refinement only for
coarse empty/ambiguous root cells. The refined result may narrow uncertainty
or recover a sound nonempty lower set; it may never revive center-only
occupancy or widen an exact losing result without proof.

### AUD-010 — Caps Lock bootstrap precedes any Wine foreground window

Status: **VALIDATED-PHYSICAL**

**Observed physical:** first full-route attempt
`lunatic_route2_fullrun_unattended_20260823_165320` failed before launching
TH08 because `ensure_caps_lock_enabled()` sent and read the global toggle
before Wine had created a focusable window. The same ordering works on a
native interactive Windows desktop but not on a fresh private Xvfb/Wine
desktop. The attempt produced no gameplay trace and cleanup observed no
dedicated-prefix process.

Moving the toggle after exact-window focus did not resolve it: follow-up Wine
smoke `smoke-20260823T165627Z` again observed `GetKeyState(VK_CAPITAL) & 1 ==
0` after the injected scan-code transition, while exact game launch, patching,
and termination still succeeded.

**Fixed offline:** repository-wide use inspection found no Caps Lock read in
the solver, direct `AgentHotkey.arm()` path, input dispatcher, or game
configuration. It was a stale convenience inherited from the earlier manual
hotkey bootstrap, whereas both unattended supervisors now call `arm()`
directly. The unattended supervisors and menu smoke no longer gate gameplay on
this unrelated desktop toggle and write an explicit `required: false` session
record. The strict helper remains available to the legacy/manual path.

**Validated physical:** ignored report
`artifacts/wine-th08/smoke-20260823T165759Z/report.json`, bound to commit
`137d9c7a23b32a91595f3340abef21f02a05b013`, passed the complete smoke
contract with `caps_lock_bootstrap.required=false`, exact target termination,
and zero dedicated-prefix processes.

### AUD-011 — Native-Windows route timeout is too short for Wine VPS cadence

Status: **VALIDATED-PHYSICAL**

**Observed physical:** calibration run
`lunatic_route2_fullrun_unattended_20260823_165837` reached manager frame
4,293 in about 84 seconds (roughly 51 frames/s) before an intentional clean
stop. The retained complete route ends near frame 239,827. The inherited
4,500-second native-Windows agent budget requires at least 53.3 frames/s and
would therefore predictably terminate before Final-B, with less headroom as
later stages become denser. The calibration summary is retained, but it is not
a policy result.

**Fixed offline:** the Wine host defaults to a deliberately nonbinding
86,400-second agent budget and 86,700-second trial timeout. Normal termination
is `route_complete`; the separate 120-second trace-stall gate remains active.
This changes only the outer wall-clock watchdog; game frames, solver horizons,
menu path, policy flags, and hit metric are unchanged.

**Validated physical:** the 85-hit baseline ran to `route_complete` without a
duration or stall termination. The host runner then observed zero processes
under the exact TH08 prefix.

## Runtime Isolation Record

At audit start, another TH06 Wine workload was active on display `:97` with
its own prefix. No signal, prefix mutation, affinity change, or shared cleanup
was performed. TH08 must use a distinct prefix and a free display selected at
launch time.

During the post-fix full route, four unrelated TH105 workers used displays
`:120..:123` and their own prefixes. TH08 remained on its auto-selected `:98`,
CPU set `24-47`, and dedicated `reference/wine-prefixes/th08-retail` prefix;
cleanup resolved and checked only that exact prefix.
