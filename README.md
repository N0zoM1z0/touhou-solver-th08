# Touhou Solver

An original-game TH08 control and reverse-engineering research workspace. The
current target is physically validated Sakuya/Remilia Lunatic Route-2 NMNB,
followed by Extra.

This is not a portable reimplementation of TH08. The solver senses and
controls the shipped Windows game, while native-root replay and a fail-closed
short-prefix model provide faster controlled iteration.

## Start

Read:

1. [`AGENTS.md`](AGENTS.md) — repository and research contract;
2. [`GOAL.MD`](GOAL.MD) — primary physical completion target;
3. [`START_HERE.md`](START_HERE.md) — current checkpoint and next experiment;
4. [`STRATEGY.md`](STRATEGY.md) — action-authority ledger;
5. [`notes/review/TH08_LUNATIC_NMNB_RESEARCH_TASKBOOK.md`](notes/review/TH08_LUNATIC_NMNB_RESEARCH_TASKBOOK.md)
   — closed research loop.

The complete chronological research log remains active. Other retired history
is intentionally absent from the active tree; see
[`ARCHIVE_INDEX.md`](ARCHIVE_INDEX.md) and Git tag
`pre-workspace-prune-20260731`.

## Current Architecture

- `scripts/th08_live_dodge_agent.py` — live orchestration entrypoint.
- `scripts/th08_live/` — sensing, policy, planning pass, trace, and issue flow.
- `scripts/touhou_control/` — reusable planning/control primitives.
- `scripts/th08_runtime/` — TH08 native layouts, snapshot, and probes.
- `scripts/analysis/` — focused differential/report tools.
- `scripts/tools/` — explicit builds and native capture/search entrypoints.
- `native/` — native decode, hazard, viability, and local reducer backend.
- `tests/` — deterministic focused and checkpoint gates.
- `artifacts/` — compact retained evidence; raw captures remain ignored.

The promoted physical policy is hard no-Bomb robust survival with native
sensing/decoding, Boolean viability, baseline local reduction, pre-loss
continuation preference, and a fresh issue-time certificate.

The native snapshot wind tunnel can branch original TH08 from one canonical
root and has already found an exact H=32 no-hit witness. The current offline
combat/resource model covers normal shots, enemy damage/defeat, item pickup,
Power, and mandatory events, but it has no live ranking authority.

## Research Principle

Progress means a controlled improvement in native survival, canonical first
hit, rotated physical hit count, or NMNB completion. More code, tests,
reports, or decoded fields are useful only when they unblock that loop.

Use:

`root -> exact repeat -> native branches -> first mismatch -> one general fix -> native confirmation -> focused physical falsifier`

After a material integrated gain, run one fresh full Lunatic route. Do not
overfit one stage or infer causality from different-RNG totals.

## Quick Verification

```bash
PYTHONPATH=scripts python3 -m unittest discover -s tests -p 'test_*.py'
```

Native build:

```bash
python3 scripts/tools/build_native_planner.py --target linux
python3 scripts/tools/build_native_planner.py --target windows
python3 scripts/tools/build_native_planner.py --target windows-x86
```

Physical launch is user-authorized only:

```bat
run_th08_practice_agent.bat --stage 5
run_th08_full_route_agent.bat
```

See [`START_HERE.md`](START_HERE.md) for the exact Windows UNC test loader,
current evidence, and operating constraints.

## License

Repository source and documentation use the [MIT License](LICENSE). Game
assets, names, and trademarks are not licensed here; see [NOTICE.md](NOTICE.md).
This independent project is not affiliated with Team Shanghai Alice.
