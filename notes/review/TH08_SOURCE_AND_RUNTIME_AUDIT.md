# TH08 Source And Runtime Audit

Last updated: 2026-08-23.

This ledger tracks discrepancies found while rebasing the live solver on the
exact Japanese TH08 1.00d executable, using the independently reconstructed
source tree at `../th08` only as a semantic reference. Rebuilding that source
tree is not part of this solver task. This ledger is intentionally separate
from historical run dossiers: entries remain open until the responsible solver
path is fixed and validated.

Evidence labels follow the repository contract:

- **Observed:** read directly from the exact executable, runtime, or retained
  trace.
- **Inferred:** follows from observed facts but has not yet received a direct
  physical falsifier.
- **Hypothesized:** a candidate explanation or improvement awaiting evidence.

Statuses are `OPEN`, `FIXED-OFFLINE`, `VALIDATED-PHYSICAL`, or `REJECTED`.

## Target And Scope

- Active target: Sakuya/Remilia, Lunatic, Route 2, Final-B, hard no-Bomb.
- Baseline: full route `lunatic_route2_fullrun_unattended_20260730_222529`,
  68 native hit edges, stage counts `2/3/5/20/15/23`, zero Bomb input.
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

## Offline Verification Record

After the Linux native build and fixes above, the complete repository suite
passed on this VPS: 1,337 tests run, 5 conditionally skipped, zero failures or
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

A complete Route-2 run remains the later physical policy gate, not part of
this runner acceptance item.

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

## Runtime Isolation Record

At audit start, another TH06 Wine workload was active on display `:97` with
its own prefix. No signal, prefix mutation, affinity change, or shared cleanup
was performed. TH08 must use a distinct prefix and a free display selected at
launch time.
