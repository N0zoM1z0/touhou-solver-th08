# TH08 source oracle

This directory contains a deliberately small C oracle used only by offline
differential tests. It is tracked in the solver repository and is not a build
of the recovered game source.

Source basis (authority repository commit `57ee34f`):

- `src/Global.cpp`: `Rng::GetRandomU16`, `GetRandomU32`, `GetRandomF32`, and
  `AddNormalizeAngle`;
- `src/BulletManager.cpp`: `BulletManager::FUN_0042f5f0` direct-fire modes
  0–8, generic state-2/3/4 spawn selection and `OnUpdate` motion/activation,
  transform handlers `FUN_00432210` through `FUN_00432830`, and the inclusive
  player/bullet AABB ordering in `OnUpdate`;
- exact shipped `etama.anm` SHA-256 `c3d19370...`: first reachable delete
  times for the 21 source-selected spawn lifecycle rows;
- `src/EclExIns.cpp`: `EclExIns::ReisenFreezeBullets` at `0x424A20`.
- `src/EnemyTimeline.cpp`, `src/EclDependencies.cpp`, `src/EclRun.cpp`, and
  `src/EclRunLow.inl` / `src/EclRunHigh.inl`: generic constructor geometry,
  admission, and hazard-relevant first-flag-word/post-bootstrap transitions
  for ECL opcodes `0x5A` through `0x5E`.

The C code is kept independent of both the Python model and the optimized
planner library. It intentionally exposes pure, bounded kernels only. Apart
from the pinned state-2/3/4 terminal-time table above, general ANM execution,
global game effects, unknown ECL callbacks, and other dependencies remain
outside its exactness claim.

Linux builds are reproducible with:

```bash
PYTHONPATH=scripts python3 scripts/build_th08_source_oracle.py
```

The resulting shared object is placed under ignored `native/build/`.
