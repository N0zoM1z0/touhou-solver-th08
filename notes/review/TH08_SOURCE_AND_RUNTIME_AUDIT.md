# TH08 Source And Runtime Audit

Last updated: 2026-08-24.

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
Stage-5 index 5.  Runtime index 4 is a valid no-writer Stage-4B Practice image,
but is not part of the Sakuya/Remilia Route-2 sequence.  Static no-writer
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

## Offline Verification Record

After the Linux native build and fixes above, the latest complete repository
suite passed on this VPS: 1,408 tests run, 5 conditionally skipped, zero
failures or errors. The Win32 planner build separately produced a PE32 i386 DLL with all
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
