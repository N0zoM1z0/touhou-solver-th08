# TH08 source oracle

This directory contains a deliberately small C oracle used only by offline
differential tests. It is tracked in the solver repository and is not a build
of the recovered game source.

Source basis (authority repository commit `57ee34f`):

- `src/Global.cpp`: `Rng::GetRandomU16`, `GetRandomU32`, `GetRandomF32`, and
  `AddNormalizeAngle`;
- `src/BulletManager.cpp`: `BulletManager::FUN_0042f5f0` direct-fire modes
  0–8 and the inclusive player/bullet AABB ordering in `OnUpdate`;
- `src/EclExIns.cpp`: `EclExIns::ReisenFreezeBullets` at `0x424A20`.

The C code is kept independent of both the Python model and the optimized
planner library. It intentionally exposes pure, bounded kernels only. Global
game effects, ANM completion, unknown ECL callbacks, and other dependencies
remain outside its exactness claim.

Linux builds are reproducible with:

```bash
PYTHONPATH=scripts python3 scripts/build_th08_source_oracle.py
```

The resulting shared object is placed under ignored `native/build/`.
