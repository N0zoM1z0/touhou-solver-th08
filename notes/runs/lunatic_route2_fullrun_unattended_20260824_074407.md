# TH08 Lunatic Full-Run Review: lunatic_route2_fullrun_unattended_20260824_074407

## Result

- Route: Sakuya/Remilia, Lunatic, Final B / Kaguya.
- Solver commit: `8b1c3de4de4f5c776644aaebab68e18d649eba2b` (clean worktree at launch).
- Combat completion: yes; gameplay scene unloaded at frame 226632.
- Native phase-2 hit edges, including Last-Spell-saveable edges: 57.
- Deathbomb requests at those edges: 0.
- Hard no-Bomb input verification: passed across 56539 decisions.
- Post-hit Bomb-stock decreases: 15.00; this is respawn-stock reset telemetry, not evidence of Bomb input.
- Agent decisions: 56539.
- Raw trace size: 2223813483 bytes across 1 segments.
- JSON decode errors: 0.
- Exact spell-level hit attribution: available from live `g_spell_card_state`.

The run is valid for stage-, death-, resource-, projectile-, latency-, and route-level analysis. Spell names below are the statically reachable Lunatic route inventory; unavailable runtime hit counts remain explicitly unresolved instead of guessed. The no-life patch allows post-hit resource resets to repeat, so resource-stock changes must not be interpreted as Bomb commands.

## Trace Integrity

| Segment | Frames | Decisions | Wall Z | Termination | Runtime error | SHA-256 |
| --- | ---: | ---: | ---: | --- | --- | --- |
| 1 | 1..226632 | 56539 | 420 | route_complete | - | `5fbf9906e06ec66c7b6fef05b6e04ffe78b10fb500063e33cbb5f59db600f242` |

The route is one continuous agent-controlled trace with no foreground interruption or manual re-arm gap.

## Stage Summary

| Stage | Frames | Decisions | Native hits | Deathbombs | Post-hit Bomb-stock decrease | Power start/end/min | Max bullets | Max lasers |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Stage 1 | 1..20943 | 5160 | 3 | 0 | 0.00 | 0.00/0.00/0.00 | 1173 | 0 |
| Stage 2 | 20943..44673 | 7117 | 7 | 0 | 0.00 | 5.00/2.00/0.00 | 1197 | 0 |
| Stage 3 | 44673..72481 | 7545 | 4 | 0 | 1.00 | 8.00/44.00/0.00 | 938 | 200 |
| Stage 4A / Reimu | 72481..118281 | 11535 | 15 | 0 | 6.00 | 49.00/1.00/0.00 | 1361 | 0 |
| Stage 5 | 118281..162934 | 9533 | 10 | 0 | 4.00 | 6.00/2.00/0.00 | 1532 | 0 |
| Final B / Kaguya | 162934..226632 | 15649 | 18 | 0 | 4.00 | 7.00/18.00/0.00 | 1252 | 255 |

## Comparison With The 60-Hit Source-Audit Baseline

The immediate baseline is run `lunatic_route2_fullrun_unattended_20260824_051944`
at commit `6b5d2d9bc26cfe0cbdea6dff4fd2566be6967c6e`.  The stage counts changed from
`1/4/8/15/14/18` to `3/7/4/15/10/18`.  In particular, Stage 4A remained
exactly 15 hits and Final B remained exactly 18; the three-hit total decrease
is distributed across different earlier-stage native RNG and post-hit roots.
GEO-001B was shadow-only and had no action authority, so the `60 -> 57`
difference is not evidence that its collision correction prevented three
hits.

Stage-4A timing also did not regress: read median/p95 changed from
`9.450/11.543 ms` to `8.619/10.370 ms`, plan median/p95 from
`32.465/50.844 ms` to `31.410/49.044 ms`, and action-lag median/p95 remained
`2/3` frames.  This rules out the collision shadow as the proposed cause of a
Stage-4A slowdown.  Both routes still recorded zero global submissions,
queries, solutions, or constrained decisions, so the VPS had no strategic
search workload with which to improve the hit count.

## Source-Collision Shadow Corpus

The tracked
`lunatic_route2_fullrun_unattended_20260824_074407.source_collision_audit.json`
was streamed from the complete 2.22 GB trace.  Across 56,539 decisions it
contains 21,394,298 current-pool bullet observations.  The legacy selector
included 2,689,327 observations (12.5703%) which the authoritative current-
frame lifecycle predicate excludes.  Native state totals were
`state1=19,545,936`, `state2=1,345,200`, `state3=25,034`,
`state4=93,130`, and `state5=384,998`.

Stage 5 is the outlier: 1,125,175 of 4,973,810 legacy candidates (22.6220%)
were source-nonlethal.  Of these, 840,965 are state-1 observations on 1,120
decision frames where Reisen's callback auxiliary byte suppresses collision.
Stage 4A instead has 484,249 of 4,214,434 legacy-only observations (11.4902%)
and no callback suppression.  This is strong evidence of Stage-5-specific
modeling debt, not a causal claim about individual hits or the ten-hit count.

The runtime player half-extents were `(1,1)` and stable on all 56,539 control
roots.  The cached AABB was coherent on 55,890 roots; the 649 remaining roots
must not be treated as a position-derived exact cache.  Lasers contributed
393,216 observations on 5,100 decisions, with a maximum live pool of 255.
The trace retains nearby geometry only within 160 pixels, so this ledger is
authoritative for complete current-pool lifecycle counts and density, but not
for route-wide geometric replay, hit causality, future lifecycle transitions,
bit-exact laser trigonometry, or action selection.

## Failure Taxonomy

| Primary class | Deaths | Interpretation |
| --- | ---: | --- |
| `modeled_committed_prefix_collision` | 40 | The hit-row committed pipeline or the causal last-alive selected-action certificate was already unsafe. |
| `observed_bullet_overlap` | 16 | A bullet overlaps the native player AABB in the hit observation. |
| `observed_multiple_hazard_overlap` | 1 | More than one captured native hazard family overlaps at the hit edge; the trace does not invent a single causal winner. |

Contributing factors:

- `playfield_boundary`: 48 deaths
- `fast_mode`: 38 deaths
- `pool_density_over_1000`: 11 deaths

## High-Risk Clusters

| Cluster | Stage | Frames | Deaths | Min Power | Max bullets at hit |
| --- | --- | ---: | ---: | ---: | ---: |
| cluster-41 | Final B / Kaguya | 220124..222663 | 6 | 1.00 | 578 |
| cluster-18 | Stage 4A / Reimu | 94659..95457 | 3 | 0.00 | 825 |
| cluster-01 | Stage 1 | 2287..2829 | 2 | 1.00 | 168 |
| cluster-06 | Stage 2 | 25511..26099 | 2 | 1.00 | 455 |
| cluster-16 | Stage 4A / Reimu | 84847..85357 | 2 | 23.00 | 636 |
| cluster-23 | Stage 4A / Reimu | 116523..117002 | 2 | 1.00 | 1322 |
| cluster-35 | Final B / Kaguya | 175466..175830 | 2 | 45.00 | 571 |
| cluster-36 | Final B / Kaguya | 176454..176812 | 2 | 13.00 | 591 |
| cluster-39 | Final B / Kaguya | 212883..213360 | 2 | 1.00 | 284 |

## Stage Detail

### Stage 1

- Death frames: 2287, 2829, 13831
- Cause counts: `{"modeled_committed_prefix_collision": 2, "observed_bullet_overlap": 1}`
- Phase markers: observed 3, reachable static opcode `0x94` 4.
- Bottom/side occupancy decisions: 450/300.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 2287 | 3.00 | 1.00 | 0.00 | 168 | -3.77 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 2829 | 3.00 | 1.00 | 0.00 | 164 | -2.10 | - | `observed_bullet_overlap` | playfield_boundary |
| 13831 | 3.00 | 8.00 | 0.00 | 419 | -1.27 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |

### Stage 2

- Death frames: 22532, 23909, 24807, 25511, 26099, 38558, 39387
- Cause counts: `{"modeled_committed_prefix_collision": 6, "observed_bullet_overlap": 1}`
- Phase markers: observed 2, reachable static opcode `0x94` 3.
- Bottom/side occupancy decisions: 939/678.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 22532 | 3.00 | 15.00 | 0.00 | 164 | -1.40 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 23909 | 3.00 | 1.00 | 0.00 | 447 | -2.21 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 24807 | 3.00 | 1.00 | 0.00 | 79 | 0.10 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 25511 | 3.00 | 10.00 | 0.00 | 165 | -2.26 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 26099 | 3.00 | 1.00 | 0.00 | 455 | -12.41 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 38558 | 3.00 | 11.00 | 0.00 | 718 | -3.06 | - | `modeled_committed_prefix_collision` | - |
| 39387 | 3.00 | 0.00 | 0.00 | 831 | -1.83 | - | `modeled_committed_prefix_collision` | playfield_boundary |

### Stage 3

- Death frames: 46886, 51140, 52913, 53675
- Cause counts: `{"modeled_committed_prefix_collision": 3, "observed_bullet_overlap": 1}`
- Phase markers: observed 3, reachable static opcode `0x94` 4.
- Bottom/side occupancy decisions: 960/752.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 46886 | 3.00 | 11.00 | 0.00 | 480 | -4.39 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 51140 | 3.00 | 16.00 | 0.00 | 320 | 0.95 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 52913 | 4.00 | 4.00 | 1.00 | 703 | -3.02 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 53675 | 3.00 | 1.00 | 0.00 | 619 | -2.90 | - | `modeled_committed_prefix_collision` | playfield_boundary |

### Stage 4A / Reimu

- Death frames: 75259, 76386, 81473, 84847, 85357, 86257, 94659, 94962, 95457, 103208, 104621, 110904, 115836, 116523, 117002
- Cause counts: `{"observed_bullet_overlap": 5, "modeled_committed_prefix_collision": 10}`
- Phase markers: observed 7, reachable static opcode `0x94` 8.
- Bottom/side occupancy decisions: 1379/1049.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 75259 | 5.00 | 57.00 | 2.00 | 495 | -1.67 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 76386 | 3.00 | 55.00 | 0.00 | 677 | -2.21 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 81473 | 3.00 | 42.00 | 0.00 | 172 | -2.41 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 84847 | 3.00 | 36.00 | 0.00 | 609 | -3.23 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 85357 | 3.00 | 23.00 | 0.00 | 636 | -3.60 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 86257 | 4.00 | 16.00 | 1.00 | 581 | 0.28 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 94659 | 4.00 | 2.00 | 1.00 | 339 | -3.09 | - | `observed_bullet_overlap` | playfield_boundary |
| 94962 | 3.00 | 0.00 | 0.00 | 825 | -3.11 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 95457 | 3.00 | 9.00 | 0.00 | 586 | -1.98 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 103208 | 3.00 | 9.00 | 0.00 | 1232 | -1.47 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 104621 | 4.00 | 0.00 | 1.00 | 1234 | -2.32 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 110904 | 4.00 | 9.00 | 1.00 | 419 | -5.65 | - | `modeled_committed_prefix_collision` | fast_mode |
| 115836 | 3.00 | 11.00 | 0.00 | 980 | -0.55 | - | `modeled_committed_prefix_collision` | fast_mode |
| 116523 | 3.00 | 1.00 | 0.00 | 1281 | -2.26 | - | `observed_bullet_overlap` | pool_density_over_1000,fast_mode |
| 117002 | 3.00 | 1.00 | 0.00 | 1322 | -3.51 | - | `modeled_committed_prefix_collision` | pool_density_over_1000,fast_mode |

### Stage 5

- Death frames: 122507, 132446, 142266, 143347, 149538, 150286, 154249, 159518, 160786, 161401
- Cause counts: `{"observed_bullet_overlap": 3, "modeled_committed_prefix_collision": 7}`
- Phase markers: observed 7, reachable static opcode `0x94` 8.
- Bottom/side occupancy decisions: 2244/1012.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 122507 | 4.00 | 13.00 | 1.00 | 614 | -5.19 | - | `observed_bullet_overlap` | playfield_boundary |
| 132446 | 4.00 | 0.00 | 1.00 | 509 | -1.57 | - | `observed_bullet_overlap` | playfield_boundary |
| 142266 | 5.00 | 8.00 | 2.00 | 1116 | -2.01 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 143347 | 3.00 | 9.00 | 0.00 | 1032 | -1.95 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 149538 | 3.00 | 1.00 | 0.00 | 1003 | -5.41 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000 |
| 150286 | 3.00 | 10.00 | 0.00 | 1017 | -7.79 | - | `modeled_committed_prefix_collision` | pool_density_over_1000 |
| 154249 | 3.00 | 10.00 | 0.00 | 431 | -2.80 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 159518 | 3.00 | 9.00 | 0.00 | 508 | -2.03 | - | `modeled_committed_prefix_collision` | fast_mode |
| 160786 | 3.00 | 6.00 | 0.00 | 1138 | -3.37 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 161401 | 3.00 | 1.00 | 0.00 | 1166 | -1.83 | - | `observed_bullet_overlap` | pool_density_over_1000 |

### Final B / Kaguya

- Death frames: 171575, 175466, 175830, 176454, 176812, 182136, 185845, 212883, 213360, 213982, 220124, 220636, 221137, 221671, 222189, 222663, 223657, 226429
- Cause counts: `{"modeled_committed_prefix_collision": 12, "observed_bullet_overlap": 5, "observed_multiple_hazard_overlap": 1}`
- Phase markers: observed 10, reachable static opcode `0x94` 14.
- Bottom/side occupancy decisions: 2490/1953.

| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | Corridor slack | Cause | Factors |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 171575 | 3.00 | 75.00 | 0.00 | 354 | -2.85 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 175466 | 4.00 | 61.00 | 1.00 | 355 | -0.75 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 175830 | 3.00 | 45.00 | 0.00 | 571 | -2.46 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 176454 | 3.00 | 29.00 | 0.00 | 464 | -8.22 | - | `observed_bullet_overlap` | playfield_boundary |
| 176812 | 3.00 | 13.00 | 0.00 | 591 | 0.73 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 182136 | 3.00 | 4.00 | 0.00 | 1187 | -3.28 | - | `modeled_committed_prefix_collision` | playfield_boundary,pool_density_over_1000,fast_mode |
| 185845 | 3.00 | 1.00 | 0.00 | 120 | -2.32 | - | `observed_multiple_hazard_overlap` | playfield_boundary,fast_mode |
| 212883 | 3.00 | 1.00 | 0.00 | 284 | -1.58 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 213360 | 4.00 | 10.00 | 1.00 | 232 | -2.64 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 213982 | 3.00 | 8.00 | 0.00 | 482 | -3.46 | - | `modeled_committed_prefix_collision` | fast_mode |
| 220124 | 3.00 | 16.00 | 0.00 | 567 | -0.10 | - | `observed_bullet_overlap` | playfield_boundary |
| 220636 | 4.00 | 10.00 | 1.00 | 564 | -0.86 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 221137 | 3.00 | 2.00 | 0.00 | 578 | -2.24 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 221671 | 3.00 | 9.00 | 0.00 | 554 | -1.19 | - | `modeled_committed_prefix_collision` | playfield_boundary |
| 222189 | 4.00 | 9.00 | 1.00 | 561 | -1.67 | - | `observed_bullet_overlap` | playfield_boundary |
| 222663 | 3.00 | 1.00 | 0.00 | 565 | -4.06 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |
| 223657 | 3.00 | 1.00 | 0.00 | 572 | -2.57 | - | `observed_bullet_overlap` | playfield_boundary,fast_mode |
| 226429 | 4.00 | 18.00 | 0.00 | 906 | -3.72 | - | `modeled_committed_prefix_collision` | playfield_boundary,fast_mode |

## Spell Inventory And Runtime Coverage

Every spell below is statically reachable for route 2 Lunatic Final B. Observed decisions count only rows whose live spell state reported that active spell ID. Zero decisions therefore means the run did not enter that spell; zero hits with nonzero decisions means it entered cleanly. `unresolved` means the trace schema did not persist enough live spell state.

### Stage 1

- ECL: `ecldata1.ecl`
- Observed/expected phase-counter markers: 3/4.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 1 | 蛍符「地上の彗星」 | リグル・ナイトバグ | 3 | 6 | 0 | yes | 662 | 0 |
| 5 | 灯符「ファイヤフライフェノメノン」 | リグル・ナイトバグ | 11 | 6 | 0 | yes | 607 | 1 |
| 9 | 蠢符「ナイトバグトルネード」 | リグル・ナイトバグ | 13 | 27 | 0 | yes | 666 | 0 |
| 12 | 隠蟲「永夜蟄居」 | リグル・ナイトバグ | 12 | 27 | 0 | no | 0 | 0 |

### Stage 2

- ECL: `ecldata2.ecl`
- Observed/expected phase-counter markers: 2/3.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 16 | 声符「木菟咆哮」 | ミスティア・ローレライ | 4 | 7 | 0 | yes | 550 | 0 |
| 20 | 猛毒「毒蛾の暗闇演舞」 | ミスティア・ローレライ | 5 | 7 | 0 | yes | 711 | 0 |
| 24 | 鷹符「イルスタードダイブ」 | ミスティア・ローレライ | 6 | 8 | 0 | yes | 734 | 0 |
| 28 | 夜盲「夜雀の歌」 | ミスティア・ローレライ | 8 | 9 | 0 | yes | 831 | 0 |
| 31 | 夜雀「真夜中のコーラスマスター」 | ミスティア・ローレライ | 3 | 7 | 0 | no | 0 | 0 |

### Stage 3

- ECL: `ecldata3.ecl`
- Observed/expected phase-counter markers: 3/4.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 35 | 産霊「ファーストピラミッド」 | 上白沢慧音 | 3 | 0 | 0 | yes | 750 | 1 |
| 38 | 始符「エフェメラリティ137」 | 上白沢慧音 | 2 | 2 | 0 | yes | 648 | 0 |
| 42 | 野符「GHQクライシス」 | 上白沢慧音 | 3 | 3 | 0 | yes | 637 | 0 |
| 46 | 国体「三種の神器　郷」 | 上白沢慧音 | 3 | 0 | 0 | yes | 710 | 0 |
| 50 | 虚史「幻想郷伝説」 | 上白沢慧音 | 1 | 0 | 1 | yes | 559 | 0 |
| 53 | 未来「高天原」 | 上白沢慧音 | 1 | 0 | 1 | no | 0 | 0 |

### Stage 4A / Reimu

- ECL: `ecldata4a.ecl`
- Observed/expected phase-counter markers: 7/8.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 57 | 夢境「二重大結界」 | 博麗霊夢 | 3 | 0 | 0 | yes | 1034 | 3 |
| 61 | 散霊「夢想封印　寂」 | 博麗霊夢 | 3 | 0 | 0 | yes | 1033 | 0 |
| 65 | 神技「八方龍殺陣」 | 博麗霊夢 | 7 | 27 | 0 | yes | 777 | 2 |
| 69 | 回霊「夢想封印　侘」 | 博麗霊夢 | 2 | 17 | 0 | yes | 917 | 1 |
| 73 | 大結界「博麗弾幕結界」 | 博麗霊夢 | 5 | 4 | 0 | yes | 1007 | 3 |
| 76 | 神霊「夢想封印　瞬」 | 博麗霊夢 | 2 | 5 | 0 | no | 0 | 0 |

### Stage 5

- ECL: `ecldata5.ecl`
- Observed/expected phase-counter markers: 7/8.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 103 | 幻波「赤眼催眠(マインドブローイング)」 | 鈴仙・Ｕ・イナバ | 6 | 0 | 0 | yes | 817 | 2 |
| 111 | 懶惰「生神停止(マインドストッパー)」 | 鈴仙・Ｕ・イナバ | 3 | 0 | 0 | yes | 822 | 1 |
| 107 | 狂視「狂視調律(イリュージョンシーカー)」 | 鈴仙・Ｕ・イナバ | 3 | 3 | 0 | yes | 710 | 2 |
| 115 | 散符「真実の月(インビジブルフルムーン)」 | 鈴仙・Ｕ・イナバ | 6 | 3 | 0 | yes | 890 | 2 |
| 118 | 月眼「月兎遠隔催眠術(テレメスメリズム)」 | 鈴仙・Ｕ・イナバ | 4 | 2 | 0 | no | 0 | 0 |

### Final B / Kaguya

- ECL: `ecldata7.ecl`
- Observed/expected phase-counter markers: 10/14.

| ID | Name | Owner | Emits | Transforms | Lasers | Observed | Decisions | Hits |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| 150 | 薬符「壺中の大銀河」 | 八意永琳 | 4 | 0 | 0 | yes | 768 | 4 |
| 154 | 神宝「ブリリアントドラゴンバレッタ」 | 蓬莱山輝夜 | 5 | 1 | 5 | yes | 767 | 1 |
| 158 | 神宝「ブディストダイアモンド」 | 蓬莱山輝夜 | 4 | 4 | 2 | yes | 1357 | 0 |
| 162 | 神宝「サラマンダーシールド」 | 蓬莱山輝夜 | 4 | 8 | 2 | yes | 1490 | 0 |
| 166 | 神宝「ライフスプリングインフィニティ」 | 蓬莱山輝夜 | 3 | 2 | 2 | yes | 1392 | 3 |
| 170 | 神宝「蓬莱の玉の枝  -夢色の郷-」 | 蓬莱山輝夜 | 26 | 3 | 0 | yes | 1774 | 7 |
| 174 | 「永夜返し  -待宵-」 | 蓬莱山輝夜 | 3 | 1 | 0 | yes | 229 | 1 |
| 178 | 「永夜返し  -子の四つ-」 | 蓬莱山輝夜 | 3 | 2 | 0 | no | 0 | 0 |
| 182 | 「永夜返し  -丑の四つ-」 | 蓬莱山輝夜 | 2 | 2 | 0 | no | 0 | 0 |
| 186 | 「永夜返し  -寅の四つ-」 | 蓬莱山輝夜 | 4 | 4 | 0 | no | 0 | 0 |
| 190 | 「永夜返し  -世明け-」 | 蓬莱山輝夜 | 12 | 5 | 0 | no | 0 | 0 |

## Runtime And Harness Findings

- Observed auto-Z stall frames: none.
- Route termination: `route_complete` at completion probe frame 226632.
- Unique robust solutions observed: 0; solve time median/p95/max -/-/- ms.
- First-observed policy age median/p95/max: -/-/- frames.
- Viability queries available: 0/0; robustly constrained decisions: 0/56539.
- Robust-policy decisions without any usable query: 0/0.
- Global-horizon/local-prefix cross-tab: 0 decisions; winning global state with unsafe selected prefix: 0; losing global state with safe short prefix: 0; selected globally certified action contradicted by the fresh local prefix checker: 0; selected action outside the reported winning set: 0.
- Live spell attribution was recorded at every hit edge; exact per-spell counts are preserved below.
- `0` hit edges remain in the `sensor_gap_or_unmodeled_hazard` class and require executor-level same-frame emission/transform evidence.

## Next Regression Work

1. Keep robust backward-reachability solves within the finite policy horizon, then verify nonzero live query and constrained-decision counts.
2. Replay all 57 retained witnesses through the integrated executor and preserve one regression per concrete failure.
3. Re-run focused Stage 4A and Final B practices before another full Lunatic route; compare hit frames, policy age, action-set exhaustion, and cluster recurrence.
4. Add item/Power state and finite Bomb resources only after the no-Bomb movement policy has passed physical validation.
