# TH08 Lunatic Full-Run Review: lunatic_route2_fullrun_unattended_20260824_051944

## Result

- Route: Sakuya/Remilia, Lunatic, Final B / Kaguya.
- Combat completion: yes; gameplay scene unloaded at frame 230561.
- Native phase-2 hit edges, including Last-Spell-saveable edges: 60.
- Deathbomb requests at those edges: 0.
- Hard no-Bomb input verification: passed across 57553 decisions.
- Post-hit Bomb-stock decreases: 15.00; this is respawn-stock reset telemetry, not evidence of Bomb input.
- Agent decisions: 57553.
- Raw trace size: 2053273015 bytes across 1 segments.
- JSON decode errors: 0.
- Exact spell-level hit attribution: available from live `g_spell_card_state`.

The run is valid for stage-, death-, resource-, projectile-, latency-, and route-level analysis. Spell names below are the statically reachable Lunatic route inventory; unavailable runtime hit counts remain explicitly unresolved instead of guessed. The no-life patch allows post-hit resource resets to repeat, so resource-stock changes must not be interpreted as Bomb commands.

## Trace Integrity

| Segment | Frames | Decisions | Wall Z | Termination | Runtime error | SHA-256 |
| --- | ---: | ---: | ---: | --- | --- | --- |
| 1 | 1..230561 | 57553 | 429 | route_complete | - | `8862488a623e14e54813e9461e7f321bd14567c64cfdefcfdfdfb81946d44ef0` |

The route is one continuous agent-controlled trace with no foreground interruption or manual re-arm gap.

## Stage Summary

| Stage | Frames | Decisions | Native hits | Deathbombs | Post-hit Bomb-stock decrease | Power start/end/min | Max bullets | Max lasers |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Stage 1 | 1..20979 | 5389 | 1 | 0 | 0.00 | 0.00/6.00/0.00 | 1174 | 0 |
| Stage 2 | 20979..44709 | 7217 | 4 | 0 | 0.00 | 11.00/10.00/0.00 | 1188 | 0 |
| Stage 3 | 44709..72633 | 7621 | 8 | 0 | 3.00 | 16.00/1.00/0.00 | 1074 | 200 |
| Stage 4A / Reimu | 72633..118404 | 11487 | 15 | 0 | 4.00 | 6.00/0.00/0.00 | 1363 | 0 |
| Stage 5 | 118404..164795 | 10046 | 14 | 0 | 3.00 | 5.00/9.00/0.00 | 1531 | 0 |
| Final B / Kaguya | 164796..230561 | 15793 | 18 | 0 | 5.00 | 14.00/14.00/0.00 | 1230 | 250 |

## Failure Taxonomy

| Primary class | Deaths | Interpretation |
| --- | ---: | --- |
| `modeled_committed_prefix_collision` | 41 | The hit-row committed pipeline or the causal last-alive selected-action certificate was already unsafe. |
| `observed_bullet_overlap` | 16 | A bullet overlaps the native player AABB in the hit observation. |
| `observed_laser_overlap` | 2 | The player overlaps an active laser's exact finite segment; TH08 checks this before the broad bullet pass. |
| `observed_enemy_body_overlap` | 1 | A captured lethal enemy-body AABB overlaps the player at action time. |

Contributing factors:

- `playfield_boundary`: 48 deaths
- `fast_mode`: 43 deaths
- `pool_density_over_1000`: 10 deaths

## High-Risk Clusters

| Cluster | Stage | Frames | Deaths | Min Power | Max bullets at hit |
| --- | --- | ---: | ---: | ---: | ---: |
| cluster-48 | Final B / Kaguya | 221052..222599 | 4 | 3.00 | 572 |
| cluster-22 | Stage 4A / Reimu | 103597..104548 | 3 | 1.00 | 1287 |
| cluster-49 | Final B / Kaguya | 223202..224286 | 3 | 1.00 | 594 |
| cluster-14 | Stage 4A / Reimu | 74779..75367 | 2 | 12.00 | 535 |
| cluster-15 | Stage 4A / Reimu | 76543..76859 | 2 | 2.00 | 822 |
| cluster-33 | Stage 5 | 158940..159527 | 2 | 0.00 | 486 |

## Stage Detail

### Stage 1

- Death frames: 4750
- Cause counts: `{"observed_bullet_overlap": 1}`
- Phase markers: observed 3, reachable static opcode `0x94` 4.
- Bottom/side occupancy decisions: 394/376.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 4750 | 3.00 | 2.00 | 0.00 | 336 | -0.58 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |

### Stage 2

- Death frames: 23996, 24687, 26124, 38598
- Cause counts: `{"modeled_committed_prefix_collision": 1, "observed_bullet_overlap": 2, "observed_enemy_body_overlap": 1}`
- Phase markers: observed 2, reachable static opcode `0x94` 3.
- Bottom/side occupancy decisions: 952/621.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 23996 | 3.00 | 21.00 | 0.00 | 349 | -1.37 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 24687 | 3.00 | 7.00 | 0.00 | 254 | -4.60 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 26124 | 3.00 | 2.00 | 0.00 | 564 | -6.54 | - | `observed_enemy_body_overlap` | playfield_boundary,fast_mode |
| 38598 | 3.00 | 4.00 | 0.00 | 721 | 0.42 | - | `observed_bullet_overlap` | fast_mode |

### Stage 3

- Death frames: 45945, 46910, 51473, 52304, 53155, 60338, 68555, 71601
- Cause counts: `{"modeled_committed_prefix_collision": 7, "observed_bullet_overlap": 1}`
- Phase markers: observed 3, reachable static opcode `0x94` 4.
- Bottom/side occupancy decisions: 1013/794.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 45945 | 3.00 | 17.00 | 0.00 | 204 | -3.58 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 46910 | 3.00 | 11.00 | 0.00 | 601 | -2.00 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 51473 | 3.00 | 3.00 | 0.00 | 603 | -3.18 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 52304 | 4.00 | 1.00 | 1.00 | 333 | -3.40 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 53155 | 4.00 | 27.00 | 1.00 | 282 | -0.27 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 60338 | 4.00 | 29.00 | 1.00 | 234 | -7.30 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 68555 | 3.00 | 14.00 | 0.00 | 451 | -2.14 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 71601 | 3.00 | 2.00 | 0.00 | 316 | -1.67 | - | `modeled_committed_prefix_collision` | playfield_boundary |

### Stage 4A / Reimu

- Death frames: 74779, 75367, 76543, 76859, 83110, 84222, 85151, 93798, 95104, 95788, 103597, 104085, 104548, 112404, 116019
- Cause counts: `{"modeled_committed_prefix_collision": 10, "observed_bullet_overlap": 5}`
- Phase markers: observed 7, reachable static opcode `0x94` 8.
- Bottom/side occupancy decisions: 1337/1117.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 74779 | 4.00 | 12.00 | 1.00 | 127 | -1.58 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 75367 | 3.00 | 12.00 | 0.00 | 535 | -2.05 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 76543 | 4.00 | 5.00 | 1.00 | 706 | 0.07 | - | `observed_bullet_overlap` | - |
| 76859 | 3.00 | 2.00 | 0.00 | 822 | -1.26 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 83110 | 3.00 | 3.00 | 0.00 | 161 | -3.01 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 84222 | 3.00 | 3.00 | 0.00 | 525 | -1.46 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 85151 | 3.00 | 0.00 | 0.00 | 617 | -1.45 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 93798 | 3.00 | 1.00 | 0.00 | 635 | -0.31 | - | `observed_bullet_overlap` | playfield_boundary |
| 95104 | 4.00 | 14.00 | 1.00 | 773 | -2.50 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 95788 | 3.00 | 2.00 | 0.00 | 722 | -1.21 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 103597 | 3.00 | 2.00 | 0.00 | 1134 | -2.83 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000 |
| 104085 | 3.00 | 1.00 | 0.00 | 1207 | -1.41 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000,fast_mode |
| 104548 | 4.00 | 1.00 | 1.00 | 1287 | -0.87 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000 |
| 112404 | 3.00 | 2.00 | 0.00 | 694 | -1.88 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 116019 | 3.00 | 4.00 | 0.00 | 1000 | -4.01 | - | `modeled_committed_prefix_collision` | pool_density_over_1000 |

### Stage 5

- Death frames: 120246, 121895, 122823, 130723, 131389, 150018, 152244, 155561, 158940, 159527, 161174, 162189, 162839, 163728
- Cause counts: `{"modeled_committed_prefix_collision": 11, "observed_bullet_overlap": 3}`
- Phase markers: observed 7, reachable static opcode `0x94` 8.
- Bottom/side occupancy decisions: 2559/1311.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 120246 | 3.00 | 5.00 | 0.00 | 672 | -2.20 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 121895 | 3.00 | 1.00 | 0.00 | 972 | -2.24 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 122823 | 3.00 | 9.00 | 0.00 | 562 | -3.54 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 130723 | 3.00 | 1.00 | 0.00 | 362 | -2.64 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 131389 | 3.00 | 9.00 | 0.00 | 294 | -4.23 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 150018 | 5.00 | 8.00 | 2.00 | 1011 | -6.51 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 152244 | 3.00 | 3.00 | 0.00 | 1021 | -5.67 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 155561 | 4.00 | 11.00 | 1.00 | 419 | -1.28 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 158940 | 3.00 | 0.00 | 0.00 | 248 | -2.44 | - | `modeled_committed_prefix_collision` | fast_mode |
| 159527 | 3.00 | 2.00 | 0.00 | 486 | -1.77 | - | `modeled_committed_prefix_collision` | fast_mode |
| 161174 | 3.00 | 9.00 | 0.00 | 362 | -1.76 | - | `modeled_committed_prefix_collision` | fast_mode |
| 162189 | 3.00 | 12.00 | 0.00 | 1091 | 0.64 | - | `observed_bullet_overlap` | pool_density_over_1000,fast_mode |
| 162839 | 3.00 | 1.00 | 0.00 | 1184 | -1.65 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000 |
| 163728 | 3.00 | 9.00 | 0.00 | 1140 | -1.43 | - | `observed_bullet_overlap` | pool_density_over_1000,fast_mode |

### Final B / Kaguya

- Death frames: 172379, 173728, 177084, 177904, 184695, 187241, 197070, 198322, 213662, 216488, 221052, 221546, 222071, 222599, 223202, 223694, 224286, 227802
- Cause counts: `{"modeled_committed_prefix_collision": 12, "observed_laser_overlap": 2, "observed_bullet_overlap": 4}`
- Phase markers: observed 11, reachable static opcode `0x94` 14.
- Bottom/side occupancy decisions: 2529/1715.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 172379 | 3.00 | 102.00 | 0.00 | 388 | -3.65 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 173728 | 3.00 | 86.00 | 0.00 | 260 | -2.69 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 177084 | 4.00 | 71.00 | 1.00 | 844 | -2.35 | - | `modeled_committed_prefix_collision` | fast_mode |
| 177904 | 3.00 | 55.00 | 0.00 | 54 | -2.18 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 184695 | 3.00 | 39.00 | 0.00 | 1095 | -1.34 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000 |
| 187241 | 3.00 | 25.00 | 0.00 | 119 | -4.07 | - | `observed_laser_overlap` | playfield_boundary,fast_mode |
| 197070 | 3.00 | 12.00 | 0.00 | 229 | -1.79 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 198322 | 4.00 | 8.00 | 1.00 | 237 | -3.45 | - | `observed_laser_overlap` | fast_mode |
| 213662 | 3.00 | 1.00 | 0.00 | 421 | -2.90 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 216488 | 3.00 | 0.00 | 0.00 | 379 | 1.80 | - | `observed_bullet_overlap` | - |
| 221052 | 4.00 | 5.00 | 1.00 | 572 | -2.66 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 221546 | 4.00 | 3.00 | 1.00 | 568 | -3.05 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 222071 | 4.00 | 9.00 | 1.00 | 560 | 0.50 | - | `modeled_committed_prefix_collision` | fast_mode |
| 222599 | 3.00 | 10.00 | 0.00 | 554 | -3.30 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 223202 | 3.00 | 9.00 | 0.00 | 579 | -2.93 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 223694 | 3.00 | 1.00 | 0.00 | 572 | -2.44 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 224286 | 3.00 | 2.00 | 0.00 | 594 | -1.30 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 227802 | 3.00 | 14.00 | 0.00 | 898 | -2.50 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |

## Spell Inventory And Runtime Coverage

Every spell below is statically reachable for route 2 Lunatic Final B. Observed decisions count only rows whose live spell state reported that active spell ID. Zero decisions therefore means the run did not enter that spell; zero hits with nonzero decisions means it entered cleanly. `unresolved` means the trace schema did not persist enough live spell state.

### Stage 1

- ECL: `ecldata1.ecl`
- Observed/expected phase-counter markers: 3/4.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 1 | 蛍符「地上の彗星」 | リグル・ナイトバグ | 3 | 6 | 0 | yes | 705 | 1 |
| 5 | 灯符「ファイヤフライフェノメノン」 | リグル・ナイトバグ | 11 | 6 | 0 | yes | 626 | 0 |
| 9 | 蠢符「ナイトバグトルネード」 | リグル・ナイトバグ | 13 | 27 | 0 | yes | 719 | 0 |
| 12 | 隠蟲「永夜蟄居」 | リグル・ナイトバグ | 12 | 27 | 0 | no | 0 | 0 |

### Stage 2

- ECL: `ecldata2.ecl`
- Observed/expected phase-counter markers: 2/3.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 16 | 声符「木菟咆哮」 | ミスティア・ローレライ | 4 | 7 | 0 | yes | 539 | 0 |
| 20 | 猛毒「毒蛾の暗闇演舞」 | ミスティア・ローレライ | 5 | 7 | 0 | yes | 723 | 0 |
| 24 | 鷹符「イルスタードダイブ」 | ミスティア・ローレライ | 6 | 8 | 0 | yes | 732 | 0 |
| 28 | 夜盲「夜雀の歌」 | ミスティア・ローレライ | 8 | 9 | 0 | yes | 853 | 0 |
| 31 | 夜雀「真夜中のコーラスマスター」 | ミスティア・ローレライ | 3 | 7 | 0 | no | 0 | 0 |

### Stage 3

- ECL: `ecldata3.ecl`
- Observed/expected phase-counter markers: 3/4.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 35 | 産霊「ファーストピラミッド」 | 上白沢慧音 | 3 | 0 | 0 | yes | 749 | 2 |
| 38 | 始符「エフェメラリティ137」 | 上白沢慧音 | 2 | 2 | 0 | yes | 658 | 1 |
| 42 | 野符「GHQクライシス」 | 上白沢慧音 | 3 | 3 | 0 | yes | 608 | 0 |
| 46 | 国体「三種の神器　郷」 | 上白沢慧音 | 3 | 0 | 0 | yes | 750 | 1 |
| 50 | 虚史「幻想郷伝説」 | 上白沢慧音 | 1 | 0 | 1 | yes | 582 | 1 |
| 53 | 未来「高天原」 | 上白沢慧音 | 1 | 0 | 1 | no | 0 | 0 |

### Stage 4A / Reimu

- ECL: `ecldata4a.ecl`
- Observed/expected phase-counter markers: 7/8.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 57 | 夢境「二重大結界」 | 博麗霊夢 | 3 | 0 | 0 | yes | 1015 | 2 |
| 61 | 散霊「夢想封印　寂」 | 博麗霊夢 | 3 | 0 | 0 | yes | 1046 | 1 |
| 65 | 神技「八方龍殺陣」 | 博麗霊夢 | 7 | 27 | 0 | yes | 791 | 3 |
| 69 | 回霊「夢想封印　侘」 | 博麗霊夢 | 2 | 17 | 0 | yes | 934 | 1 |
| 73 | 大結界「博麗弾幕結界」 | 博麗霊夢 | 5 | 4 | 0 | yes | 994 | 1 |
| 76 | 神霊「夢想封印　瞬」 | 博麗霊夢 | 2 | 5 | 0 | no | 0 | 0 |

### Stage 5

- ECL: `ecldata5.ecl`
- Observed/expected phase-counter markers: 7/8.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 103 | 幻波「赤眼催眠(マインドブローイング)」 | 鈴仙・Ｕ・イナバ | 6 | 0 | 0 | yes | 732 | 0 |
| 111 | 懶惰「生神停止(マインドストッパー)」 | 鈴仙・Ｕ・イナバ | 3 | 0 | 0 | yes | 854 | 3 |
| 107 | 狂視「狂視調律(イリュージョンシーカー)」 | 鈴仙・Ｕ・イナバ | 3 | 3 | 0 | yes | 990 | 2 |
| 115 | 散符「真実の月(インビジブルフルムーン)」 | 鈴仙・Ｕ・イナバ | 6 | 3 | 0 | yes | 914 | 3 |
| 118 | 月眼「月兎遠隔催眠術(テレメスメリズム)」 | 鈴仙・Ｕ・イナバ | 4 | 2 | 0 | no | 0 | 0 |

### Final B / Kaguya

- ECL: `ecldata7.ecl`
- Observed/expected phase-counter markers: 11/14.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 150 | 薬符「壺中の大銀河」 | 八意永琳 | 4 | 0 | 0 | yes | 748 | 2 |
| 154 | 神宝「ブリリアントドラゴンバレッタ」 | 蓬莱山輝夜 | 5 | 1 | 5 | yes | 521 | 1 |
| 158 | 神宝「ブディストダイアモンド」 | 蓬莱山輝夜 | 4 | 4 | 2 | yes | 1382 | 2 |
| 162 | 神宝「サラマンダーシールド」 | 蓬莱山輝夜 | 4 | 8 | 2 | yes | 1505 | 0 |
| 166 | 神宝「ライフスプリングインフィニティ」 | 蓬莱山輝夜 | 3 | 2 | 2 | yes | 1379 | 2 |
| 170 | 神宝「蓬莱の玉の枝  -夢色の郷-」 | 蓬莱山輝夜 | 26 | 3 | 0 | yes | 1734 | 7 |
| 174 | 「永夜返し  -待宵-」 | 蓬莱山輝夜 | 3 | 1 | 0 | yes | 367 | 1 |
| 178 | 「永夜返し  -子の四つ-」 | 蓬莱山輝夜 | 3 | 2 | 0 | yes | 215 | 0 |
| 182 | 「永夜返し  -丑の四つ-」 | 蓬莱山輝夜 | 2 | 2 | 0 | no | 0 | 0 |
| 186 | 「永夜返し  -寅の四つ-」 | 蓬莱山輝夜 | 4 | 4 | 0 | no | 0 | 0 |
| 190 | 「永夜返し  -世明け-」 | 蓬莱山輝夜 | 12 | 5 | 0 | no | 0 | 0 |

## Runtime And Harness Findings

- Observed auto-Z stall frames: none.
- Route termination: `route_complete` at completion probe frame 230561.
- Unique robust solutions observed: 0; solve time median/p95/max -/-/- ms.
- First-observed policy age median/p95/max: -/-/- frames.
- Viability queries available: 0/0; robustly constrained decisions: 0/57553.
- Robust-policy decisions without any usable query: 0/0.
- Global-horizon/local-prefix cross-tab: 0 decisions; winning global state with unsafe selected prefix: 0; losing global state with safe short prefix: 0; selected globally certified action contradicted by the fresh local prefix checker: 0; selected action outside the reported winning set: 0.
- Live spell attribution was recorded at every hit edge; exact per-spell counts are preserved below.
- `0` hit edges remain in the `sensor_gap_or_unmodeled_hazard` class and require executor-level same-frame emission/transform evidence.

## Next Regression Work

1. Keep robust backward-reachability solves within the finite policy horizon, then verify nonzero live query and constrained-decision counts.
2. Replay all 60 retained witnesses through the integrated executor and preserve one regression per concrete failure.
3. Re-run focused Stage 4A and Final B practices before another full Lunatic route; compare hit frames, policy age, action-set exhaustion, and cluster recurrence.
4. Add item/Power state and finite Bomb resources only after the no-Bomb movement policy has passed physical validation.
