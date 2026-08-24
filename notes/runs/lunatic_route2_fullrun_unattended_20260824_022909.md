# TH08 Lunatic Full-Run Review: lunatic_route2_fullrun_unattended_20260824_022909

## Result

- Route: Sakuya/Remilia, Lunatic, Final B / Kaguya.
- Combat completion: yes; gameplay scene unloaded at frame 224868.
- Native phase-2 hit edges, including Last-Spell-saveable edges: 61.
- Deathbomb requests at those edges: 0.
- Hard no-Bomb input verification: passed across 55915 decisions.
- Post-hit Bomb-stock decreases: 17.00; this is respawn-stock reset telemetry, not evidence of Bomb input.
- Agent decisions: 55915.
- Raw trace size: 1988879241 bytes across 1 segments.
- JSON decode errors: 0.
- Exact spell-level hit attribution: available from live `g_spell_card_state`.

The run is valid for stage-, death-, resource-, projectile-, latency-, and route-level analysis. Spell names below are the statically reachable Lunatic route inventory; unavailable runtime hit counts remain explicitly unresolved instead of guessed. The no-life patch allows post-hit resource resets to repeat, so resource-stock changes must not be interpreted as Bomb commands.

## Trace Integrity

| Segment | Frames | Decisions | Wall Z | Termination | Runtime error | SHA-256 |
| --- | ---: | ---: | ---: | --- | --- | --- |
| 1 | 2..224868 | 55915 | 422 | route_complete | - | `10da0dcb3f2db66967c5272b2543b0effd76f3405615648e7eea1f7e7f4affc0` |

The route is one continuous agent-controlled trace with no foreground interruption or manual re-arm gap.

## Stage Summary

| Stage | Frames | Decisions | Native hits | Deathbombs | Post-hit Bomb-stock decrease | Power start/end/min | Max bullets | Max lasers |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Stage 1 | 2..21008 | 5157 | 5 | 0 | 1.00 | 0.00/2.00/0.00 | 1179 | 0 |
| Stage 2 | 21008..44737 | 7011 | 2 | 0 | 0.00 | 7.00/12.00/0.00 | 1208 | 0 |
| Stage 3 | 44737..72262 | 7406 | 5 | 0 | 3.00 | 18.00/26.00/0.00 | 1214 | 200 |
| Stage 4A / Reimu | 72262..117893 | 11370 | 15 | 0 | 7.00 | 31.00/2.00/0.00 | 1530 | 0 |
| Stage 5 | 117893..161542 | 9156 | 15 | 0 | 3.00 | 7.00/0.00/0.00 | 1530 | 0 |
| Final B / Kaguya | 161543..224868 | 15815 | 19 | 0 | 3.00 | 5.00/6.00/0.00 | 1262 | 240 |

## Failure Taxonomy

| Primary class | Deaths | Interpretation |
| --- | ---: | --- |
| `modeled_committed_prefix_collision` | 48 | The measured three-frame input pipeline was already unsafe. |
| `observed_bullet_overlap` | 12 | A bullet overlaps the native player AABB in the hit observation. |
| `observed_laser_overlap` | 1 | The player overlaps an active laser's exact finite segment; TH08 checks this before the broad bullet pass. |

Contributing factors:

- `playfield_boundary`: 53 deaths
- `fast_mode`: 43 deaths
- `pool_density_over_1000`: 9 deaths

## High-Risk Clusters

| Cluster | Stage | Frames | Deaths | Min Power | Max bullets at hit |
| --- | --- | ---: | ---: | ---: | ---: |
| cluster-47 | Final B / Kaguya | 217759..220759 | 7 | 1.00 | 579 |
| cluster-03 | Stage 1 | 6829..7303 | 2 | 1.00 | 378 |
| cluster-05 | Stage 2 | 23267..23849 | 2 | 0.00 | 142 |
| cluster-16 | Stage 4A / Reimu | 85015..85409 | 2 | 0.00 | 616 |
| cluster-17 | Stage 4A / Reimu | 94969..95463 | 2 | 2.00 | 873 |
| cluster-18 | Stage 4A / Reimu | 103699..104049 | 2 | 0.00 | 1181 |
| cluster-41 | Final B / Kaguya | 174093..174525 | 2 | 51.00 | 630 |

## Stage Detail

### Stage 1

- Death frames: 3386, 5549, 6829, 7303, 13822
- Cause counts: `{"modeled_committed_prefix_collision": 3, "observed_bullet_overlap": 2}`
- Phase markers: observed 3, reachable static opcode `0x94` 4.
- Bottom/side occupancy decisions: 401/454.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 3386 | 3.00 | 20.00 | 0.00 | 37 | -2.36 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 5549 | 3.00 | 5.00 | 0.00 | 301 | -5.94 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 6829 | 3.00 | 8.00 | 0.00 | 57 | -1.39 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 7303 | 4.00 | 1.00 | 1.00 | 378 | -3.13 | - | `observed_bullet_overlap` | playfield_boundary |
| 13822 | 3.00 | 9.00 | 0.00 | 365 | -0.04 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |

### Stage 2

- Death frames: 23267, 23849
- Cause counts: `{"modeled_committed_prefix_collision": 2}`
- Phase markers: observed 2, reachable static opcode `0x94` 3.
- Bottom/side occupancy decisions: 892/911.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 23267 | 3.00 | 14.00 | 0.00 | 121 | -1.69 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 23849 | 3.00 | 0.00 | 0.00 | 142 | -3.44 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |

### Stage 3

- Death frames: 50865, 51992, 53532, 59169, 60357
- Cause counts: `{"modeled_committed_prefix_collision": 4, "observed_bullet_overlap": 1}`
- Phase markers: observed 3, reachable static opcode `0x94` 4.
- Bottom/side occupancy decisions: 1134/813.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 50865 | 3.00 | 22.00 | 0.00 | 329 | -2.41 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 51992 | 3.00 | 7.00 | 0.00 | 323 | -1.57 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 53532 | 4.00 | 26.00 | 1.00 | 541 | -2.55 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 59169 | 5.00 | 40.00 | 2.00 | 381 | -3.71 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 60357 | 3.00 | 25.00 | 0.00 | 227 | -4.05 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |

### Stage 4A / Reimu

- Death frames: 74051, 75231, 76128, 82114, 84268, 85015, 85409, 94969, 95463, 103699, 104049, 109693, 111806, 112831, 115509
- Cause counts: `{"modeled_committed_prefix_collision": 12, "observed_bullet_overlap": 3}`
- Phase markers: observed 7, reachable static opcode `0x94` 8.
- Bottom/side occupancy decisions: 1532/1148.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 74051 | 3.00 | 34.00 | 0.00 | 508 | -3.53 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 75231 | 3.00 | 21.00 | 0.00 | 604 | -2.30 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 76128 | 3.00 | 8.00 | 0.00 | 599 | -2.51 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 82114 | 5.00 | 7.00 | 2.00 | 503 | 3.11 | - | `observed_bullet_overlap` | fast_mode |
| 84268 | 3.00 | 1.00 | 0.00 | 610 | -2.42 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 85015 | 4.00 | 0.00 | 1.00 | 616 | -1.56 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 85409 | 4.00 | 0.00 | 1.00 | 607 | -3.84 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 94969 | 4.00 | 2.00 | 1.00 | 873 | -2.74 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 95463 | 3.00 | 3.00 | 0.00 | 752 | -1.33 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 103699 | 4.00 | 3.00 | 1.00 | 1181 | -2.25 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 104049 | 3.00 | 0.00 | 0.00 | 1139 | 0.09 | - | `observed_bullet_overlap` | playfield_boundary,pool_density_over_1000,fast_mode |
| 109693 | 3.00 | 9.00 | 0.00 | 87 | -3.31 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 111806 | 3.00 | 0.00 | 0.00 | 641 | -1.32 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 112831 | 3.00 | 0.00 | 0.00 | 742 | -3.64 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 115509 | 4.00 | 9.00 | 1.00 | 1000 | -1.69 | - | `modeled_committed_prefix_collision` | pool_density_over_1000,fast_mode |

### Stage 5

- Death frames: 120668, 121386, 122309, 129537, 130687, 147765, 149594, 152328, 152949, 153885, 156130, 156864, 157642, 159562, 160244
- Cause counts: `{"modeled_committed_prefix_collision": 12, "observed_bullet_overlap": 3}`
- Phase markers: observed 7, reachable static opcode `0x94` 8.
- Bottom/side occupancy decisions: 2111/1444.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 120668 | 3.00 | 7.00 | 0.00 | 1237 | -1.25 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000 |
| 121386 | 3.00 | 2.00 | 0.00 | 997 | -1.59 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 122309 | 3.00 | 2.00 | 0.00 | 557 | -0.32 | - | `observed_bullet_overlap` | playfield_boundary |
| 129537 | 3.00 | 0.00 | 0.00 | 910 | -1.95 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 130687 | 3.00 | 0.00 | 0.00 | 343 | -3.26 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 147765 | 5.00 | 9.00 | 2.00 | 1005 | -5.25 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 149594 | 4.00 | 1.00 | 1.00 | 1010 | -6.54 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 152328 | 3.00 | 11.00 | 0.00 | 430 | -3.57 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 152949 | 3.00 | 8.00 | 0.00 | 511 | -2.80 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 153885 | 3.00 | 1.00 | 0.00 | 383 | -2.02 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 156130 | 3.00 | 1.00 | 0.00 | 353 | -2.28 | - | `modeled_committed_prefix_collision` | - |
| 156864 | 3.00 | 3.00 | 0.00 | 336 | -2.81 | - | `observed_bullet_overlap` | fast_mode |
| 157642 | 3.00 | 1.00 | 0.00 | 330 | -2.57 | - | `modeled_committed_prefix_collision` | - |
| 159562 | 3.00 | 5.00 | 0.00 | 1147 | -1.33 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 160244 | 3.00 | 0.00 | 0.00 | 1195 | -2.14 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |

### Final B / Kaguya

- Death frames: 162392, 169179, 173240, 174093, 174525, 181852, 199946, 209614, 211071, 213961, 217759, 218266, 218749, 219225, 219759, 220270, 220759, 221430, 224664
- Cause counts: `{"modeled_committed_prefix_collision": 15, "observed_bullet_overlap": 3, "observed_laser_overlap": 1}`
- Phase markers: observed 10, reachable static opcode `0x94` 14.
- Bottom/side occupancy decisions: 2380/1911.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 162392 | 3.00 | 5.00 | 0.00 | 847 | -2.00 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 169179 | 3.00 | 90.00 | 0.00 | 736 | 1.02 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 173240 | 3.00 | 82.00 | 0.00 | 663 | -3.25 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 174093 | 3.00 | 66.00 | 0.00 | 313 | -1.70 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 174525 | 3.00 | 51.00 | 0.00 | 630 | -3.74 | - | `observed_bullet_overlap` | playfield_boundary |
| 181852 | 3.00 | 37.00 | 0.00 | 1195 | -2.95 | - | `modeled_committed_prefix_collision` | pool_density_over_1000,fast_mode |
| 199946 | 4.00 | 23.00 | 1.00 | 694 | -2.31 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 209614 | 3.00 | 7.00 | 0.00 | 446 | -2.24 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 211071 | 3.00 | 9.00 | 0.00 | 460 | -2.94 | - | `modeled_committed_prefix_collision` | fast_mode |
| 213961 | 3.00 | 0.00 | 0.00 | 275 | -2.48 | - | `observed_laser_overlap` | playfield_boundary,fast_mode |
| 217759 | 3.00 | 14.00 | 0.00 | 558 | -1.81 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 218266 | 3.00 | 8.00 | 0.00 | 561 | -2.87 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 218749 | 3.00 | 1.00 | 0.00 | 560 | -2.11 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 219225 | 3.00 | 11.00 | 0.00 | 579 | -1.35 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 219759 | 4.00 | 10.00 | 1.00 | 574 | -3.57 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 220270 | 3.00 | 1.00 | 0.00 | 567 | -2.42 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 220759 | 4.00 | 9.00 | 1.00 | 559 | -0.06 | - | `observed_bullet_overlap` | - |
| 221430 | 3.00 | 2.00 | 0.00 | 584 | -2.66 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 224664 | 3.00 | 6.00 | 0.00 | 898 | -1.52 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |

## Spell Inventory And Runtime Coverage

Every spell below is statically reachable for route 2 Lunatic Final B. Observed decisions count only rows whose live spell state reported that active spell ID. Zero decisions therefore means the run did not enter that spell; zero hits with nonzero decisions means it entered cleanly. `unresolved` means the trace schema did not persist enough live spell state.

### Stage 1

- ECL: `ecldata1.ecl`
- Observed/expected phase-counter markers: 3/4.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 1 | 蛍符「地上の彗星」 | リグル・ナイトバグ | 3 | 6 | 0 | yes | 683 | 1 |
| 5 | 灯符「ファイヤフライフェノメノン」 | リグル・ナイトバグ | 11 | 6 | 0 | yes | 600 | 1 |
| 9 | 蠢符「ナイトバグトルネード」 | リグル・ナイトバグ | 13 | 27 | 0 | yes | 704 | 0 |
| 12 | 隠蟲「永夜蟄居」 | リグル・ナイトバグ | 12 | 27 | 0 | no | 0 | 0 |

### Stage 2

- ECL: `ecldata2.ecl`
- Observed/expected phase-counter markers: 2/3.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 16 | 声符「木菟咆哮」 | ミスティア・ローレライ | 4 | 7 | 0 | yes | 526 | 0 |
| 20 | 猛毒「毒蛾の暗闇演舞」 | ミスティア・ローレライ | 5 | 7 | 0 | yes | 672 | 0 |
| 24 | 鷹符「イルスタードダイブ」 | ミスティア・ローレライ | 6 | 8 | 0 | yes | 707 | 0 |
| 28 | 夜盲「夜雀の歌」 | ミスティア・ローレライ | 8 | 9 | 0 | yes | 836 | 0 |
| 31 | 夜雀「真夜中のコーラスマスター」 | ミスティア・ローレライ | 3 | 7 | 0 | no | 0 | 0 |

### Stage 3

- ECL: `ecldata3.ecl`
- Observed/expected phase-counter markers: 3/4.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 35 | 産霊「ファーストピラミッド」 | 上白沢慧音 | 3 | 0 | 0 | yes | 749 | 2 |
| 38 | 始符「エフェメラリティ137」 | 上白沢慧音 | 2 | 2 | 0 | yes | 679 | 1 |
| 42 | 野符「GHQクライシス」 | 上白沢慧音 | 3 | 3 | 0 | yes | 657 | 0 |
| 46 | 国体「三種の神器　郷」 | 上白沢慧音 | 3 | 0 | 0 | yes | 759 | 0 |
| 50 | 虚史「幻想郷伝説」 | 上白沢慧音 | 1 | 0 | 1 | yes | 569 | 0 |
| 53 | 未来「高天原」 | 上白沢慧音 | 1 | 0 | 1 | no | 0 | 0 |

### Stage 4A / Reimu

- ECL: `ecldata4a.ecl`
- Observed/expected phase-counter markers: 7/8.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 57 | 夢境「二重大結界」 | 博麗霊夢 | 3 | 0 | 0 | yes | 1021 | 3 |
| 61 | 散霊「夢想封印　寂」 | 博麗霊夢 | 3 | 0 | 0 | yes | 1018 | 0 |
| 65 | 神技「八方龍殺陣」 | 博麗霊夢 | 7 | 27 | 0 | yes | 784 | 2 |
| 69 | 回霊「夢想封印　侘」 | 博麗霊夢 | 2 | 17 | 0 | yes | 936 | 2 |
| 73 | 大結界「博麗弾幕結界」 | 博麗霊夢 | 5 | 4 | 0 | yes | 954 | 1 |
| 76 | 神霊「夢想封印　瞬」 | 博麗霊夢 | 2 | 5 | 0 | no | 0 | 0 |

### Stage 5

- ECL: `ecldata5.ecl`
- Observed/expected phase-counter markers: 7/8.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 103 | 幻波「赤眼催眠(マインドブローイング)」 | 鈴仙・Ｕ・イナバ | 6 | 0 | 0 | yes | 723 | 0 |
| 111 | 懶惰「生神停止(マインドストッパー)」 | 鈴仙・Ｕ・イナバ | 3 | 0 | 0 | yes | 856 | 3 |
| 107 | 狂視「狂視調律(イリュージョンシーカー)」 | 鈴仙・Ｕ・イナバ | 3 | 3 | 0 | yes | 752 | 2 |
| 115 | 散符「真実の月(インビジブルフルムーン)」 | 鈴仙・Ｕ・イナバ | 6 | 3 | 0 | yes | 891 | 2 |
| 118 | 月眼「月兎遠隔催眠術(テレメスメリズム)」 | 鈴仙・Ｕ・イナバ | 4 | 2 | 0 | no | 0 | 0 |

### Final B / Kaguya

- ECL: `ecldata7.ecl`
- Observed/expected phase-counter markers: 10/14.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 150 | 薬符「壺中の大銀河」 | 八意永琳 | 4 | 0 | 0 | yes | 778 | 3 |
| 154 | 神宝「ブリリアントドラゴンバレッタ」 | 蓬莱山輝夜 | 5 | 1 | 5 | yes | 947 | 0 |
| 158 | 神宝「ブディストダイアモンド」 | 蓬莱山輝夜 | 4 | 4 | 2 | yes | 1484 | 0 |
| 162 | 神宝「サラマンダーシールド」 | 蓬莱山輝夜 | 4 | 8 | 2 | yes | 1547 | 0 |
| 166 | 神宝「ライフスプリングインフィニティ」 | 蓬莱山輝夜 | 3 | 2 | 2 | yes | 1383 | 2 |
| 170 | 神宝「蓬莱の玉の枝  -夢色の郷-」 | 蓬莱山輝夜 | 26 | 3 | 0 | yes | 1752 | 8 |
| 174 | 「永夜返し  -待宵-」 | 蓬莱山輝夜 | 3 | 1 | 0 | yes | 229 | 1 |
| 178 | 「永夜返し  -子の四つ-」 | 蓬莱山輝夜 | 3 | 2 | 0 | no | 0 | 0 |
| 182 | 「永夜返し  -丑の四つ-」 | 蓬莱山輝夜 | 2 | 2 | 0 | no | 0 | 0 |
| 186 | 「永夜返し  -寅の四つ-」 | 蓬莱山輝夜 | 4 | 4 | 0 | no | 0 | 0 |
| 190 | 「永夜返し  -世明け-」 | 蓬莱山輝夜 | 12 | 5 | 0 | no | 0 | 0 |

## OPT-001 Physical Interpretation

This run is the physical gate for the persistent 64-slot enemy-prefix RPM
destination implemented at commit
`6305dabae9ee6f6b29f5ad1588e2dfab8a079bae`. The controller config records
`read_path: persistent_read_into` and one sequentially shared planning/issue
destination. The route terminated naturally at frame 224868; the nonbinding
86,400-second duration did not participate, hard no-Bomb passed, and the
isolated Wine host reported no prefix leftovers.

| Metric | 58-hit reference median / p95 | This run median / p95 | Delta median / p95 |
| --- | ---: | ---: | ---: |
| Planning enemy-prefix capture, ms | 2.764 / 3.317 | 1.543 / 1.929 | -1.221 / -1.388 |
| Issue enemy-prefix capture, ms | 2.944 / 5.499 | 1.707 / 2.967 | -1.236 / -2.532 |
| All pool reads, ms | 10.468 / 12.168 | 9.371 / 11.358 | -1.097 / -0.810 |
| Issue path to input, ms | 3.945 / 13.489 | 2.620 / 12.242 | -1.326 / -1.247 |
| Observe to input, ms | 47.590 / 67.279 | 45.084 / 66.613 | -2.505 / -0.665 |
| Action lag, frames | 2 / 3 | 2 / 3 | 0 / 0 |

All six stage pool-read medians improved. The change is therefore retained on
its named latency mechanism and semantic-parity evidence. The 61 versus 58 hit
total is different-RNG and observational. It does not establish a policy
improvement: 48/61 hits remain modeled committed-prefix collisions, with 53
boundary and 43 fast-mode attributions. The next work must separately address
remaining capture/issue latency, future-birth coverage, and boundary/focus
selection.

## Runtime And Harness Findings

- Observed auto-Z stall frames: none.
- Route termination: `route_complete` at completion probe frame 224868.
- Unique robust solutions observed: 0; solve time median/p95/max -/-/- ms.
- First-observed policy age median/p95/max: -/-/- frames.
- Viability queries available: 0/0; robustly constrained decisions: 0/55915.
- Robust-policy decisions without any usable query: 0/0.
- Global-horizon/local-prefix cross-tab: 0 decisions; winning global state with unsafe selected prefix: 0; losing global state with safe short prefix: 0; selected globally certified action contradicted by the fresh local prefix checker: 0; selected action outside the reported winning set: 0.
- Live spell attribution was recorded at every hit edge; exact per-spell counts are preserved below.
- `0` hit edges remain in the `sensor_gap_or_unmodeled_hazard` class and require executor-level same-frame emission/transform evidence.

## Next Regression Work

1. Keep robust backward-reachability solves within the finite policy horizon, then verify nonzero live query and constrained-decision counts.
2. Replay all 61 retained witnesses through the integrated executor and preserve one regression per concrete failure.
3. Re-run focused Stage 4A and Final B practices before another full Lunatic route; compare hit frames, policy age, action-set exhaustion, and cluster recurrence.
4. Add item/Power state and finite Bomb resources only after the no-Bomb movement policy has passed physical validation.
