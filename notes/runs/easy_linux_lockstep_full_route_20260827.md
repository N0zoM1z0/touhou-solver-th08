# TH08 Native-Linux Easy Full-Route Baseline

## Result

- Route: Sakuya/Remilia, Easy, Final B.
- Runtime: pinned native i386 ELF SHA-256
  `0bd9685c8c1a7cc57a4aaee9c1a449485b8539c9a6272bcb22d70c7a9fe9f1f1`.
- Solver commit: `a9d5408` on `codex/th08-linux-native-replay-bridge`.
- Completion: normal ResultScreen replay save, with no gameplay-duration cap.
- Native player phase-2 hit edges: **31**.
- Bomb presses: **0** in both the live hard-policy check and decoded replay.
- Wall time: 11,259.448 seconds (3 h 7 min 39 s).
- Bridge/gameplay/planned epochs: 360,400 / 280,407 / 278,630.
- Final manager frame: 217,594.

The complete compact report is
`artifacts/runtime_reports/easy_linux_lockstep_full_route_20260827.json`.
The normally saved replay is
`artifacts/replays/easy_linux_lockstep_full_route_20260827.rpy`, SHA-256
`0a2d428e32cc03539db8cc15fd79de6010f2eeeceadedb5f4438aa395cbc13cf`.
It decodes as Easy route 2 with all six expected route stages and no Bomb
frame. The replay was produced with preserved lives and 31 contacts, so this
record is not an original-executable full-playback or NMNB certificate.

## Stage distribution

| Route stage | Native hits |
| --- | ---: |
| Stage 1 | 0 |
| Stage 2 | 1 |
| Stage 3 | 1 |
| Stage 4A / Reimu | 3 |
| Stage 5 | 7 |
| Final B / Kaguya | 19 |

The historical Wine Easy route from 2026-08-25 recorded 13 hits with counts
`0/0/0/1/1/11`. That run used a different RNG trajectory, asynchronous
actuator model, planner configuration, and solver revision, so `13 -> 31` is
not a controlled platform effect. It is nevertheless enough to reject the
hypothesis that removing Wine latency and attaching the minimal `8/12/8`
current-hazard planner automatically improves Easy survival. The Linux seam is
working; the deliberately small policy attached to it has lost important
strategy.

## What the retained precursors prove

The driver retained the final 12 planned roots before every hit. Every hit
arrived exactly one manager frame after the last retained decision.

The following taxonomy describes the **selected path**, not every alternative
action and not the exact colliding native object:

| Last-decision class | Hits | Meaning |
| --- | ---: | --- |
| Nonpositive planned clearance or robust collision | 16 | The selected action was already modeled as losing or overlapping. The current report does not retain the complete per-action certificate set, so it cannot by itself prove action-set exhaustion. |
| Positive but below 2 px planned clearance | 9 | The selected path was nominally safe but had little modeling margin. Birth timing, geometry/update order, and aggressive boundary motion remain competing explanations. |
| At least 2 px positive planned clearance | 6 | High-value blind contacts: current-hazard rollout predicted a materially safe path one frame before the native hit. |

The six strongest blind witnesses are hit 1 (Stage 2 ordinary, 29.06 px), hit
5 (Stage 4A ordinary, 3.81 px), hit 9 (Stage 5 ordinary, 4.13 px), hit 12
(Stage 5 spell 108, 3.44 px), hit 15 (Final B spell 147, 2.53 px), and hit 30
(Final B spell 171, 4.27 px). These are the first roots to replay against
source-authored future births and exact update order. They do not yet prove
that a birth caused contact because the compact report did not retain the
native colliding object or a complete future root.

Three generic factors dominate the final decision rows:

- 21/31 select an unfocused `*_fast` action;
- 18/31 contacts occur at a left/right playfield edge;
- 20/31 contacts occur at or very near the bottom edge.

This separates two necessary work streams. Future-birth/current-geometry work
can explain the blind class. Boundary recoverability and Focus/fast selection
must explain why many selected paths are already nonpositive; adding unseen
births alone cannot repair those decisions.

## Infrastructure and cost

All 360,400 wire requests passed their fixed-memory witness. Seven input
differences occurred only outside the ready same-lifecycle authority domain;
there were zero authoritative echo mismatches. The route normally traversed
indices `0,1,2,3,5,7`, entered ResultScreen, and saved replay slot 1.

The synchronous solver cost over 278,630 planned epochs was:

| Component | Mean | p95 | Maximum |
| --- | ---: | ---: | ---: |
| Complete pool read | 5.45 ms | 7.12 ms | 16.38 ms |
| Decode | 2.01 ms | 7.36 ms | 76.37 ms |
| Local planning | 10.26 ms | 20.74 ms | 75.56 ms |
| Total | 17.72 ms | 32.17 ms | 101.80 ms |

The route has 61,036 more planned epochs than final manager-frame increments.
This quantity includes manager-clock gates and transitions and must not be
called dialogue time without a per-epoch scene predicate. Live inspection did
confirm long source-message episodes in which the current opcode was wait
`0x04`, `dialogueSkippable` was set, and the planner continued to copy pools.

After gameplay unregistered at epoch 280,706, the already-unlocked Ending
(`Supervisor` state 9, `Ending::hasSeenEnding == 1`) ran until ResultScreen at
epoch 360,217: 79,511 avoidable transition epochs. Source `Gui::RunMsg` and
`Ending` provide exact generic skip gates; later drivers should use them rather
than a stage/spell predicate.

## Next falsifiers

1. Retain complete per-action certificates, boundary reserve, and exact native
   contact witnesses around hit edges; do not infer action-set exhaustion from
   the selected action alone.
2. Add a source-state-driven dialogue/route-choice/Ending controller and skip
   hazard capture while the enemy clock is message-blocked. This is an
   infrastructure optimization, not a hit fix.
3. Run source-stateful A/B experiments for the minimal Linux `8/12/8` policy
   against the mature Easy local configuration before changing live defaults.
4. Replay the six high-clearance blind roots through the source future-event
   stream. Promote future hazards only when the temporal/current-pool join is
   complete.
5. Measure generic inward recoverability and Focus/fast alternatives on the
   boundary cluster. Only a mechanism-changing offline result justifies the
   next full route.
