# TH08 Lunatic Full-Run Review: lunatic_route2_fullrun_unattended_20260823_183138

## Result

- Route: Sakuya/Remilia, Lunatic, Final B / Kaguya.
- Combat completion: yes; gameplay scene unloaded at frame 233818.
- Native phase-2 hit edges, including Last-Spell-saveable edges: 58.
- Deathbomb requests at those edges: 0.
- Hard no-Bomb input verification: passed across 55024 decisions.
- Post-hit Bomb-stock decreases: 17.00; this is respawn-stock reset telemetry, not evidence of Bomb input.
- Agent decisions: 55024.
- Raw trace size: 1996849350 bytes across 1 segments.
- JSON decode errors: 0.
- Exact spell-level hit attribution: available from live `g_spell_card_state`.

The run is valid for stage-, death-, resource-, projectile-, latency-, and route-level analysis. Spell names below are the statically reachable Lunatic route inventory; unavailable runtime hit counts remain explicitly unresolved instead of guessed. The no-life patch allows post-hit resource resets to repeat, so resource-stock changes must not be interpreted as Bomb commands.

## Trace Integrity

| Segment | Frames | Decisions | Wall Z | Termination | Runtime error | SHA-256 |
| --- | ---: | ---: | ---: | --- | --- | --- |
| 1 | 2..233818 | 55024 | 434 | route_complete | - | `4a0caca711ac9b1fdf57d0d43fa72969e9e03ed270dee315d846c44054152490` |

The route is one continuous agent-controlled trace with no foreground interruption or manual re-arm gap.

## Stage Summary

| Stage | Frames | Decisions | Native hits | Deathbombs | Post-hit Bomb-stock decrease | Power start/end/min | Max bullets | Max lasers |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Stage 1 | 2..20979 | 4990 | 4 | 0 | 0.00 | 0.00/0.00/0.00 | 1175 | 0 |
| Stage 2 | 20979..44615 | 6657 | 6 | 0 | 0.00 | 5.00/1.00/0.00 | 1187 | 0 |
| Stage 3 | 44615..72452 | 7189 | 5 | 0 | 2.00 | 7.00/5.00/0.00 | 914 | 200 |
| Stage 4A / Reimu | 72452..118130 | 10978 | 13 | 0 | 2.00 | 10.00/3.00/0.00 | 1484 | 0 |
| Stage 5 | 118130..163288 | 9342 | 9 | 0 | 5.00 | 8.00/5.00/0.00 | 1531 | 0 |
| Final B / Kaguya | 163289..233818 | 15868 | 21 | 0 | 8.00 | 10.00/7.00/0.00 | 1273 | 255 |

## Failure Taxonomy

| Primary class | Deaths | Interpretation |
| --- | ---: | --- |
| `modeled_committed_prefix_collision` | 39 | The measured three-frame input pipeline was already unsafe. |
| `observed_bullet_overlap` | 17 | A bullet overlaps the native player AABB in the hit observation. |
| `observed_laser_overlap` | 2 | The player overlaps an active laser's exact finite segment; TH08 checks this before the broad bullet pass. |

Contributing factors:

- `playfield_boundary`: 46 deaths
- `fast_mode`: 41 deaths
- `pool_density_over_1000`: 9 deaths

## High-Risk Clusters

| Cluster | Stage | Frames | Deaths | Min Power | Max bullets at hit |
| --- | --- | ---: | ---: | ---: | ---: |
| cluster-13 | Stage 3 | 60838..61362 | 2 | 5.00 | 220 |
| cluster-17 | Stage 4A / Reimu | 76367..76718 | 2 | 1.00 | 1127 |
| cluster-18 | Stage 4A / Reimu | 84457..85047 | 2 | 1.00 | 613 |
| cluster-21 | Stage 4A / Reimu | 94779..95275 | 2 | 2.00 | 719 |
| cluster-34 | Final B / Kaguya | 175078..175397 | 2 | 60.00 | 264 |
| cluster-35 | Final B / Kaguya | 176195..176582 | 2 | 28.00 | 616 |
| cluster-36 | Final B / Kaguya | 181951..182513 | 2 | 0.00 | 1205 |
| cluster-46 | Final B / Kaguya | 221856..222344 | 2 | 1.00 | 573 |

## Stage Detail

### Stage 1

- Death frames: 1747, 2690, 6978, 13786
- Cause counts: `{"modeled_committed_prefix_collision": 3, "observed_bullet_overlap": 1}`
- Phase markers: observed 3, reachable static opcode `0x94` 4.
- Bottom/side occupancy decisions: 272/388.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1747 | 3.00 | 1.00 | 0.00 | 144 | -1.81 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 2690 | 3.00 | 7.00 | 0.00 | 223 | -4.17 | - | `modeled_committed_prefix_collision` | fast_mode |
| 6978 | 3.00 | 1.00 | 0.00 | 323 | -3.88 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 13786 | 3.00 | 4.00 | 0.00 | 362 | -1.78 | - | `observed_bullet_overlap` | playfield_boundary |

### Stage 2

- Death frames: 22167, 23551, 24682, 26155, 31942, 43877
- Cause counts: `{"modeled_committed_prefix_collision": 4, "observed_bullet_overlap": 2}`
- Phase markers: observed 2, reachable static opcode `0x94` 3.
- Bottom/side occupancy decisions: 814/609.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 22167 | 3.00 | 10.00 | 0.00 | 121 | -1.95 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 23551 | 3.00 | 8.00 | 0.00 | 251 | 1.12 | - | `observed_bullet_overlap` | playfield_boundary |
| 24682 | 3.00 | 0.00 | 0.00 | 248 | -1.76 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 26155 | 3.00 | 1.00 | 0.00 | 442 | -2.41 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 31942 | 3.00 | 13.00 | 0.00 | 629 | -4.17 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 43877 | 3.00 | 1.00 | 0.00 | 623 | -0.15 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |

### Stage 3

- Death frames: 46617, 52894, 60838, 61362, 67916
- Cause counts: `{"observed_bullet_overlap": 3, "modeled_committed_prefix_collision": 2}`
- Phase markers: observed 3, reachable static opcode `0x94` 4.
- Bottom/side occupancy decisions: 944/820.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 46617 | 3.00 | 14.00 | 0.00 | 456 | 0.34 | - | `observed_bullet_overlap` | playfield_boundary |
| 52894 | 3.00 | 6.00 | 0.00 | 691 | -4.14 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 60838 | 4.00 | 19.00 | 1.00 | 213 | -2.41 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 61362 | 3.00 | 5.00 | 0.00 | 220 | 1.01 | - | `observed_bullet_overlap` | fast_mode |
| 67916 | 4.00 | 17.00 | 1.00 | 83 | 0.46 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |

### Stage 4A / Reimu

- Death frames: 74282, 75223, 76367, 76718, 84457, 85047, 85984, 93715, 94779, 95275, 103940, 112691, 116398
- Cause counts: `{"modeled_committed_prefix_collision": 7, "observed_bullet_overlap": 6}`
- Phase markers: observed 7, reachable static opcode `0x94` 8.
- Bottom/side occupancy decisions: 1357/1039.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 74282 | 3.00 | 17.00 | 0.00 | 429 | -3.56 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 75223 | 3.00 | 10.00 | 0.00 | 569 | -1.21 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 76367 | 3.00 | 5.00 | 0.00 | 718 | 1.11 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 76718 | 3.00 | 1.00 | 0.00 | 1127 | -1.49 | - | `observed_bullet_overlap` | pool_density_over_1000 |
| 84457 | 3.00 | 3.00 | 0.00 | 613 | -2.33 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 85047 | 3.00 | 1.00 | 0.00 | 598 | -1.46 | - | `observed_bullet_overlap` | playfield_boundary |
| 85984 | 3.00 | 1.00 | 0.00 | 596 | -3.62 | - | `modeled_committed_prefix_collision` | fast_mode |
| 93715 | 3.00 | 0.00 | 0.00 | 676 | -1.49 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 94779 | 4.00 | 13.00 | 1.00 | 719 | -1.98 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 95275 | 3.00 | 2.00 | 0.00 | 654 | -2.50 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 103940 | 3.00 | 4.00 | 0.00 | 1248 | 1.00 | - | `observed_bullet_overlap` | pool_density_over_1000 |
| 112691 | 3.00 | 4.00 | 0.00 | 677 | 3.31 | - | `observed_bullet_overlap` | fast_mode |
| 116398 | 4.00 | 13.00 | 1.00 | 1284 | 0.01 | - | `observed_bullet_overlap` | pool_density_over_1000,fast_mode |

### Stage 5

- Death frames: 122114, 128996, 130627, 132366, 143166, 147853, 150290, 154941, 156526
- Cause counts: `{"modeled_committed_prefix_collision": 9}`
- Phase markers: observed 7, reachable static opcode `0x94` 8.
- Bottom/side occupancy decisions: 2476/1520.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 122114 | 3.00 | 10.00 | 0.00 | 374 | -1.48 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 128996 | 3.00 | 2.00 | 0.00 | 872 | -3.24 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 130627 | 4.00 | 0.00 | 1.00 | 309 | -2.11 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 132366 | 3.00 | 0.00 | 0.00 | 408 | -1.58 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 143166 | 6.00 | 11.00 | 3.00 | 1105 | -2.65 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 147853 | 3.00 | 1.00 | 0.00 | 1055 | -1.82 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 150290 | 3.00 | 0.00 | 0.00 | 1010 | -6.23 | - | `modeled_committed_prefix_collision` | pool_density_over_1000 |
| 154941 | 4.00 | 3.00 | 1.00 | 448 | -1.70 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 156526 | 3.00 | 0.00 | 0.00 | 447 | -3.59 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |

### Final B / Kaguya

- Death frames: 175078, 175397, 176195, 176582, 181951, 182513, 183504, 186366, 195306, 197390, 202764, 203566, 206495, 214633, 215383, 221856, 222344, 223398, 224295, 227901, 233644
- Cause counts: `{"modeled_committed_prefix_collision": 14, "observed_bullet_overlap": 5, "observed_laser_overlap": 2}`
- Phase markers: observed 12, reachable static opcode `0x94` 14.
- Bottom/side occupancy decisions: 2674/2567.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 175078 | 3.00 | 76.00 | 0.00 | 209 | -2.56 | - | `modeled_committed_prefix_collision` | fast_mode |
| 175397 | 3.00 | 60.00 | 0.00 | 264 | 1.29 | - | `observed_bullet_overlap` | - |
| 176195 | 3.00 | 44.00 | 0.00 | 468 | -1.69 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 176582 | 3.00 | 28.00 | 0.00 | 616 | -1.44 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 181951 | 4.00 | 13.00 | 1.00 | 1131 | -2.69 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 182513 | 4.00 | 0.00 | 1.00 | 1205 | -1.21 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 183504 | 3.00 | 0.00 | 0.00 | 1142 | -0.12 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000,fast_mode |
| 186366 | 3.00 | 2.00 | 0.00 | 108 | -4.51 | - | `modeled_committed_prefix_collision` | fast_mode |
| 195306 | 3.00 | 0.00 | 0.00 | 250 | -1.28 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 197390 | 3.00 | 2.00 | 0.00 | 251 | -1.63 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 202764 | 4.00 | 3.00 | 1.00 | 551 | -1.82 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 203566 | 4.00 | 0.00 | 1.00 | 674 | -2.94 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 206495 | 3.00 | 0.00 | 0.00 | 524 | -4.94 | - | `observed_laser_overlap` | playfield_boundary,fast_mode |
| 214633 | 3.00 | 0.00 | 0.00 | 356 | -2.68 | - | `observed_laser_overlap` | playfield_boundary,fast_mode |
| 215383 | 4.00 | 1.00 | 1.00 | 273 | -2.10 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 221856 | 3.00 | 11.00 | 0.00 | 561 | -3.10 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 222344 | 4.00 | 1.00 | 1.00 | 573 | -2.27 | - | `observed_bullet_overlap` | fast_mode |
| 223398 | 4.00 | 3.00 | 1.00 | 564 | -2.98 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 224295 | 4.00 | 2.00 | 1.00 | 572 | -2.83 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 227901 | 3.00 | 7.00 | 0.00 | 950 | -0.42 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 233644 | 3.00 | 7.00 | 0.00 | 408 | -6.54 | - | `modeled_committed_prefix_collision` | playfield_boundary |

## Spell Inventory And Runtime Coverage

Every spell below is statically reachable for route 2 Lunatic Final B. Observed decisions count only rows whose live spell state reported that active spell ID. Zero decisions therefore means the run did not enter that spell; zero hits with nonzero decisions means it entered cleanly. `unresolved` means the trace schema did not persist enough live spell state.

### Stage 1

- ECL: `ecldata1.ecl`
- Observed/expected phase-counter markers: 3/4.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 1 | 蛍符「地上の彗星」 | リグル・ナイトバグ | 3 | 6 | 0 | yes | 669 | 0 |
| 5 | 灯符「ファイヤフライフェノメノン」 | リグル・ナイトバグ | 11 | 6 | 0 | yes | 609 | 1 |
| 9 | 蠢符「ナイトバグトルネード」 | リグル・ナイトバグ | 13 | 27 | 0 | yes | 680 | 0 |
| 12 | 隠蟲「永夜蟄居」 | リグル・ナイトバグ | 12 | 27 | 0 | no | 0 | 0 |

### Stage 2

- ECL: `ecldata2.ecl`
- Observed/expected phase-counter markers: 2/3.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 16 | 声符「木菟咆哮」 | ミスティア・ローレライ | 4 | 7 | 0 | yes | 517 | 0 |
| 20 | 猛毒「毒蛾の暗闇演舞」 | ミスティア・ローレライ | 5 | 7 | 0 | yes | 655 | 0 |
| 24 | 鷹符「イルスタードダイブ」 | ミスティア・ローレライ | 6 | 8 | 0 | yes | 657 | 0 |
| 28 | 夜盲「夜雀の歌」 | ミスティア・ローレライ | 8 | 9 | 0 | yes | 822 | 1 |
| 31 | 夜雀「真夜中のコーラスマスター」 | ミスティア・ローレライ | 3 | 7 | 0 | no | 0 | 0 |

### Stage 3

- ECL: `ecldata3.ecl`
- Observed/expected phase-counter markers: 3/4.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 35 | 産霊「ファーストピラミッド」 | 上白沢慧音 | 3 | 0 | 0 | yes | 737 | 0 |
| 38 | 始符「エフェメラリティ137」 | 上白沢慧音 | 2 | 2 | 0 | yes | 647 | 2 |
| 42 | 野符「GHQクライシス」 | 上白沢慧音 | 3 | 3 | 0 | yes | 595 | 0 |
| 46 | 国体「三種の神器　郷」 | 上白沢慧音 | 3 | 0 | 0 | yes | 680 | 0 |
| 50 | 虚史「幻想郷伝説」 | 上白沢慧音 | 1 | 0 | 1 | yes | 545 | 0 |
| 53 | 未来「高天原」 | 上白沢慧音 | 1 | 0 | 1 | no | 0 | 0 |

### Stage 4A / Reimu

- ECL: `ecldata4a.ecl`
- Observed/expected phase-counter markers: 7/8.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 57 | 夢境「二重大結界」 | 博麗霊夢 | 3 | 0 | 0 | yes | 1012 | 3 |
| 61 | 散霊「夢想封印　寂」 | 博麗霊夢 | 3 | 0 | 0 | yes | 1005 | 1 |
| 65 | 神技「八方龍殺陣」 | 博麗霊夢 | 7 | 27 | 0 | yes | 747 | 1 |
| 69 | 回霊「夢想封印　侘」 | 博麗霊夢 | 2 | 17 | 0 | yes | 918 | 1 |
| 73 | 大結界「博麗弾幕結界」 | 博麗霊夢 | 5 | 4 | 0 | yes | 972 | 1 |
| 76 | 神霊「夢想封印　瞬」 | 博麗霊夢 | 2 | 5 | 0 | no | 0 | 0 |

### Stage 5

- ECL: `ecldata5.ecl`
- Observed/expected phase-counter markers: 7/8.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 103 | 幻波「赤眼催眠(マインドブローイング)」 | 鈴仙・Ｕ・イナバ | 6 | 0 | 0 | yes | 756 | 1 |
| 111 | 懶惰「生神停止(マインドストッパー)」 | 鈴仙・Ｕ・イナバ | 3 | 0 | 0 | yes | 785 | 0 |
| 107 | 狂視「狂視調律(イリュージョンシーカー)」 | 鈴仙・Ｕ・イナバ | 3 | 3 | 0 | yes | 767 | 1 |
| 115 | 散符「真実の月(インビジブルフルムーン)」 | 鈴仙・Ｕ・イナバ | 6 | 3 | 0 | yes | 860 | 0 |
| 118 | 月眼「月兎遠隔催眠術(テレメスメリズム)」 | 鈴仙・Ｕ・イナバ | 4 | 2 | 0 | no | 0 | 0 |

### Final B / Kaguya

- ECL: `ecldata7.ecl`
- Observed/expected phase-counter markers: 12/14.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 150 | 薬符「壺中の大銀河」 | 八意永琳 | 4 | 0 | 0 | yes | 725 | 4 |
| 154 | 神宝「ブリリアントドラゴンバレッタ」 | 蓬莱山輝夜 | 5 | 1 | 5 | yes | 938 | 1 |
| 158 | 神宝「ブディストダイアモンド」 | 蓬莱山輝夜 | 4 | 4 | 2 | yes | 1394 | 2 |
| 162 | 神宝「サラマンダーシールド」 | 蓬莱山輝夜 | 4 | 8 | 2 | yes | 1465 | 1 |
| 166 | 神宝「ライフスプリングインフィニティ」 | 蓬莱山輝夜 | 3 | 2 | 2 | yes | 1334 | 2 |
| 170 | 神宝「蓬莱の玉の枝  -夢色の郷-」 | 蓬莱山輝夜 | 26 | 3 | 0 | yes | 1613 | 4 |
| 174 | 「永夜返し  -待宵-」 | 蓬莱山輝夜 | 3 | 1 | 0 | yes | 325 | 1 |
| 178 | 「永夜返し  -子の四つ-」 | 蓬莱山輝夜 | 3 | 2 | 0 | yes | 361 | 0 |
| 182 | 「永夜返し  -丑の四つ-」 | 蓬莱山輝夜 | 2 | 2 | 0 | yes | 254 | 1 |
| 186 | 「永夜返し  -寅の四つ-」 | 蓬莱山輝夜 | 4 | 4 | 0 | no | 0 | 0 |
| 190 | 「永夜返し  -世明け-」 | 蓬莱山輝夜 | 12 | 5 | 0 | no | 0 | 0 |

## Runtime And Harness Findings

- Observed auto-Z stall frames: none.
- Route termination: `route_complete` at completion probe frame 233818.
- Unique robust solutions observed: 0; solve time median/p95/max -/-/- ms.
- First-observed policy age median/p95/max: -/-/- frames.
- Viability queries available: 0/0; robustly constrained decisions: 0/55024.
- Robust-policy decisions without any usable query: 0/0.
- Global-horizon/local-prefix cross-tab: 0 decisions; winning global state with unsafe selected prefix: 0; losing global state with safe short prefix: 0; selected globally certified action contradicted by the fresh local prefix checker: 0; selected action outside the reported winning set: 0.
- Live spell attribution was recorded at every hit edge; exact per-spell counts are preserved below.
- `0` hit edges remain in the `sensor_gap_or_unmodeled_hazard` class and require executor-level same-frame emission/transform evidence.

## Next Regression Work

1. Keep robust backward-reachability solves within the finite policy horizon, then verify nonzero live query and constrained-decision counts.
2. Replay all 58 retained witnesses through the integrated executor and preserve one regression per concrete failure.
3. Re-run focused Stage 4A and Final B practices before another full Lunatic route; compare hit frames, policy age, action-set exhaustion, and cluster recurrence.
4. Add item/Power state and finite Bomb resources only after the no-Bomb movement policy has passed physical validation.
