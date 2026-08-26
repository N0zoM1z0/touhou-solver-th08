# TH08 Easy Full-Run Review: easy_route2_fullrun_unattended_20260825_101715

## Result

- Route: Sakuya/Remilia, Easy, Final B / Kaguya.
- Combat completion: yes; gameplay scene unloaded at frame 213264.
- Native phase-2 hit edges, including Last-Spell-saveable edges: 13.
- Deathbomb requests at those edges: 0.
- Hard no-Bomb input verification: passed across 49325 decisions.
- Post-hit Bomb-stock decreases: 7.00; this is respawn-stock reset telemetry, not evidence of Bomb input.
- Agent decisions: 49325.
- Raw trace size: 1493957622 bytes across 1 segments.
- JSON decode errors: 0.
- Exact spell-level hit attribution: available from live `g_spell_card_state`.

The run is valid for stage-, death-, resource-, projectile-, latency-, and route-level analysis. Spell names below are the statically reachable Easy route inventory; unavailable runtime hit counts remain explicitly unresolved instead of guessed. The no-life patch allows post-hit resource resets to repeat, so resource-stock changes must not be interpreted as Bomb commands.

## Trace Integrity

| Segment | Frames | Decisions | Wall Z | Termination | Runtime error | SHA-256 |
| --- | ---: | ---: | ---: | --- | --- | --- |
| 1 | 1..213262 | 49325 | 422 | route_complete | - | `7628b132f2c80e8da07aa48d49f7a8bd8a61609abb5d46dc4c9ff62c9eea3fd9` |

The route is one continuous agent-controlled trace with no foreground interruption or manual re-arm gap.

## Stage Summary

| Stage | Frames | Decisions | Native hits | Deathbombs | Post-hit Bomb-stock decrease | Power start/end/min | Max bullets | Max lasers |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Stage 1 | 1..16993 | 4126 | 0 | 0 | 0 | 0.00/28.00/0.00 | 259 | 0 |
| Stage 2 | 16993..39878 | 6604 | 0 | 0 | 0 | 33.00/50.00/33.00 | 287 | 0 |
| Stage 3 | 39878..63592 | 6171 | 0 | 0 | 0 | 56.00/120.00/56.00 | 270 | 140 |
| Stage 4A / Reimu | 63592..101569 | 8668 | 1 | 0 | 2.00 | 125.00/128.00/112.00 | 527 | 0 |
| Stage 5 | 101569..140329 | 8241 | 1 | 0 | 3.00 | 128.00/113.00/112.00 | 664 | 0 |
| Final B / Kaguya | 140329..213262 | 15515 | 11 | 0 | 2.00 | 118.00/14.00/0.00 | 1186 | 225 |

## Failure Taxonomy

| Primary class | Deaths | Interpretation |
| --- | ---: | --- |
| `modeled_committed_prefix_collision` | 6 | The hit-row committed pipeline or the causal last-alive selected-action certificate was already unsafe. |
| `observed_bullet_overlap` | 3 | A bullet overlaps the native player AABB in the hit observation. |
| `observed_laser_overlap` | 3 | The player overlaps an active laser's exact finite segment; TH08 checks this before the broad bullet pass. |
| `sensor_gap_or_unmodeled_hazard` | 1 | No observed overlap and positive pipeline clearance; same-frame ECL emission, transform error, or another unmodeled hazard is the leading explanation. |

Contributing factors:

- `playfield_boundary`: 11 deaths
- `fast_mode`: 9 deaths
- `action_lag_over_model`: 4 deaths

## High-Risk Clusters

| Cluster | Stage | Frames | Deaths | Min Power | Max bullets at hit |
| --- | --- | ---: | ---: | ---: | ---: |
| cluster-05 | Final B / Kaguya | 151655..153341 | 6 | 34.00 | 639 |
| cluster-07 | Final B / Kaguya | 161864..162451 | 2 | 8.00 | 26 |

## Stage Detail

### Stage 1

- Death frames: -
- Cause counts: `{}`
- Phase markers: observed 3, reachable static opcode `0x94` 3.
- Bottom/side occupancy decisions: 10/6.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |

### Stage 2

- Death frames: -
- Cause counts: `{}`
- Phase markers: observed 2, reachable static opcode `0x94` 2.
- Bottom/side occupancy decisions: 93/206.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |

### Stage 3

- Death frames: -
- Cause counts: `{}`
- Phase markers: observed 3, reachable static opcode `0x94` 3.
- Bottom/side occupancy decisions: 129/116.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |

### Stage 4A / Reimu

- Death frames: 67903
- Cause counts: `{"observed_bullet_overlap": 1}`
- Phase markers: observed 7, reachable static opcode `0x94` 7.
- Bottom/side occupancy decisions: 541/578.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 67903 | 5.00 | 128.00 | 2.00 | 100 | -0.23 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |

### Stage 5

- Death frames: 139187
- Cause counts: `{"modeled_committed_prefix_collision": 1}`
- Phase markers: observed 7, reachable static opcode `0x94` 7.
- Bottom/side occupancy decisions: 606/430.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 139187 | 6.00 | 128.00 | 3.00 | 426 | -2.14 | - | `modeled_committed_prefix_collision` | - |

### Final B / Kaguya

- Death frames: 147860, 148766, 151655, 151990, 152333, 152676, 153001, 153341, 160787, 161864, 162451
- Cause counts: `{"sensor_gap_or_unmodeled_hazard": 1, "observed_bullet_overlap": 2, "modeled_committed_prefix_collision": 5, "observed_laser_overlap": 3}`
- Phase markers: observed 14, reachable static opcode `0x94` 14.
- Bottom/side occupancy decisions: 1024/1158.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 147860 | 3.00 | 128.00 | 0.00 | 190 | 10.06 | - | `sensor_gap_or_unmodeled_hazard` | fast_mode |
| 148766 | 3.00 | 121.00 | 0.00 | 204 | -1.79 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 151655 | 4.00 | 114.00 | 1.00 | 563 | 0.56 | - | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model |
| 151990 | 3.00 | 98.00 | 0.00 | 639 | -2.40 | - | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model |
| 152333 | 3.00 | 82.00 | 0.00 | 607 | 1.92 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 152676 | 3.00 | 66.00 | 0.00 | 590 | -0.39 | - | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model,fast_mode |
| 153001 | 3.00 | 50.00 | 0.00 | 596 | -0.80 | - | `modeled_committed_prefix_collision` | playfield_boundary,action_lag_over_model |
| 153341 | 3.00 | 34.00 | 0.00 | 591 | 0.71 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 160787 | 3.00 | 28.00 | 0.00 | 18 | -3.84 | - | `observed_laser_overlap` | playfield_boundary,fast_mode |
| 161864 | 4.00 | 12.00 | 1.00 | 26 | -4.43 | - | `observed_laser_overlap` | playfield_boundary,fast_mode |
| 162451 | 3.00 | 8.00 | 0.00 | 17 | -3.61 | - | `observed_laser_overlap` | playfield_boundary,fast_mode |

## Spell Inventory And Runtime Coverage

Every spell below is statically reachable for route 2 Easy Final B. Observed decisions count only rows whose live spell state reported that active spell ID. Zero decisions therefore means the run did not enter that spell; zero hits with nonzero decisions means it entered cleanly. `unresolved` means the trace schema did not persist enough live spell state.

### Stage 1

- ECL: `ecldata1.ecl`
- Observed/expected phase-counter markers: 3/3.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 2 | 灯符「ファイヤフライフェノメノン」 | リグル・ナイトバグ | 7 | 6 | 0 | yes | 458 | 0 |
| 6 | 蠢符「リトルバグ」 | リグル・ナイトバグ | 7 | 27 | 0 | yes | 767 | 0 |

### Stage 2

- ECL: `ecldata2.ecl`
- Observed/expected phase-counter markers: 2/2.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 13 | 声符「梟の夜鳴声」 | ミスティア・ローレライ | 2 | 7 | 0 | yes | 610 | 0 |
| 17 | 蛾符「天蛾の蠱道」 | ミスティア・ローレライ | 3 | 6 | 0 | yes | 719 | 0 |
| 21 | 鷹符「イルスタードダイブ」 | ミスティア・ローレライ | 3 | 4 | 0 | yes | 735 | 0 |
| 25 | 夜盲「夜雀の歌」 | ミスティア・ローレライ | 6 | 9 | 0 | yes | 679 | 0 |

### Stage 3

- ECL: `ecldata3.ecl`
- Observed/expected phase-counter markers: 3/3.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 32 | 産霊「ファーストピラミッド」 | 上白沢慧音 | 3 | 0 | 0 | yes | 761 | 0 |
| 39 | 野符「武烈クライシス」 | 上白沢慧音 | 3 | 2 | 0 | yes | 483 | 0 |
| 43 | 国符「三種の神器　剣」 | 上白沢慧音 | 3 | 0 | 0 | yes | 762 | 0 |
| 47 | 終符「幻想天皇」 | 上白沢慧音 | 1 | 0 | 1 | yes | 483 | 0 |

### Stage 4A / Reimu

- ECL: `ecldata4a.ecl`
- Observed/expected phase-counter markers: 7/7.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 54 | 夢符「二重結界」 | 博麗霊夢 | 2 | 0 | 0 | yes | 989 | 0 |
| 58 | 霊符「夢想封印　散」 | 博麗霊夢 | 3 | 0 | 0 | yes | 917 | 0 |
| 62 | 夢符「封魔陣」 | 博麗霊夢 | 7 | 27 | 0 | yes | 450 | 0 |
| 66 | 霊符「夢想封印　集」 | 博麗霊夢 | 1 | 17 | 0 | yes | 513 | 0 |
| 70 | 境界「二重弾幕結界」 | 博麗霊夢 | 3 | 4 | 0 | yes | 460 | 0 |

### Stage 5

- ECL: `ecldata5.ecl`
- Observed/expected phase-counter markers: 7/7.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 100 | 波符「赤眼催眠(マインドシェイカー)」 | 鈴仙・Ｕ・イナバ | 6 | 0 | 0 | yes | 351 | 0 |
| 108 | 懶符「生神停止(アイドリングウェーブ」 | 鈴仙・Ｕ・イナバ | 2 | 0 | 0 | yes | 822 | 0 |
| 104 | 狂符「幻視調律(ビジョナリチューニング)」 | 鈴仙・Ｕ・イナバ | 2 | 2 | 0 | yes | 375 | 0 |
| 112 | 散符「真実の月(インビジブルフルムーン)」 | 鈴仙・Ｕ・イナバ | 5 | 0 | 0 | yes | 854 | 1 |

### Final B / Kaguya

- ECL: `ecldata7.ecl`
- Observed/expected phase-counter markers: 14/14.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 147 | 薬符「壺中の大銀河」 | 八意永琳 | 4 | 0 | 0 | yes | 786 | 6 |
| 151 | 難題「龍の頸の玉  -五色の弾丸-」 | 蓬莱山輝夜 | 5 | 1 | 5 | yes | 1091 | 3 |
| 155 | 難題「仏の御石の鉢  -砕けぬ意思-」 | 蓬莱山輝夜 | 3 | 4 | 2 | yes | 1307 | 0 |
| 159 | 難題「火鼠の皮衣  -焦れぬ心-」 | 蓬莱山輝夜 | 4 | 8 | 1 | yes | 1220 | 0 |
| 163 | 難題「燕の子安貝  -永命線-」 | 蓬莱山輝夜 | 3 | 2 | 2 | yes | 980 | 0 |
| 167 | 難題「蓬莱の弾の枝  -虹色の弾幕-」 | 蓬莱山輝夜 | 26 | 3 | 0 | yes | 1583 | 0 |
| 171 | 「永夜返し  -初月-」 | 蓬莱山輝夜 | 3 | 1 | 0 | yes | 308 | 0 |
| 175 | 「永夜返し  -子の刻-」 | 蓬莱山輝夜 | 3 | 2 | 0 | yes | 324 | 0 |
| 179 | 「永夜返し  -丑の刻-」 | 蓬莱山輝夜 | 2 | 2 | 0 | yes | 426 | 0 |
| 183 | 「永夜返し  -寅の刻-」 | 蓬莱山輝夜 | 4 | 4 | 0 | yes | 334 | 0 |
| 187 | 「永夜返し  -朝靄-」 | 蓬莱山輝夜 | 12 | 5 | 0 | yes | 708 | 0 |

## Runtime And Harness Findings

- Observed auto-Z stall frames: none.
- Route termination: `route_complete` at completion probe frame 213264.
- Unique robust solutions observed: 0; solve time median/p95/max -/-/- ms.
- First-observed policy age median/p95/max: -/-/- frames.
- Viability queries available: 0/0; robustly constrained decisions: 0/49325.
- Robust-policy decisions without any usable query: 0/0.
- Global-horizon/local-prefix cross-tab: 0 decisions; winning global state with unsafe selected prefix: 0; losing global state with safe short prefix: 0; selected globally certified action contradicted by the fresh local prefix checker: 0; selected action outside the reported winning set: 0.
- Live spell attribution was recorded at every hit edge; exact per-spell counts are preserved below.
- `1` hit edges remain in the `sensor_gap_or_unmodeled_hazard` class and require executor-level same-frame emission/transform evidence.

## Next Regression Work

1. Keep robust backward-reachability solves within the finite policy horizon, then verify nonzero live query and constrained-decision counts.
2. Replay all 13 retained witnesses through the integrated executor and preserve one regression per concrete failure.
3. Re-run focused Stage 4A and Final B practices before another full Easy route; compare hit frames, policy age, action-set exhaustion, and cluster recurrence.
4. Add item/Power state and finite Bomb resources only after the no-Bomb movement policy has passed physical validation.
