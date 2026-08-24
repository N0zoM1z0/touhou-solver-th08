# TH08 Source And Runtime Audit

Last updated: 2026-08-24.

This ledger tracks discrepancies found while rebasing the live solver on the
exact Japanese TH08 1.00d executable, using the independently reconstructed
source tree at `../th08` only as a semantic reference. Rebuilding that source
tree is not part of this solver task. This ledger is intentionally separate
from historical run dossiers: entries remain open until the responsible solver
path is fixed and validated.

The ordered one-change-at-a-time implementation and physical experiment
sequence is tracked in `TH08_LUNATIC_OPTIMIZATION_CAMPAIGN.md`.

Evidence labels follow the repository contract:

- **Observed:** read directly from the exact executable, runtime, or retained
  trace.
- **Inferred:** follows from observed facts but has not yet received a direct
  physical falsifier.
- **Hypothesized:** a candidate explanation or improvement awaiting evidence.

Statuses are `OPEN`, `FIXED-OFFLINE`, `VALIDATED-PHYSICAL`, or `REJECTED`.

## Target And Scope

- Active target: Sakuya/Remilia, Lunatic, Route 2, Final-B, hard no-Bomb.
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

Status: **REJECTED**

**Observed source cross-check:** Sakuya and Remilia SHT headers both specify a
2-unit player hitbox width, hence one-unit lethal half-extents already used by
the solver. `BulletManager::OnUpdate` constructs active laser size as visible
length (or the source's 0.7 tail reduction) by half the raw laser width;
`Player::CalcLaserHitbox` then halves those full dimensions and performs the
same inclusive, origin-rotated AABB test implemented in
`th08_laser_model.py`. Warmup/fade fallthrough, collision thresholds, and the
source's unusual longitudinal ramp also match. The four observed laser hits
remain real policy failures; no geometry correction is justified by current
evidence.

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

## Offline Verification Record

After the Linux native build and fixes above, the complete repository suite
passed on this VPS: 1,349 tests run, 5 conditionally skipped, zero failures or
errors. The Win32 planner build separately produced a PE32 i386 DLL with all
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
