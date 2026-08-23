# TH08 Isolated Wine Runtime

This is the host-side path for the exact Japanese TH08 1.00d executable on the
VPS. It runs the existing Windows supervisor and live solver unchanged inside
a dedicated 32-bit Wine prefix. The reconstructed source checkout is reference
material only and is not built by this workflow.

## Fixed Inputs

- `th08.exe`: SHA-256
  `330fbdbf58a710829d65277b4f312cfbb38d5448b3df523e79350b879213d924`.
- Python: official 3.11.9 embeddable Win32 archive, pinned by SHA-256.
- NumPy: 1.26.4 CPython 3.11 Win32 wheel, pinned by SHA-256.
- Native planner: locally built PE32 i386
  `native/build/windows-x86/touhou_viability.dll`, SHA-256
  `4c8c3a34485ec22437224d0fa8a5ad631d3d64f952d66bc9e621147cedf41603`.
- Runtime game, Python, prefix, raw Wine logs, and large traces are ignored.

The prepared `th08.cfg` changes display/audio operation only: windowed mode,
sound off, no frameskip, and the original maximum effect quality. It preserves
the target's default controller mapping, lives, Bomb stock, and gameplay
quality. The solver still makes Bomb input unrepresentable.

## Prepare Once

```bash
.venv/bin/python scripts/tools/build_native_planner.py --target windows-x86
.venv/bin/python scripts/tools/prepare_th08_wine_runtime.py \
  --game-source '/home/yann/yann/touhou/th08-research/game_exe/extracted/[th08] 东方永夜抄 (日文版)'
```

The preparer is idempotent only for an attested runtime. It refuses an existing
unmarked directory instead of overwriting it.

## Smoke

```bash
.venv/bin/python scripts/tools/run_th08_wine.py --mode smoke
```

The smoke must prove all of the following before gameplay:

1. a free private X display and idle dedicated prefix;
2. 32-bit Windows Python importing NumPy;
3. the PE32 native planner loading and accepting an ABI call;
4. exact executable identity and the in-memory no-life-decrement byte;
5. one exact TH08 window reaching the native title state;
6. exact-prefix cleanup with no remaining processes.

Wine 8 requires valid console handles for the embeddable Windows CPython. The
host therefore gives the controller a private PTY and records all forwarded
output; the game launched by the Windows controller remains separately
redirected to its batch log.

## Lunatic Sakuya/Remilia Route 2

```bash
.venv/bin/python scripts/tools/run_th08_wine.py --mode full-route
```

This invokes the existing full-route supervisor with `--armed`,
`--refuse-existing`, exact Final-B ECL scale authority, Lunatic default, and
Sakuya/Remilia team selection. The baseline command does not enable the
experimental ordinary pre-exhaustion authority or kill-before-saturation
objective. Add those flags only for a declared comparison.

The Wine runner uses a deliberately nonbinding 24-hour agent budget and a
24-hour-plus-five-minute trial timeout. Normal termination is `route_complete`;
the independent 120-second trace-stall gate still stops a genuinely frozen
run. The retained route is about 239,000 game frames, so this avoids coupling
acceptance to the VPS's sub-realtime Wine rate without changing any in-game
timing or policy parameter.

The default affinity is CPUs `24-47`, bounding the whole Wine/controller tree
to 24 of the VPS's 96 logical CPUs. Override with `--cpu-list` when necessary.
The runner never calls a generic Wine cleanup: every `wineserver -k` receives
the exact dedicated `WINEPREFIX`, and cleanup is attested from `/proc`.
Wine 8 may return status 1 when that server is already idle, so the recorded
return code is advisory; any actual exact-prefix process left in `/proc` fails
the run.

Host reports and Wine logs live under ignored `artifacts/wine-th08/`. The
existing supervisor writes compact route session/dossier evidence under
`artifacts/runtime_reports/` and `notes/runs/`.
