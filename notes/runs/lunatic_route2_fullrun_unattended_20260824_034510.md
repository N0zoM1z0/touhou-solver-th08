# TH08 Lunatic Full-Run Review: lunatic_route2_fullrun_unattended_20260824_034510

## Result

- Route: Sakuya/Remilia, Lunatic, Final B / Kaguya.
- Combat completion: yes; gameplay scene unloaded at frame 229967.
- Native phase-2 hit edges, including Last-Spell-saveable edges: 67.
- Deathbomb requests at those edges: 0.
- Hard no-Bomb input verification: passed across 58020 decisions.
- Post-hit Bomb-stock decreases: 18.00; this is respawn-stock reset telemetry, not evidence of Bomb input.
- Agent decisions: 58020.
- Raw trace size: 2046365993 bytes across 1 segments.
- JSON decode errors: 0.
- Exact spell-level hit attribution: available from live `g_spell_card_state`.

The run is valid for stage-, death-, resource-, projectile-, latency-, and route-level analysis. Spell names below are the statically reachable Lunatic route inventory; unavailable runtime hit counts remain explicitly unresolved instead of guessed. The no-life patch allows post-hit resource resets to repeat, so resource-stock changes must not be interpreted as Bomb commands.

## Trace Integrity

| Segment | Frames | Decisions | Wall Z | Termination | Runtime error | SHA-256 |
| --- | ---: | ---: | ---: | --- | --- | --- |
| 1 | 2..229967 | 58020 | 426 | route_complete | - | `e5611a960d3b847787fd198c4949b5878e182a396096754ae3b7289fe9038dfc` |

The route is one continuous agent-controlled trace with no foreground interruption or manual re-arm gap.

## Stage Summary

| Stage | Frames | Decisions | Native hits | Deathbombs | Post-hit Bomb-stock decrease | Power start/end/min | Max bullets | Max lasers |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Stage 1 | 2..20950 | 5308 | 0 | 0 | 0 | 0.00/24.00/0.00 | 1171 | 0 |
| Stage 2 | 20950..44709 | 7353 | 4 | 0 | 0.00 | 29.00/13.00/0.00 | 1214 | 0 |
| Stage 3 | 44709..72546 | 7733 | 5 | 0 | 4.00 | 19.00/6.00/3.00 | 921 | 200 |
| Stage 4A / Reimu | 72546..118404 | 11796 | 21 | 0 | 8.00 | 11.00/0.00/0.00 | 1368 | 0 |
| Stage 5 | 118404..163295 | 9691 | 10 | 0 | 4.00 | 5.00/8.00/0.00 | 1531 | 0 |
| Final B / Kaguya | 163295..229967 | 16139 | 27 | 0 | 2.00 | 16.00/7.00/0.00 | 1228 | 245 |

## Failure Taxonomy

| Primary class | Deaths | Interpretation |
| --- | ---: | --- |
| `modeled_committed_prefix_collision` | 43 | The hit-row committed pipeline or the causal last-alive selected-action certificate was already unsafe. |
| `observed_bullet_overlap` | 24 | A bullet overlaps the native player AABB in the hit observation. |

Contributing factors:

- `playfield_boundary`: 58 deaths
- `fast_mode`: 46 deaths
- `pool_density_over_1000`: 14 deaths
- `action_lag_over_model`: 1 deaths

## High-Risk Clusters

| Cluster | Stage | Frames | Deaths | Min Power | Max bullets at hit |
| --- | --- | ---: | ---: | ---: | ---: |
| cluster-50 | Final B / Kaguya | 219801..223857 | 9 | 0.00 | 573 |
| cluster-13 | Stage 4A / Reimu | 84555..85543 | 3 | 0.00 | 612 |
| cluster-12 | Stage 4A / Reimu | 76575..76886 | 2 | 0.00 | 968 |
| cluster-15 | Stage 4A / Reimu | 95085..95578 | 2 | 0.00 | 827 |
| cluster-21 | Stage 4A / Reimu | 110940..111424 | 2 | 2.00 | 477 |
| cluster-24 | Stage 4A / Reimu | 117193..117658 | 2 | 0.00 | 1322 |
| cluster-40 | Final B / Kaguya | 182355..182787 | 2 | 2.00 | 1143 |

## Stage Detail

### Stage 1

- Death frames: -
- Cause counts: `{}`
- Phase markers: observed 3, reachable static opcode `0x94` 4.
- Bottom/side occupancy decisions: 339/290.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |

### Stage 2

- Death frames: 23778, 24510, 26001, 42243
- Cause counts: `{"observed_bullet_overlap": 1, "modeled_committed_prefix_collision": 3}`
- Phase markers: observed 2, reachable static opcode `0x94` 3.
- Bottom/side occupancy decisions: 1032/671.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 23778 | 3.00 | 32.00 | 0.00 | 144 | -0.47 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 24510 | 3.00 | 16.00 | 0.00 | 266 | -2.60 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 26001 | 3.00 | 2.00 | 0.00 | 462 | -2.22 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 42243 | 3.00 | 3.00 | 0.00 | 370 | -3.23 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |

### Stage 3

- Death frames: 46433, 53712, 60310, 61104, 67048
- Cause counts: `{"modeled_committed_prefix_collision": 3, "observed_bullet_overlap": 2}`
- Phase markers: observed 3, reachable static opcode `0x94` 4.
- Bottom/side occupancy decisions: 1073/715.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 46433 | 4.00 | 25.00 | 1.00 | 523 | -3.19 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 53712 | 3.00 | 23.00 | 0.00 | 417 | -2.32 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 60310 | 5.00 | 37.00 | 2.00 | 230 | -1.13 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 61104 | 4.00 | 22.00 | 1.00 | 235 | -1.16 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 67048 | 3.00 | 19.00 | 0.00 | 359 | -2.89 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |

### Stage 4A / Reimu

- Death frames: 73042, 74360, 76575, 76886, 84555, 84943, 85543, 92487, 95085, 95578, 100961, 101789, 104767, 108194, 109173, 110940, 111424, 112751, 115968, 117193, 117658
- Cause counts: `{"modeled_committed_prefix_collision": 16, "observed_bullet_overlap": 5}`
- Phase markers: observed 7, reachable static opcode `0x94` 8.
- Bottom/side occupancy decisions: 1458/1068.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 73042 | 4.00 | 11.00 | 1.00 | 112 | -3.30 | - | `modeled_committed_prefix_collision` | action_lag_over_model |
| 74360 | 3.00 | 17.00 | 0.00 | 462 | -1.48 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 76575 | 3.00 | 10.00 | 0.00 | 968 | -1.15 | - | `observed_bullet_overlap` | - |
| 76886 | 3.00 | 0.00 | 0.00 | 905 | -1.68 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 84555 | 4.00 | 4.00 | 1.00 | 602 | -3.34 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 84943 | 3.00 | 10.00 | 0.00 | 597 | -1.79 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 85543 | 3.00 | 0.00 | 0.00 | 612 | -1.45 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 92487 | 4.00 | 1.00 | 1.00 | 343 | -4.76 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 95085 | 3.00 | 3.00 | 0.00 | 827 | -2.92 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 95578 | 4.00 | 0.00 | 1.00 | 599 | -1.94 | - | `modeled_committed_prefix_collision` | fast_mode |
| 100961 | 4.00 | 4.00 | 1.00 | 116 | -4.20 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 101789 | 4.00 | 1.00 | 1.00 | 80 | -2.07 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 104767 | 3.00 | 8.00 | 0.00 | 1329 | 1.36 | - | `modeled_committed_prefix_collision` | pool_density_over_1000 |
| 108194 | 3.00 | 1.00 | 0.00 | 101 | 0.07 | - | `observed_bullet_overlap` | playfield_boundary |
| 109173 | 3.00 | 2.00 | 0.00 | 87 | 2.70 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 110940 | 4.00 | 2.00 | 1.00 | 458 | -3.23 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 111424 | 3.00 | 3.00 | 0.00 | 477 | -2.26 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 112751 | 3.00 | 0.00 | 0.00 | 594 | -2.30 | - | `observed_bullet_overlap` | playfield_boundary |
| 115968 | 3.00 | 4.00 | 0.00 | 1000 | -1.44 | - | `modeled_committed_prefix_collision` | pool_density_over_1000,fast_mode |
| 117193 | 3.00 | 0.00 | 0.00 | 1316 | -3.27 | - | `modeled_committed_prefix_collision` | pool_density_over_1000,fast_mode |
| 117658 | 4.00 | 1.00 | 1.00 | 1322 | -3.04 | - | `modeled_committed_prefix_collision` | pool_density_over_1000,fast_mode |

### Stage 5

- Death frames: 122195, 130808, 131415, 143020, 150032, 158572, 160649, 161524, 162153, 162984
- Cause counts: `{"observed_bullet_overlap": 4, "modeled_committed_prefix_collision": 6}`
- Phase markers: observed 7, reachable static opcode `0x94` 8.
- Bottom/side occupancy decisions: 2347/1223.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 122195 | 3.00 | 9.00 | 0.00 | 827 | -1.31 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 130808 | 3.00 | 10.00 | 0.00 | 290 | 1.50 | - | `observed_bullet_overlap` | playfield_boundary |
| 131415 | 3.00 | 2.00 | 0.00 | 323 | -10.82 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 143020 | 5.00 | 17.00 | 2.00 | 1104 | -1.88 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 150032 | 3.00 | 1.00 | 0.00 | 1016 | -5.64 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 158572 | 3.00 | 3.00 | 0.00 | 354 | -2.26 | - | `modeled_committed_prefix_collision` | - |
| 160649 | 3.00 | 2.00 | 0.00 | 1127 | -2.03 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 161524 | 4.00 | 0.00 | 1.00 | 1170 | -2.36 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000 |
| 162153 | 3.00 | 0.00 | 0.00 | 1150 | -1.11 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 162984 | 4.00 | 2.00 | 1.00 | 900 | -1.21 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |

### Final B / Kaguya

- Death frames: 166078, 171155, 175271, 175944, 176825, 182355, 182787, 183520, 184787, 185605, 194392, 197323, 204565, 213921, 214610, 216036, 219801, 220307, 220824, 221289, 221801, 222305, 222825, 223348, 223857, 227026, 229794
- Cause counts: `{"modeled_committed_prefix_collision": 15, "observed_bullet_overlap": 12}`
- Phase markers: observed 11, reachable static opcode `0x94` 14.
- Bottom/side occupancy decisions: 2413/1689.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 166078 | 4.00 | 16.00 | 1.00 | 533 | -1.94 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 171155 | 3.00 | 69.00 | 0.00 | 372 | -2.64 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 175271 | 3.00 | 53.00 | 0.00 | 628 | -0.33 | - | `observed_bullet_overlap` | playfield_boundary |
| 175944 | 3.00 | 38.00 | 0.00 | 674 | -6.71 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 176825 | 3.00 | 22.00 | 0.00 | 571 | -1.36 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 182355 | 3.00 | 9.00 | 0.00 | 1136 | -2.42 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 182787 | 3.00 | 2.00 | 0.00 | 1143 | -2.17 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000 |
| 183520 | 3.00 | 1.00 | 0.00 | 1117 | -0.23 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000 |
| 184787 | 4.00 | 2.00 | 1.00 | 1171 | 0.65 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000,fast_mode |
| 185605 | 3.00 | 1.00 | 0.00 | 105 | -4.60 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 194392 | 3.00 | 3.00 | 0.00 | 249 | -2.38 | - | `observed_bullet_overlap` | playfield_boundary |
| 197323 | 3.00 | 8.00 | 0.00 | 244 | 0.79 | - | `observed_bullet_overlap` | playfield_boundary |
| 204565 | 3.00 | 9.00 | 0.00 | 532 | -3.11 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 213921 | 3.00 | 0.00 | 0.00 | 281 | -0.27 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 214610 | 3.00 | 0.00 | 0.00 | 358 | -1.43 | - | `observed_bullet_overlap` | playfield_boundary |
| 216036 | 3.00 | 0.00 | 0.00 | 449 | -2.65 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 219801 | 3.00 | 0.00 | 0.00 | 543 | -1.79 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 220307 | 3.00 | 9.00 | 0.00 | 562 | -1.18 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 220824 | 3.00 | 1.00 | 0.00 | 567 | -2.25 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 221289 | 3.00 | 0.00 | 0.00 | 548 | -2.43 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 221801 | 3.00 | 1.00 | 0.00 | 573 | -2.31 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 222305 | 3.00 | 2.00 | 0.00 | 562 | -2.92 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 222825 | 3.00 | 2.00 | 0.00 | 555 | -2.05 | - | `observed_bullet_overlap` | fast_mode |
| 223348 | 3.00 | 8.00 | 0.00 | 554 | 0.73 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 223857 | 3.00 | 8.00 | 0.00 | 560 | -1.07 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 227026 | 3.00 | 7.00 | 0.00 | 913 | -0.78 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 229794 | 3.00 | 7.00 | 0.00 | 1037 | -4.54 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |

## Spell Inventory And Runtime Coverage

Every spell below is statically reachable for route 2 Lunatic Final B. Observed decisions count only rows whose live spell state reported that active spell ID. Zero decisions therefore means the run did not enter that spell; zero hits with nonzero decisions means it entered cleanly. `unresolved` means the trace schema did not persist enough live spell state.

### Stage 1

- ECL: `ecldata1.ecl`
- Observed/expected phase-counter markers: 3/4.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 1 | 蛍符「地上の彗星」 | リグル・ナイトバグ | 3 | 6 | 0 | yes | 692 | 0 |
| 5 | 灯符「ファイヤフライフェノメノン」 | リグル・ナイトバグ | 11 | 6 | 0 | yes | 624 | 0 |
| 9 | 蠢符「ナイトバグトルネード」 | リグル・ナイトバグ | 13 | 27 | 0 | yes | 722 | 0 |
| 12 | 隠蟲「永夜蟄居」 | リグル・ナイトバグ | 12 | 27 | 0 | no | 0 | 0 |

### Stage 2

- ECL: `ecldata2.ecl`
- Observed/expected phase-counter markers: 2/3.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 16 | 声符「木菟咆哮」 | ミスティア・ローレライ | 4 | 7 | 0 | yes | 586 | 0 |
| 20 | 猛毒「毒蛾の暗闇演舞」 | ミスティア・ローレライ | 5 | 7 | 0 | yes | 729 | 0 |
| 24 | 鷹符「イルスタードダイブ」 | ミスティア・ローレライ | 6 | 8 | 0 | yes | 750 | 1 |
| 28 | 夜盲「夜雀の歌」 | ミスティア・ローレライ | 8 | 9 | 0 | yes | 854 | 0 |
| 31 | 夜雀「真夜中のコーラスマスター」 | ミスティア・ローレライ | 3 | 7 | 0 | no | 0 | 0 |

### Stage 3

- ECL: `ecldata3.ecl`
- Observed/expected phase-counter markers: 3/4.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 35 | 産霊「ファーストピラミッド」 | 上白沢慧音 | 3 | 0 | 0 | yes | 745 | 0 |
| 38 | 始符「エフェメラリティ137」 | 上白沢慧音 | 2 | 2 | 0 | yes | 701 | 2 |
| 42 | 野符「GHQクライシス」 | 上白沢慧音 | 3 | 3 | 0 | yes | 667 | 0 |
| 46 | 国体「三種の神器　郷」 | 上白沢慧音 | 3 | 0 | 0 | yes | 762 | 0 |
| 50 | 虚史「幻想郷伝説」 | 上白沢慧音 | 1 | 0 | 1 | yes | 575 | 0 |
| 53 | 未来「高天原」 | 上白沢慧音 | 1 | 0 | 1 | no | 0 | 0 |

### Stage 4A / Reimu

- ECL: `ecldata4a.ecl`
- Observed/expected phase-counter markers: 7/8.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 57 | 夢境「二重大結界」 | 博麗霊夢 | 3 | 0 | 0 | yes | 1028 | 3 |
| 61 | 散霊「夢想封印　寂」 | 博麗霊夢 | 3 | 0 | 0 | yes | 1060 | 1 |
| 65 | 神技「八方龍殺陣」 | 博麗霊夢 | 7 | 27 | 0 | yes | 792 | 1 |
| 69 | 回霊「夢想封印　侘」 | 博麗霊夢 | 2 | 17 | 0 | yes | 967 | 3 |
| 73 | 大結界「博麗弾幕結界」 | 博麗霊夢 | 5 | 4 | 0 | yes | 1037 | 3 |
| 76 | 神霊「夢想封印　瞬」 | 博麗霊夢 | 2 | 5 | 0 | no | 0 | 0 |

### Stage 5

- ECL: `ecldata5.ecl`
- Observed/expected phase-counter markers: 7/8.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 103 | 幻波「赤眼催眠(マインドブローイング)」 | 鈴仙・Ｕ・イナバ | 6 | 0 | 0 | yes | 764 | 1 |
| 111 | 懶惰「生神停止(マインドストッパー)」 | 鈴仙・Ｕ・イナバ | 3 | 0 | 0 | yes | 827 | 1 |
| 107 | 狂視「狂視調律(イリュージョンシーカー)」 | 鈴仙・Ｕ・イナバ | 3 | 3 | 0 | yes | 673 | 1 |
| 115 | 散符「真実の月(インビジブルフルムーン)」 | 鈴仙・Ｕ・イナバ | 6 | 3 | 0 | yes | 935 | 4 |
| 118 | 月眼「月兎遠隔催眠術(テレメスメリズム)」 | 鈴仙・Ｕ・イナバ | 4 | 2 | 0 | no | 0 | 0 |

### Final B / Kaguya

- ECL: `ecldata7.ecl`
- Observed/expected phase-counter markers: 11/14.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 150 | 薬符「壺中の大銀河」 | 八意永琳 | 4 | 0 | 0 | yes | 799 | 3 |
| 154 | 神宝「ブリリアントドラゴンバレッタ」 | 蓬莱山輝夜 | 5 | 1 | 5 | yes | 777 | 1 |
| 158 | 神宝「ブディストダイアモンド」 | 蓬莱山輝夜 | 4 | 4 | 2 | yes | 1398 | 2 |
| 162 | 神宝「サラマンダーシールド」 | 蓬莱山輝夜 | 4 | 8 | 2 | yes | 1561 | 1 |
| 166 | 神宝「ライフスプリングインフィニティ」 | 蓬莱山輝夜 | 3 | 2 | 2 | yes | 1354 | 3 |
| 170 | 神宝「蓬莱の玉の枝  -夢色の郷-」 | 蓬莱山輝夜 | 26 | 3 | 0 | yes | 1712 | 9 |
| 174 | 「永夜返し  -待宵-」 | 蓬莱山輝夜 | 3 | 1 | 0 | yes | 244 | 1 |
| 178 | 「永夜返し  -子の四つ-」 | 蓬莱山輝夜 | 3 | 2 | 0 | yes | 268 | 1 |
| 182 | 「永夜返し  -丑の四つ-」 | 蓬莱山輝夜 | 2 | 2 | 0 | no | 0 | 0 |
| 186 | 「永夜返し  -寅の四つ-」 | 蓬莱山輝夜 | 4 | 4 | 0 | no | 0 | 0 |
| 190 | 「永夜返し  -世明け-」 | 蓬莱山輝夜 | 12 | 5 | 0 | no | 0 | 0 |

## Runtime And Harness Findings

- Observed auto-Z stall frames: none.
- Route termination: `route_complete` at completion probe frame 229967.
- Unique robust solutions observed: 0; solve time median/p95/max -/-/- ms.
- First-observed policy age median/p95/max: -/-/- frames.
- Viability queries available: 0/0; robustly constrained decisions: 0/58020.
- Robust-policy decisions without any usable query: 0/0.
- Global-horizon/local-prefix cross-tab: 0 decisions; winning global state with unsafe selected prefix: 0; losing global state with safe short prefix: 0; selected globally certified action contradicted by the fresh local prefix checker: 0; selected action outside the reported winning set: 0.
- Live spell attribution was recorded at every hit edge; exact per-spell counts are preserved below.
- `0` hit edges remain in the `sensor_gap_or_unmodeled_hazard` class and require executor-level same-frame emission/transform evidence.

## Next Regression Work

1. Keep robust backward-reachability solves within the finite policy horizon, then verify nonzero live query and constrained-decision counts.
2. Replay all 67 retained witnesses through the integrated executor and preserve one regression per concrete failure.
3. Re-run focused Stage 4A and Final B practices before another full Lunatic route; compare hit frames, policy age, action-set exhaustion, and cluster recurrence.
4. Add item/Power state and finite Bomb resources only after the no-Bomb movement policy has passed physical validation.
