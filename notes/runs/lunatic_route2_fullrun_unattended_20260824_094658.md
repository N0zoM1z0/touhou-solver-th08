# TH08 Lunatic Full-Run Review: lunatic_route2_fullrun_unattended_20260824_094658

## Result

- Route: Sakuya/Remilia, Lunatic, Final B / Kaguya.
- Combat completion: yes; gameplay scene unloaded at frame 228477.
- Native phase-2 hit edges, including Last-Spell-saveable edges: 93.
- Deathbomb requests at those edges: 0.
- Hard no-Bomb input verification: passed across 50669 decisions.
- Post-hit Bomb-stock decreases: 23.00; this is respawn-stock reset telemetry, not evidence of Bomb input.
- Agent decisions: 50669.
- Raw trace size: 1902012413 bytes across 1 segments.
- JSON decode errors: 0.
- Exact spell-level hit attribution: available from live `g_spell_card_state`.

The run is valid for stage-, death-, resource-, projectile-, latency-, and route-level analysis. Spell names below are the statically reachable Lunatic route inventory; unavailable runtime hit counts remain explicitly unresolved instead of guessed. The no-life patch allows post-hit resource resets to repeat, so resource-stock changes must not be interpreted as Bomb commands.

## Trace Integrity

| Segment | Frames | Decisions | Wall Z | Termination | Runtime error | SHA-256 |
| --- | ---: | ---: | ---: | --- | --- | --- |
| 1 | 1..228477 | 50669 | 418 | route_complete | - | `8c17c304dd4f3d154f98ba22969c53e8719204a7368fab8eec1e2b0e64b5538f` |

The route is one continuous agent-controlled trace with no foreground interruption or manual re-arm gap.

## Stage Summary

| Stage | Frames | Decisions | Native hits | Deathbombs | Post-hit Bomb-stock decrease | Power start/end/min | Max bullets | Max lasers |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Stage 1 | 1..21008 | 4842 | 4 | 0 | 1.00 | 0.00/2.00/0.00 | 1178 | 0 |
| Stage 2 | 21008..44738 | 6190 | 7 | 0 | 0.00 | 7.00/19.00/0.00 | 1182 | 0 |
| Stage 3 | 44738..72546 | 6933 | 5 | 0 | 1.00 | 25.00/55.00/0.00 | 833 | 200 |
| Stage 4A / Reimu | 72546..118433 | 10185 | 20 | 0 | 7.00 | 60.00/0.00/0.00 | 1536 | 0 |
| Stage 5 | 118433..164747 | 8247 | 31 | 0 | 7.00 | 5.00/2.00/0.00 | 1345 | 0 |
| Final B / Kaguya | 164748..228477 | 14272 | 26 | 0 | 7.00 | 7.00/15.00/0.00 | 1250 | 255 |

## Failure Taxonomy

| Primary class | Deaths | Interpretation |
| --- | ---: | --- |
| `modeled_committed_prefix_collision` | 53 | The hit-row committed pipeline or the causal last-alive selected-action certificate was already unsafe. |
| `observed_bullet_overlap` | 36 | A bullet overlaps the native player AABB in the hit observation. |
| `sensor_gap_or_unmodeled_hazard` | 4 | No observed overlap and positive pipeline clearance; same-frame ECL emission, transform error, or another unmodeled hazard is the leading explanation. |

Contributing factors:

- `playfield_boundary`: 63 deaths
- `fast_mode`: 48 deaths
- `action_lag_over_model`: 28 deaths
- `pool_density_over_1000`: 19 deaths

## Post-Run Root-Cause Analysis

This route rejects source geometry as a sufficient optimization, not as a
physical model.  The native player AABB was stable at `(1,1)` on all 50,669
decisions and the binary32 differential remains exact.  Restoring radius 2
would hide the failure behind a false hitbox.

The strongest changed mechanism is timing.  Relative to the 57-hit GEO-001B
route, hit-row action-lag median/p95 changed from `2/4` to `4/9` frames and
hit-row observe-to-input median changed from 86.80ms to 125.43ms.  Stage 5
changed from `2/4` to `7/10` frames and from 87.98ms to 160.75ms.  Sixteen of
its 31 hits exceeded modeled delay support.  Stage-5 hit-row initial planning
and issue recertification medians were 76.37ms and 28.74ms respectively.  This
supports a latency/root feedback: late avoidance causes hits, power loss alters
phase duration and future roots, and dense later decisions become slower.

Bulk bullet capture crossed a manager frame on 4.79% of decisions, on 8 of 93
hit rows, and somewhere in 30 of 93 four-decision hit windows.  The ignored
capture interval is a real model defect but is not large enough to explain the
route regression alone.

Global planning performed no work.  Every decision had a due submission and a
sufficient numerical scale horizon, but hard scale authority was false and all
50,669 jobs were blocked.  The sole runtime ECL identity attempt compared the
Final-B static image with Stage 1, failed, and never retried.  Future hostile
birth coverage was `model_unknown` on every decision, so fixing the scale
dispatcher must first activate workers in shadow; hard control additionally
requires complete, version-compatible future-birth coverage.

## High-Risk Clusters

| Cluster | Stage | Frames | Deaths | Min Power | Max bullets at hit |
| --- | --- | ---: | ---: | ---: | ---: |
| cluster-38 | Stage 5 | 148733..152577 | 11 | 0.00 | 1015 |
| cluster-58 | Final B / Kaguya | 221344..225397 | 9 | 0.00 | 573 |
| cluster-09 | Stage 2 | 39019..39955 | 3 | 2.00 | 914 |
| cluster-20 | Stage 4A / Reimu | 84944..85921 | 3 | 0.00 | 612 |
| cluster-50 | Final B / Kaguya | 175820..176527 | 3 | 27.00 | 621 |
| cluster-16 | Stage 4A / Reimu | 76604..77047 | 2 | 54.00 | 1320 |
| cluster-21 | Stage 4A / Reimu | 95064..95533 | 2 | 3.00 | 802 |
| cluster-24 | Stage 4A / Reimu | 110902..111432 | 2 | 1.00 | 498 |
| cluster-27 | Stage 4A / Reimu | 115999..116505 | 2 | 2.00 | 1292 |
| cluster-32 | Stage 5 | 130789..131160 | 2 | 4.00 | 311 |
| cluster-41 | Stage 5 | 158847..159258 | 2 | 0.00 | 338 |
| cluster-42 | Stage 5 | 159983..160394 | 2 | 1.00 | 346 |
| cluster-48 | Final B / Kaguya | 167409..167957 | 2 | 2.00 | 610 |
| cluster-51 | Final B / Kaguya | 177180..177690 | 2 | 7.00 | 672 |
| cluster-56 | Final B / Kaguya | 205638..206163 | 2 | 0.00 | 576 |

## Stage Detail

### Stage 1

- Death frames: 1874, 4840, 7330, 13917
- Cause counts: `{"modeled_committed_prefix_collision": 3, "observed_bullet_overlap": 1}`
- Phase markers: observed 3, reachable static opcode `0x94` 4.
- Bottom/side occupancy decisions: 247/266.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1874 | 3.00 | 1.00 | 0.00 | 156 | -0.52 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 4840 | 3.00 | 11.00 | 0.00 | 373 | -0.29 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 7330 | 3.00 | 4.00 | 0.00 | 312 | -2.77 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 13917 | 4.00 | 2.00 | 1.00 | 423 | 10.86 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |

### Stage 2

- Death frames: 22051, 23036, 24340, 25280, 39019, 39456, 39955
- Cause counts: `{"observed_bullet_overlap": 3, "modeled_committed_prefix_collision": 4}`
- Phase markers: observed 2, reachable static opcode `0x94` 3.
- Bottom/side occupancy decisions: 657/601.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 22051 | 3.00 | 9.00 | 0.00 | 193 | -1.66 | - | `observed_bullet_overlap` | playfield_boundary,action_lag_over_model |
| 23036 | 3.00 | 4.00 | 0.00 | 163 | -0.48 | - | `observed_bullet_overlap` | fast_mode |
| 24340 | 3.00 | 0.00 | 0.00 | 137 | -2.89 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 25280 | 3.00 | 0.00 | 0.00 | 82 | -0.33 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 39019 | 3.00 | 21.00 | 0.00 | 914 | -1.48 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 39456 | 3.00 | 6.00 | 0.00 | 821 | -0.80 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 39955 | 3.00 | 2.00 | 0.00 | 145 | 0.09 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |

### Stage 3

- Death frames: 46362, 47043, 48203, 51504, 53024
- Cause counts: `{"modeled_committed_prefix_collision": 3, "observed_bullet_overlap": 2}`
- Phase markers: observed 3, reachable static opcode `0x94` 4.
- Bottom/side occupancy decisions: 762/722.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 46362 | 3.00 | 25.00 | 0.00 | 335 | -1.49 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 47043 | 3.00 | 10.00 | 0.00 | 299 | -0.85 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 48203 | 3.00 | 3.00 | 0.00 | 374 | -1.06 | - | `observed_bullet_overlap` | fast_mode |
| 51504 | 3.00 | 2.00 | 0.00 | 600 | -2.88 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 53024 | 4.00 | 6.00 | 1.00 | 572 | 1.32 | - | `observed_bullet_overlap` | playfield_boundary |

### Stage 4A / Reimu

- Death frames: 75093, 76604, 77047, 81445, 82887, 84193, 84944, 85535, 85921, 95064, 95533, 101678, 104795, 110902, 111432, 112235, 112964, 115999, 116505, 117546
- Cause counts: `{"modeled_committed_prefix_collision": 13, "sensor_gap_or_unmodeled_hazard": 2, "observed_bullet_overlap": 5}`
- Phase markers: observed 7, reachable static opcode `0x94` 8.
- Bottom/side occupancy decisions: 985/630.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 75093 | 4.00 | 68.00 | 1.00 | 312 | -0.80 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 76604 | 3.00 | 62.00 | 0.00 | 745 | -2.47 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 77047 | 3.00 | 54.00 | 0.00 | 1320 | -0.72 | - | `modeled_committed_prefix_collision` | pool_density_over_1000,fast_mode |
| 81445 | 3.00 | 39.00 | 0.00 | 446 | 2.03 | - | `sensor_gap_or_unmodeled_hazard` | fast_mode |
| 82887 | 4.00 | 23.00 | 1.00 | 528 | -1.84 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 84193 | 4.00 | 8.00 | 1.00 | 577 | -0.45 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 84944 | 3.00 | 1.00 | 0.00 | 612 | -0.38 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 85535 | 3.00 | 0.00 | 0.00 | 597 | -0.50 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 85921 | 3.00 | 1.00 | 0.00 | 587 | 28.39 | - | `sensor_gap_or_unmodeled_hazard` | - |
| 95064 | 4.00 | 3.00 | 1.00 | 802 | 3.69 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 95533 | 3.00 | 10.00 | 0.00 | 621 | -0.69 | - | `modeled_committed_prefix_collision` | fast_mode |
| 101678 | 3.00 | 3.00 | 0.00 | 162 | -0.39 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 104795 | 3.00 | 8.00 | 0.00 | 1248 | 2.59 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000,fast_mode |
| 110902 | 3.00 | 1.00 | 0.00 | 408 | -2.06 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 111432 | 3.00 | 1.00 | 0.00 | 498 | -1.04 | - | `observed_bullet_overlap` | playfield_boundary,action_lag_over_model,fast_mode |
| 112235 | 4.00 | 0.00 | 1.00 | 692 | -2.29 | - | `modeled_committed_prefix_collision` | action_lag_over_model,fast_mode |
| 112964 | 4.00 | 8.00 | 1.00 | 715 | -2.81 | - | `modeled_committed_prefix_collision` | action_lag_over_model |
| 115999 | 3.00 | 7.00 | 0.00 | 1000 | 0.33 | - | `observed_bullet_overlap` | pool_density_over_1000 |
| 116505 | 3.00 | 2.00 | 0.00 | 1292 | -0.02 | - | `observed_bullet_overlap` | pool_density_over_1000,fast_mode |
| 117546 | 4.00 | 1.00 | 1.00 | 1335 | -1.51 | - | `modeled_committed_prefix_collision` | pool_density_over_1000 |

### Stage 5

- Death frames: 120476, 121971, 122822, 130789, 131160, 141402, 142054, 142690, 146918, 147878, 148733, 149121, 149540, 149850, 150226, 150622, 151106, 151490, 151911, 152225, 152577, 156613, 157613, 158847, 159258, 159983, 160394, 161167, 162140, 163343, 164302
- Cause counts: `{"sensor_gap_or_unmodeled_hazard": 1, "modeled_committed_prefix_collision": 14, "observed_bullet_overlap": 16}`
- Phase markers: observed 7, reachable static opcode `0x94` 8.
- Bottom/side occupancy decisions: 1587/749.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 120476 | 3.00 | 6.00 | 0.00 | 655 | 0.76 | - | `sensor_gap_or_unmodeled_hazard` | action_lag_over_model,fast_mode |
| 121971 | 3.00 | 3.00 | 0.00 | 932 | -1.52 | - | `modeled_committed_prefix_collision` | action_lag_over_model |
| 122822 | 3.00 | 2.00 | 0.00 | 573 | -2.54 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 130789 | 3.00 | 9.00 | 0.00 | 311 | -1.97 | - | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model |
| 131160 | 3.00 | 4.00 | 0.00 | 222 | 16.12 | - | `observed_bullet_overlap` | playfield_boundary |
| 141402 | 5.00 | 8.00 | 2.00 | 1118 | 8.45 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000,fast_mode |
| 142054 | 3.00 | 1.00 | 0.00 | 1279 | -1.29 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000 |
| 142690 | 3.00 | 9.00 | 0.00 | 1252 | 0.04 | - | `observed_bullet_overlap` | pool_density_over_1000 |
| 146918 | 3.00 | 5.00 | 0.00 | 1031 | -0.60 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 147878 | 3.00 | 2.00 | 0.00 | 1051 | 3.10 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000,fast_mode |
| 148733 | 3.00 | 1.00 | 0.00 | 799 | -5.37 | - | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model |
| 149121 | 3.00 | 0.00 | 0.00 | 998 | -6.52 | - | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model,fast_mode |
| 149540 | 4.00 | 12.00 | 1.00 | 991 | -3.21 | - | `observed_bullet_overlap` | playfield_boundary,action_lag_over_model,fast_mode |
| 149850 | 3.00 | 0.00 | 0.00 | 1000 | -10.41 | - | `modeled_committed_prefix_collision` | action_lag_over_model,pool_density_over_1000 |
| 150226 | 3.00 | 0.00 | 0.00 | 1008 | -6.23 | - | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model,pool_density_over_1000 |
| 150622 | 4.00 | 9.00 | 1.00 | 1000 | -8.06 | - | `observed_bullet_overlap` | action_lag_over_model,pool_density_over_1000 |
| 151106 | 3.00 | 0.00 | 0.00 | 996 | -2.12 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 151490 | 3.00 | 0.00 | 0.00 | 1001 | -5.73 | - | `modeled_committed_prefix_collision` | action_lag_over_model,pool_density_over_1000 |
| 151911 | 3.00 | 2.00 | 0.00 | 1015 | -4.72 | - | `modeled_committed_prefix_collision` | action_lag_over_model,pool_density_over_1000 |
| 152225 | 3.00 | 1.00 | 0.00 | 997 | -5.66 | - | `modeled_committed_prefix_collision` | action_lag_over_model |
| 152577 | 3.00 | 9.00 | 0.00 | 1007 | -7.07 | - | `modeled_committed_prefix_collision` | action_lag_over_model,pool_density_over_1000 |
| 156613 | 4.00 | 0.00 | 1.00 | 391 | 5.04 | - | `observed_bullet_overlap` | - |
| 157613 | 3.00 | 0.00 | 0.00 | 457 | -1.88 | - | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model |
| 158847 | 3.00 | 0.00 | 0.00 | 245 | 4.68 | - | `observed_bullet_overlap` | fast_mode |
| 159258 | 3.00 | 3.00 | 0.00 | 338 | -2.26 | - | `modeled_committed_prefix_collision` | action_lag_over_model |
| 159983 | 3.00 | 1.00 | 0.00 | 346 | 0.20 | - | `observed_bullet_overlap` | action_lag_over_model,fast_mode |
| 160394 | 3.00 | 1.00 | 0.00 | 339 | 3.36 | - | `observed_bullet_overlap` | action_lag_over_model,fast_mode |
| 161167 | 3.00 | 0.00 | 0.00 | 336 | 0.44 | - | `observed_bullet_overlap` | action_lag_over_model |
| 162140 | 4.00 | 15.00 | 1.00 | 1097 | 2.19 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000,fast_mode |
| 163343 | 4.00 | 1.00 | 1.00 | 966 | 5.21 | - | `observed_bullet_overlap` | playfield_boundary |
| 164302 | 3.00 | 0.00 | 0.00 | 1149 | 0.62 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000,fast_mode |

### Final B / Kaguya

- Death frames: 165485, 167409, 167957, 172607, 175820, 176188, 176527, 177180, 177690, 184199, 187012, 189189, 202010, 205638, 206163, 216337, 221344, 221846, 222335, 222830, 223336, 223814, 224324, 224848, 225397, 228273
- Cause counts: `{"observed_bullet_overlap": 9, "modeled_committed_prefix_collision": 16, "sensor_gap_or_unmodeled_hazard": 1}`
- Phase markers: observed 10, reachable static opcode `0x94` 14.
- Bottom/side occupancy decisions: 1653/1225.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 165485 | 3.00 | 7.00 | 0.00 | 629 | -2.66 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 167409 | 3.00 | 14.00 | 0.00 | 573 | -2.53 | - | `observed_bullet_overlap` | fast_mode |
| 167957 | 3.00 | 2.00 | 0.00 | 610 | -2.48 | - | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model |
| 172607 | 4.00 | 66.00 | 1.00 | 385 | -1.08 | - | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model |
| 175820 | 4.00 | 58.00 | 1.00 | 484 | 3.60 | - | `sensor_gap_or_unmodeled_hazard` | playfield_boundary,action_lag_over_model,fast_mode |
| 176188 | 4.00 | 43.00 | 1.00 | 596 | -0.98 | - | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model |
| 176527 | 3.00 | 27.00 | 0.00 | 621 | 4.28 | - | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model |
| 177180 | 4.00 | 20.00 | 1.00 | 672 | -0.57 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 177690 | 4.00 | 7.00 | 1.00 | 76 | -1.90 | - | `modeled_committed_prefix_collision` | - |
| 184199 | 3.00 | 3.00 | 0.00 | 1088 | 0.49 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000,fast_mode |
| 187012 | 4.00 | 0.00 | 1.00 | 125 | -2.65 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 189189 | 3.00 | 1.00 | 0.00 | 112 | -2.17 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 202010 | 3.00 | 1.00 | 0.00 | 645 | -3.95 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 205638 | 3.00 | 2.00 | 0.00 | 530 | 0.02 | - | `observed_bullet_overlap` | - |
| 206163 | 3.00 | 0.00 | 0.00 | 576 | -2.77 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 216337 | 3.00 | 0.00 | 0.00 | 478 | -0.64 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 221344 | 3.00 | 10.00 | 0.00 | 558 | -1.49 | - | `modeled_committed_prefix_collision` | fast_mode |
| 221846 | 3.00 | 1.00 | 0.00 | 559 | -2.10 | - | `observed_bullet_overlap` | playfield_boundary |
| 222335 | 3.00 | 1.00 | 0.00 | 563 | -1.70 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 222830 | 3.00 | 3.00 | 0.00 | 562 | -2.06 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 223336 | 4.00 | 9.00 | 1.00 | 572 | -1.71 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 223814 | 3.00 | 0.00 | 0.00 | 558 | -2.54 | - | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model,fast_mode |
| 224324 | 3.00 | 9.00 | 0.00 | 561 | -0.30 | - | `observed_bullet_overlap` | playfield_boundary |
| 224848 | 3.00 | 9.00 | 0.00 | 573 | 0.80 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 225397 | 3.00 | 2.00 | 0.00 | 560 | -2.39 | - | `observed_bullet_overlap` | playfield_boundary |
| 228273 | 3.00 | 15.00 | 0.00 | 884 | -0.81 | - | `modeled_committed_prefix_collision` | playfield_boundary |

## Spell Inventory And Runtime Coverage

Every spell below is statically reachable for route 2 Lunatic Final B. Observed decisions count only rows whose live spell state reported that active spell ID. Zero decisions therefore means the run did not enter that spell; zero hits with nonzero decisions means it entered cleanly. `unresolved` means the trace schema did not persist enough live spell state.

### Stage 1

- ECL: `ecldata1.ecl`
- Observed/expected phase-counter markers: 3/4.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 1 | 蛍符「地上の彗星」 | リグル・ナイトバグ | 3 | 6 | 0 | yes | 593 | 1 |
| 5 | 灯符「ファイヤフライフェノメノン」 | リグル・ナイトバグ | 11 | 6 | 0 | yes | 554 | 1 |
| 9 | 蠢符「ナイトバグトルネード」 | リグル・ナイトバグ | 13 | 27 | 0 | yes | 673 | 0 |
| 12 | 隠蟲「永夜蟄居」 | リグル・ナイトバグ | 12 | 27 | 0 | no | 0 | 0 |

### Stage 2

- ECL: `ecldata2.ecl`
- Observed/expected phase-counter markers: 2/3.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 16 | 声符「木菟咆哮」 | ミスティア・ローレライ | 4 | 7 | 0 | yes | 504 | 0 |
| 20 | 猛毒「毒蛾の暗闇演舞」 | ミスティア・ローレライ | 5 | 7 | 0 | yes | 614 | 0 |
| 24 | 鷹符「イルスタードダイブ」 | ミスティア・ローレライ | 6 | 8 | 0 | yes | 604 | 0 |
| 28 | 夜盲「夜雀の歌」 | ミスティア・ローレライ | 8 | 9 | 0 | yes | 676 | 0 |
| 31 | 夜雀「真夜中のコーラスマスター」 | ミスティア・ローレライ | 3 | 7 | 0 | no | 0 | 0 |

### Stage 3

- ECL: `ecldata3.ecl`
- Observed/expected phase-counter markers: 3/4.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 35 | 産霊「ファーストピラミッド」 | 上白沢慧音 | 3 | 0 | 0 | yes | 687 | 1 |
| 38 | 始符「エフェメラリティ137」 | 上白沢慧音 | 2 | 2 | 0 | yes | 606 | 0 |
| 42 | 野符「GHQクライシス」 | 上白沢慧音 | 3 | 3 | 0 | yes | 567 | 0 |
| 46 | 国体「三種の神器　郷」 | 上白沢慧音 | 3 | 0 | 0 | yes | 635 | 0 |
| 50 | 虚史「幻想郷伝説」 | 上白沢慧音 | 1 | 0 | 1 | yes | 525 | 0 |
| 53 | 未来「高天原」 | 上白沢慧音 | 1 | 0 | 1 | no | 0 | 0 |

### Stage 4A / Reimu

- ECL: `ecldata4a.ecl`
- Observed/expected phase-counter markers: 7/8.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 57 | 夢境「二重大結界」 | 博麗霊夢 | 3 | 0 | 0 | yes | 955 | 4 |
| 61 | 散霊「夢想封印　寂」 | 博麗霊夢 | 3 | 0 | 0 | yes | 872 | 0 |
| 65 | 神技「八方龍殺陣」 | 博麗霊夢 | 7 | 27 | 0 | yes | 631 | 1 |
| 69 | 回霊「夢想封印　侘」 | 博麗霊夢 | 2 | 17 | 0 | yes | 878 | 4 |
| 73 | 大結界「博麗弾幕結界」 | 博麗霊夢 | 5 | 4 | 0 | yes | 888 | 3 |
| 76 | 神霊「夢想封印　瞬」 | 博麗霊夢 | 2 | 5 | 0 | no | 0 | 0 |

### Stage 5

- ECL: `ecldata5.ecl`
- Observed/expected phase-counter markers: 7/8.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 103 | 幻波「赤眼催眠(マインドブローイング)」 | 鈴仙・Ｕ・イナバ | 6 | 0 | 0 | yes | 584 | 3 |
| 111 | 懶惰「生神停止(マインドストッパー)」 | 鈴仙・Ｕ・イナバ | 3 | 0 | 0 | yes | 718 | 5 |
| 107 | 狂視「狂視調律(イリュージョンシーカー)」 | 鈴仙・Ｕ・イナバ | 3 | 3 | 0 | yes | 766 | 11 |
| 115 | 散符「真実の月(インビジブルフルムーン)」 | 鈴仙・Ｕ・イナバ | 6 | 3 | 0 | yes | 727 | 3 |
| 118 | 月眼「月兎遠隔催眠術(テレメスメリズム)」 | 鈴仙・Ｕ・イナバ | 4 | 2 | 0 | no | 0 | 0 |

### Final B / Kaguya

- ECL: `ecldata7.ecl`
- Observed/expected phase-counter markers: 10/14.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 150 | 薬符「壺中の大銀河」 | 八意永琳 | 4 | 0 | 0 | yes | 590 | 5 |
| 154 | 神宝「ブリリアントドラゴンバレッタ」 | 蓬莱山輝夜 | 5 | 1 | 5 | yes | 983 | 2 |
| 158 | 神宝「ブディストダイアモンド」 | 蓬莱山輝夜 | 4 | 4 | 2 | yes | 1187 | 0 |
| 162 | 神宝「サラマンダーシールド」 | 蓬莱山輝夜 | 4 | 8 | 2 | yes | 1338 | 2 |
| 166 | 神宝「ライフスプリングインフィニティ」 | 蓬莱山輝夜 | 3 | 2 | 2 | yes | 1194 | 1 |
| 170 | 神宝「蓬莱の玉の枝  -夢色の郷-」 | 蓬莱山輝夜 | 26 | 3 | 0 | yes | 1670 | 9 |
| 174 | 「永夜返し  -待宵-」 | 蓬莱山輝夜 | 3 | 1 | 0 | yes | 202 | 1 |
| 178 | 「永夜返し  -子の四つ-」 | 蓬莱山輝夜 | 3 | 2 | 0 | no | 0 | 0 |
| 182 | 「永夜返し  -丑の四つ-」 | 蓬莱山輝夜 | 2 | 2 | 0 | no | 0 | 0 |
| 186 | 「永夜返し  -寅の四つ-」 | 蓬莱山輝夜 | 4 | 4 | 0 | no | 0 | 0 |
| 190 | 「永夜返し  -世明け-」 | 蓬莱山輝夜 | 12 | 5 | 0 | no | 0 | 0 |

## Runtime And Harness Findings

- Observed auto-Z stall frames: none.
- Route termination: `route_complete` at completion probe frame 228477.
- Unique robust solutions observed: 0; solve time median/p95/max -/-/- ms.
- First-observed policy age median/p95/max: -/-/- frames.
- Viability queries available: 0/0; robustly constrained decisions: 0/50669.
- Robust-policy decisions without any usable query: 0/0.
- Global-horizon/local-prefix cross-tab: 0 decisions; winning global state with unsafe selected prefix: 0; losing global state with safe short prefix: 0; selected globally certified action contradicted by the fresh local prefix checker: 0; selected action outside the reported winning set: 0.
- Live spell attribution was recorded at every hit edge; exact per-spell counts are preserved below.
- `4` hit edges remain in the `sensor_gap_or_unmodeled_hazard` class and require executor-level same-frame emission/transform evidence.

## Next Regression Work

1. Keep robust backward-reachability solves within the finite policy horizon, then verify nonzero live query and constrained-decision counts.
2. Replay all 93 retained witnesses through the integrated executor and preserve one regression per concrete failure.
3. Re-run focused Stage 4A and Final B practices before another full Lunatic route; compare hit frames, policy age, action-set exhaustion, and cluster recurrence.
4. Add item/Power state and finite Bomb resources only after the no-Bomb movement policy has passed physical validation.
