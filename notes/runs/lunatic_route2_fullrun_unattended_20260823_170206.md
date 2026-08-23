# TH08 Lunatic Full-Run Review: lunatic_route2_fullrun_unattended_20260823_170206

## Result

- Route: Sakuya/Remilia, Lunatic, Final B / Kaguya.
- Combat completion: yes; gameplay scene unloaded at frame 231289.
- Native phase-2 hit edges, including Last-Spell-saveable edges: 85.
- Deathbomb requests at those edges: 0.
- Hard no-Bomb input verification: passed across 51411 decisions.
- Post-hit Bomb-stock decreases: 17.00; this is respawn-stock reset telemetry, not evidence of Bomb input.
- Agent decisions: 51411.
- Raw trace size: 2041772078 bytes across 1 segments.
- JSON decode errors: 0.
- Exact spell-level hit attribution: available from live `g_spell_card_state`.

The run is valid for stage-, death-, resource-, projectile-, latency-, and route-level analysis. Spell names below are the statically reachable Lunatic route inventory; unavailable runtime hit counts remain explicitly unresolved instead of guessed. The no-life patch allows post-hit resource resets to repeat, so resource-stock changes must not be interpreted as Bomb commands.

## Trace Integrity

| Segment | Frames | Decisions | Wall Z | Termination | Runtime error | SHA-256 |
| --- | ---: | ---: | ---: | --- | --- | --- |
| 1 | 2..231289 | 51411 | 429 | route_complete | - | `06d3473bae979b450e7ac1f7f3723687c114e054188f69d2c2b44aeb77290a11` |

The route is one continuous agent-controlled trace with no foreground interruption or manual re-arm gap.

## Stage Summary

| Stage | Frames | Decisions | Native hits | Deathbombs | Post-hit Bomb-stock decrease | Power start/end/min | Max bullets | Max lasers |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Stage 1 | 2..20979 | 4818 | 1 | 0 | 0.00 | 0.00/0.00/0.00 | 1176 | 0 |
| Stage 2 | 20979..44796 | 6326 | 8 | 0 | 2.00 | 5.00/5.00/0.00 | 1195 | 0 |
| Stage 3 | 44796..72807 | 6850 | 14 | 0 | 4.00 | 11.00/0.00/0.00 | 1188 | 200 |
| Stage 4A / Reimu | 72807..118513 | 10391 | 14 | 0 | 1.00 | 18.00/1.00/0.00 | 1361 | 0 |
| Stage 5 | 118513..164131 | 8702 | 18 | 0 | 5.00 | 6.00/8.00/0.00 | 1513 | 0 |
| Final B / Kaguya | 164133..231289 | 14324 | 30 | 0 | 5.00 | 13.00/16.00/0.00 | 1224 | 245 |

## Failure Taxonomy

| Primary class | Deaths | Interpretation |
| --- | ---: | --- |
| `modeled_committed_prefix_collision` | 53 | The measured three-frame input pipeline was already unsafe. |
| `observed_bullet_overlap` | 26 | A bullet overlaps the native player AABB in the hit observation. |
| `observed_laser_overlap` | 4 | The player overlaps an active laser's exact finite segment; TH08 checks this before the broad bullet pass. |
| `sensor_gap_or_unmodeled_hazard` | 2 | No observed overlap and positive pipeline clearance; same-frame ECL emission, transform error, or another unmodeled hazard is the leading explanation. |

Contributing factors:

- `playfield_boundary`: 68 deaths
- `fast_mode`: 56 deaths
- `corridor_deadline_miss`: 26 deaths
- `pool_density_over_1000`: 10 deaths
- `action_lag_over_model`: 5 deaths

## High-Risk Clusters

| Cluster | Stage | Frames | Deaths | Min Power | Max bullets at hit |
| --- | --- | ---: | ---: | ---: | ---: |
| cluster-59 | Final B / Kaguya | 221127..224114 | 7 | 0.00 | 566 |
| cluster-14 | Stage 3 | 71086..72642 | 5 | 0.00 | 281 |
| cluster-09 | Stage 3 | 47284..48520 | 4 | 0.00 | 526 |
| cluster-46 | Final B / Kaguya | 176403..177091 | 3 | 39.00 | 666 |
| cluster-05 | Stage 2 | 39103..39508 | 2 | 2.00 | 155 |
| cluster-12 | Stage 3 | 61362..61719 | 2 | 14.00 | 233 |
| cluster-17 | Stage 4A / Reimu | 84306..84785 | 2 | 7.00 | 632 |
| cluster-22 | Stage 4A / Reimu | 95340..95847 | 2 | 3.00 | 804 |
| cluster-51 | Final B / Kaguya | 187122..187596 | 2 | 0.00 | 120 |
| cluster-52 | Final B / Kaguya | 188207..188722 | 2 | 0.00 | 123 |
| cluster-58 | Final B / Kaguya | 216809..217377 | 2 | 1.00 | 493 |
| cluster-60 | Final B / Kaguya | 224718..225193 | 2 | 1.00 | 587 |

## Stage Detail

### Stage 1

- Death frames: 14813
- Cause counts: `{"modeled_committed_prefix_collision": 1}`
- Phase markers: observed 3, reachable static opcode `0x94` 4.
- Bottom/side occupancy decisions: 283/267.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 14813 | 3.00 | 11.00 | 0.00 | 457 | -4.05 | - | `modeled_committed_prefix_collision` | playfield_boundary |

### Stage 2

- Death frames: 21936, 23958, 25723, 39103, 39508, 40758, 41596, 44292
- Cause counts: `{"modeled_committed_prefix_collision": 5, "observed_bullet_overlap": 3}`
- Phase markers: observed 2, reachable static opcode `0x94` 3.
- Bottom/side occupancy decisions: 839/618.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 21936 | 4.00 | 8.00 | 1.00 | 109 | -1.33 | 1.73 | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 23958 | 3.00 | 6.00 | 0.00 | 440 | -2.27 | -17.46 | `modeled_committed_prefix_collision` | corridor_deadline_miss,fast_mode |
| 25723 | 4.00 | 11.00 | 1.00 | 225 | -2.83 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 39103 | 3.00 | 3.00 | 0.00 | 82 | -4.56 | -6.94 | `observed_bullet_overlap` | playfield_boundary,corridor_deadline_miss,fast_mode |
| 39508 | 3.00 | 2.00 | 0.00 | 155 | -3.03 | 12.19 | `modeled_committed_prefix_collision` | playfield_boundary |
| 40758 | 3.00 | 2.00 | 0.00 | 353 | -2.87 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 41596 | 3.00 | 9.00 | 0.00 | 403 | -1.66 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 44292 | 3.00 | 20.00 | 0.00 | 542 | -1.36 | - | `observed_bullet_overlap` | - |

### Stage 3

- Death frames: 47284, 47691, 48145, 48520, 52888, 54048, 61362, 61719, 68921, 71086, 71433, 71730, 72083, 72642
- Cause counts: `{"modeled_committed_prefix_collision": 11, "observed_bullet_overlap": 2, "observed_laser_overlap": 1}`
- Phase markers: observed 3, reachable static opcode `0x94` 4.
- Bottom/side occupancy decisions: 970/652.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 47284 | 3.00 | 17.00 | 0.00 | 218 | -2.92 | - | `modeled_committed_prefix_collision` | fast_mode |
| 47691 | 3.00 | 2.00 | 0.00 | 526 | -1.47 | -31.40 | `modeled_committed_prefix_collision` | playfield_boundary,corridor_deadline_miss |
| 48145 | 3.00 | 1.00 | 0.00 | 526 | -2.47 | -4.12 | `modeled_committed_prefix_collision` | playfield_boundary,corridor_deadline_miss,fast_mode |
| 48520 | 3.00 | 0.00 | 0.00 | 519 | -2.43 | -2.76 | `modeled_committed_prefix_collision` | playfield_boundary,corridor_deadline_miss,fast_mode |
| 52888 | 3.00 | 8.00 | 0.00 | 693 | -2.30 | -5.37 | `observed_bullet_overlap` | playfield_boundary,corridor_deadline_miss |
| 54048 | 3.00 | 0.00 | 0.00 | 569 | -1.83 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 61362 | 5.00 | 30.00 | 2.00 | 233 | -1.45 | -2.15 | `modeled_committed_prefix_collision` | playfield_boundary,corridor_deadline_miss |
| 61719 | 3.00 | 14.00 | 0.00 | 167 | -1.70 | -8.50 | `modeled_committed_prefix_collision` | playfield_boundary,corridor_deadline_miss,fast_mode |
| 68921 | 4.00 | 19.00 | 1.00 | 370 | -1.37 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 71086 | 4.00 | 4.00 | 1.00 | 236 | -2.66 | 4.50 | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model,fast_mode |
| 71433 | 3.00 | 0.00 | 0.00 | 257 | -3.60 | 0.57 | `observed_laser_overlap` | playfield_boundary,fast_mode |
| 71730 | 3.00 | 9.00 | 0.00 | 281 | -3.61 | 11.29 | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 72083 | 3.00 | 10.00 | 0.00 | 270 | -0.49 | 6.64 | `observed_bullet_overlap` | playfield_boundary |
| 72642 | 3.00 | 2.00 | 0.00 | 250 | -4.29 | - | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model |

### Stage 4A / Reimu

- Death frames: 74641, 76980, 84306, 84785, 85949, 86702, 93156, 93839, 95340, 95847, 111443, 112366, 113372, 116132
- Cause counts: `{"observed_bullet_overlap": 8, "modeled_committed_prefix_collision": 6}`
- Phase markers: observed 7, reachable static opcode `0x94` 8.
- Bottom/side occupancy decisions: 1363/1131.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 74641 | 4.00 | 25.00 | 1.00 | 419 | -15.75 | - | `observed_bullet_overlap` | playfield_boundary |
| 76980 | 3.00 | 19.00 | 0.00 | 1112 | -1.80 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 84306 | 3.00 | 7.00 | 0.00 | 467 | -1.46 | -7.83 | `modeled_committed_prefix_collision` | playfield_boundary,corridor_deadline_miss,fast_mode |
| 84785 | 3.00 | 9.00 | 0.00 | 632 | -1.46 | -12.16 | `modeled_committed_prefix_collision` | playfield_boundary,corridor_deadline_miss,fast_mode |
| 85949 | 3.00 | 1.00 | 0.00 | 619 | -0.43 | 0.50 | `observed_bullet_overlap` | fast_mode |
| 86702 | 3.00 | 1.00 | 0.00 | 611 | 1.05 | -1.77 | `observed_bullet_overlap` | playfield_boundary,corridor_deadline_miss,fast_mode |
| 93156 | 3.00 | 0.00 | 0.00 | 263 | 0.55 | 14.99 | `observed_bullet_overlap` | fast_mode |
| 93839 | 3.00 | 8.00 | 0.00 | 928 | -1.48 | 2.91 | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 95340 | 3.00 | 3.00 | 0.00 | 804 | -1.75 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 95847 | 3.00 | 9.00 | 0.00 | 570 | -0.00 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 111443 | 3.00 | 13.00 | 0.00 | 531 | -0.59 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 112366 | 3.00 | 3.00 | 0.00 | 695 | -0.87 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 113372 | 3.00 | 1.00 | 0.00 | 712 | -1.72 | - | `observed_bullet_overlap` | fast_mode |
| 116132 | 3.00 | 1.00 | 0.00 | 990 | -1.96 | -6.13 | `observed_bullet_overlap` | corridor_deadline_miss,fast_mode |

### Stage 5

- Death frames: 120659, 122004, 122892, 129750, 130932, 132673, 141871, 142550, 146411, 147890, 149709, 150531, 155373, 157506, 158734, 160587, 162153, 163441
- Cause counts: `{"modeled_committed_prefix_collision": 12, "observed_bullet_overlap": 5, "sensor_gap_or_unmodeled_hazard": 1}`
- Phase markers: observed 7, reachable static opcode `0x94` 8.
- Bottom/side occupancy decisions: 2135/866.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 120659 | 3.00 | 6.00 | 0.00 | 645 | -2.93 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 122004 | 4.00 | 4.00 | 1.00 | 972 | -2.24 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 122892 | 4.00 | 1.00 | 1.00 | 583 | -0.90 | - | `observed_bullet_overlap` | playfield_boundary |
| 129750 | 3.00 | 1.00 | 0.00 | 905 | 0.67 | - | `sensor_gap_or_unmodeled_hazard` | playfield_boundary,fast_mode |
| 130932 | 3.00 | 8.00 | 0.00 | 332 | -1.44 | 5.47 | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 132673 | 3.00 | 0.00 | 0.00 | 532 | -1.46 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 141871 | 5.00 | 11.00 | 2.00 | 992 | -2.54 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 142550 | 3.00 | 0.00 | 0.00 | 1079 | -1.76 | 4.15 | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000,fast_mode |
| 146411 | 3.00 | 3.00 | 0.00 | 1025 | -1.48 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000,fast_mode |
| 147890 | 3.00 | 2.00 | 0.00 | 1062 | -1.69 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000,fast_mode |
| 149709 | 3.00 | 0.00 | 0.00 | 920 | -6.88 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 150531 | 3.00 | 0.00 | 0.00 | 1021 | -7.50 | - | `modeled_committed_prefix_collision` | pool_density_over_1000,fast_mode |
| 155373 | 4.00 | 3.00 | 1.00 | 411 | -1.93 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 157506 | 3.00 | 1.00 | 0.00 | 461 | -2.51 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 158734 | 3.00 | 1.00 | 0.00 | 363 | -2.96 | 1.25 | `modeled_committed_prefix_collision` | fast_mode |
| 160587 | 3.00 | 9.00 | 0.00 | 333 | -2.05 | -2.59 | `modeled_committed_prefix_collision` | corridor_deadline_miss,fast_mode |
| 162153 | 3.00 | 14.00 | 0.00 | 1158 | -2.02 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 163441 | 3.00 | 1.00 | 0.00 | 1156 | -3.42 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000 |

### Final B / Kaguya

- Death frames: 173071, 176403, 176767, 177091, 177753, 183016, 183629, 186479, 187122, 187596, 188207, 188722, 196363, 197749, 204356, 206315, 216078, 216809, 217377, 221127, 221625, 222117, 222605, 223097, 223590, 224114, 224718, 225193, 228139, 231116
- Cause counts: `{"modeled_committed_prefix_collision": 18, "observed_bullet_overlap": 8, "observed_laser_overlap": 3, "sensor_gap_or_unmodeled_hazard": 1}`
- Phase markers: observed 11, reachable static opcode `0x94` 14.
- Bottom/side occupancy decisions: 1840/1508.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 173071 | 3.00 | 77.00 | 0.00 | 762 | -1.82 | 7.63 | `modeled_committed_prefix_collision` | playfield_boundary |
| 176403 | 4.00 | 71.00 | 1.00 | 666 | -3.09 | -7.79 | `modeled_committed_prefix_collision` | playfield_boundary,corridor_deadline_miss,fast_mode |
| 176767 | 3.00 | 55.00 | 0.00 | 619 | -2.27 | -7.08 | `modeled_committed_prefix_collision` | playfield_boundary,corridor_deadline_miss |
| 177091 | 3.00 | 39.00 | 0.00 | 612 | -0.67 | -3.47 | `observed_bullet_overlap` | playfield_boundary,corridor_deadline_miss |
| 177753 | 3.00 | 23.00 | 0.00 | 681 | -1.44 | -27.38 | `modeled_committed_prefix_collision` | playfield_boundary,corridor_deadline_miss,fast_mode |
| 183016 | 3.00 | 16.00 | 0.00 | 1199 | -3.59 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000 |
| 183629 | 3.00 | 1.00 | 0.00 | 1135 | 0.82 | -8.43 | `observed_bullet_overlap` | playfield_boundary,corridor_deadline_miss,pool_density_over_1000,fast_mode |
| 186479 | 3.00 | 9.00 | 0.00 | 93 | -4.95 | - | `observed_laser_overlap` | action_lag_over_model |
| 187122 | 3.00 | 2.00 | 0.00 | 120 | -3.25 | 9.98 | `modeled_committed_prefix_collision` | playfield_boundary |
| 187596 | 3.00 | 0.00 | 0.00 | 108 | 0.45 | -3.48 | `observed_bullet_overlap` | playfield_boundary,corridor_deadline_miss,fast_mode |
| 188207 | 3.00 | 0.00 | 0.00 | 111 | -5.04 | - | `modeled_committed_prefix_collision` | action_lag_over_model |
| 188722 | 4.00 | 0.00 | 1.00 | 123 | -3.59 | - | `modeled_committed_prefix_collision` | action_lag_over_model,fast_mode |
| 196363 | 3.00 | 3.00 | 0.00 | 260 | -2.80 | - | `observed_bullet_overlap` | - |
| 197749 | 4.00 | 0.00 | 1.00 | 237 | -1.65 | - | `observed_laser_overlap` | playfield_boundary,fast_mode |
| 204356 | 3.00 | 8.00 | 0.00 | 689 | -2.52 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 206315 | 3.00 | 1.00 | 0.00 | 532 | -2.91 | - | `observed_laser_overlap` | playfield_boundary,fast_mode |
| 216078 | 3.00 | 0.00 | 0.00 | 457 | -4.31 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 216809 | 3.00 | 1.00 | 0.00 | 453 | -0.86 | - | `observed_bullet_overlap` | - |
| 217377 | 3.00 | 1.00 | 0.00 | 493 | -2.96 | - | `modeled_committed_prefix_collision` | - |
| 221127 | 4.00 | 18.00 | 1.00 | 554 | -1.47 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 221625 | 3.00 | 10.00 | 0.00 | 555 | -1.94 | -2.56 | `modeled_committed_prefix_collision` | corridor_deadline_miss |
| 222117 | 3.00 | 9.00 | 0.00 | 559 | -2.98 | -23.87 | `modeled_committed_prefix_collision` | playfield_boundary,corridor_deadline_miss |
| 222605 | 3.00 | 3.00 | 0.00 | 559 | -0.49 | -26.77 | `modeled_committed_prefix_collision` | playfield_boundary,corridor_deadline_miss |
| 223097 | 3.00 | 0.00 | 0.00 | 561 | -1.71 | -27.09 | `modeled_committed_prefix_collision` | playfield_boundary,corridor_deadline_miss,fast_mode |
| 223590 | 3.00 | 4.00 | 0.00 | 566 | -3.16 | -19.87 | `observed_bullet_overlap` | playfield_boundary,corridor_deadline_miss |
| 224114 | 3.00 | 0.00 | 0.00 | 563 | -3.43 | -3.71 | `modeled_committed_prefix_collision` | playfield_boundary,corridor_deadline_miss,fast_mode |
| 224718 | 3.00 | 3.00 | 0.00 | 587 | -2.48 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 225193 | 4.00 | 1.00 | 1.00 | 568 | -3.92 | -9.10 | `modeled_committed_prefix_collision` | playfield_boundary,corridor_deadline_miss,fast_mode |
| 228139 | 4.00 | 16.00 | 0.00 | 872 | 0.36 | - | `sensor_gap_or_unmodeled_hazard` | playfield_boundary,fast_mode |
| 231116 | 4.00 | 16.00 | 0.00 | 1023 | -2.68 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000,fast_mode |

## Spell Inventory And Runtime Coverage

Every spell below is statically reachable for route 2 Lunatic Final B. Observed decisions count only rows whose live spell state reported that active spell ID. Zero decisions therefore means the run did not enter that spell; zero hits with nonzero decisions means it entered cleanly. `unresolved` means the trace schema did not persist enough live spell state.

### Stage 1

- ECL: `ecldata1.ecl`
- Observed/expected phase-counter markers: 3/4.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 1 | 蛍符「地上の彗星」 | リグル・ナイトバグ | 3 | 6 | 0 | yes | 638 | 0 |
| 5 | 灯符「ファイヤフライフェノメノン」 | リグル・ナイトバグ | 11 | 6 | 0 | yes | 561 | 1 |
| 9 | 蠢符「ナイトバグトルネード」 | リグル・ナイトバグ | 13 | 27 | 0 | yes | 642 | 0 |
| 12 | 隠蟲「永夜蟄居」 | リグル・ナイトバグ | 12 | 27 | 0 | no | 0 | 0 |

### Stage 2

- ECL: `ecldata2.ecl`
- Observed/expected phase-counter markers: 2/3.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 16 | 声符「木菟咆哮」 | ミスティア・ローレライ | 4 | 7 | 0 | yes | 487 | 0 |
| 20 | 猛毒「毒蛾の暗闇演舞」 | ミスティア・ローレライ | 5 | 7 | 0 | yes | 622 | 0 |
| 24 | 鷹符「イルスタードダイブ」 | ミスティア・ローレライ | 6 | 8 | 0 | yes | 634 | 2 |
| 28 | 夜盲「夜雀の歌」 | ミスティア・ローレライ | 8 | 9 | 0 | yes | 787 | 1 |
| 31 | 夜雀「真夜中のコーラスマスター」 | ミスティア・ローレライ | 3 | 7 | 0 | no | 0 | 0 |

### Stage 3

- ECL: `ecldata3.ecl`
- Observed/expected phase-counter markers: 3/4.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 35 | 産霊「ファーストピラミッド」 | 上白沢慧音 | 3 | 0 | 0 | yes | 681 | 0 |
| 38 | 始符「エフェメラリティ137」 | 上白沢慧音 | 2 | 2 | 0 | yes | 634 | 2 |
| 42 | 野符「GHQクライシス」 | 上白沢慧音 | 3 | 3 | 0 | yes | 583 | 0 |
| 46 | 国体「三種の神器　郷」 | 上白沢慧音 | 3 | 0 | 0 | yes | 668 | 1 |
| 50 | 虚史「幻想郷伝説」 | 上白沢慧音 | 1 | 0 | 1 | yes | 448 | 5 |
| 53 | 未来「高天原」 | 上白沢慧音 | 1 | 0 | 1 | no | 0 | 0 |

### Stage 4A / Reimu

- ECL: `ecldata4a.ecl`
- Observed/expected phase-counter markers: 7/8.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 57 | 夢境「二重大結界」 | 博麗霊夢 | 3 | 0 | 0 | yes | 971 | 4 |
| 61 | 散霊「夢想封印　寂」 | 博麗霊夢 | 3 | 0 | 0 | yes | 975 | 2 |
| 65 | 神技「八方龍殺陣」 | 博麗霊夢 | 7 | 27 | 0 | yes | 680 | 0 |
| 69 | 回霊「夢想封印　侘」 | 博麗霊夢 | 2 | 17 | 0 | yes | 875 | 3 |
| 73 | 大結界「博麗弾幕結界」 | 博麗霊夢 | 5 | 4 | 0 | yes | 859 | 1 |
| 76 | 神霊「夢想封印　瞬」 | 博麗霊夢 | 2 | 5 | 0 | no | 0 | 0 |

### Stage 5

- ECL: `ecldata5.ecl`
- Observed/expected phase-counter markers: 7/8.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 103 | 幻波「赤眼催眠(マインドブローイング)」 | 鈴仙・Ｕ・イナバ | 6 | 0 | 0 | yes | 709 | 2 |
| 111 | 懶惰「生神停止(マインドストッパー)」 | 鈴仙・Ｕ・イナバ | 3 | 0 | 0 | yes | 791 | 2 |
| 107 | 狂視「狂視調律(イリュージョンシーカー)」 | 鈴仙・Ｕ・イナバ | 3 | 3 | 0 | yes | 762 | 2 |
| 115 | 散符「真実の月(インビジブルフルムーン)」 | 鈴仙・Ｕ・イナバ | 6 | 3 | 0 | yes | 804 | 2 |
| 118 | 月眼「月兎遠隔催眠術(テレメスメリズム)」 | 鈴仙・Ｕ・イナバ | 4 | 2 | 0 | no | 0 | 0 |

### Final B / Kaguya

- ECL: `ecldata7.ecl`
- Observed/expected phase-counter markers: 11/14.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 150 | 薬符「壺中の大銀河」 | 八意永琳 | 4 | 0 | 0 | yes | 673 | 4 |
| 154 | 神宝「ブリリアントドラゴンバレッタ」 | 蓬莱山輝夜 | 5 | 1 | 5 | yes | 605 | 5 |
| 158 | 神宝「ブディストダイアモンド」 | 蓬莱山輝夜 | 4 | 4 | 2 | yes | 1285 | 2 |
| 162 | 神宝「サラマンダーシールド」 | 蓬莱山輝夜 | 4 | 8 | 2 | yes | 1335 | 1 |
| 166 | 神宝「ライフスプリングインフィニティ」 | 蓬莱山輝夜 | 3 | 2 | 2 | yes | 1185 | 3 |
| 170 | 神宝「蓬莱の玉の枝  -夢色の郷-」 | 蓬莱山輝夜 | 26 | 3 | 0 | yes | 1606 | 9 |
| 174 | 「永夜返し  -待宵-」 | 蓬莱山輝夜 | 3 | 1 | 0 | yes | 221 | 1 |
| 178 | 「永夜返し  -子の四つ-」 | 蓬莱山輝夜 | 3 | 2 | 0 | yes | 305 | 1 |
| 182 | 「永夜返し  -丑の四つ-」 | 蓬莱山輝夜 | 2 | 2 | 0 | no | 0 | 0 |
| 186 | 「永夜返し  -寅の四つ-」 | 蓬莱山輝夜 | 4 | 4 | 0 | no | 0 | 0 |
| 190 | 「永夜返し  -世明け-」 | 蓬莱山輝夜 | 12 | 5 | 0 | no | 0 | 0 |

## Runtime And Harness Findings

- Observed auto-Z stall frames: none.
- Route termination: `route_complete` at completion probe frame 231289.
- Unique robust solutions observed: 9894; solve time median/p95/max 122.08/283.18/412.19 ms.
- First-observed policy age median/p95/max: 4.00/7.00/1804.00 frames.
- Viability queries available: 50760/50760; robustly constrained decisions: 0/51411.
- Robust-policy decisions without any usable query: 427/51187.
- Global-horizon/local-prefix cross-tab: 30791 decisions; winning global state with unsafe selected prefix: 1; losing global state with safe short prefix: 22171; selected globally certified action contradicted by the fresh local prefix checker: 1; selected action outside the reported winning set: 567.
- Live spell attribution was recorded at every hit edge; exact per-spell counts are preserved below.
- `2` hit edges remain in the `sensor_gap_or_unmodeled_hazard` class and require executor-level same-frame emission/transform evidence.

## Next Regression Work

1. Keep robust backward-reachability solves within the finite policy horizon, then verify nonzero live query and constrained-decision counts.
2. Replay all 85 retained witnesses through the integrated executor and preserve one regression per concrete failure.
3. Re-run focused Stage 4A and Final B practices before another full Lunatic route; compare hit frames, policy age, action-set exhaustion, and cluster recurrence.
4. Add item/Power state and finite Bomb resources only after the no-Bomb movement policy has passed physical validation.
