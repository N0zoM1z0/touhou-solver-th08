# TH08 Final B / Kaguya No-Bomb Practice Review: easy_route2_stage6b_unattended_20260826_043723

## Scope And Integrity

- Valid practice scope: `2..75551` (11163 decisions).
- Selected frame epoch: 0 of 1; 0 earlier decisions were excluded.
- Scope terminator: `raw_trace_end`; 0 reset-tail decisions were excluded.
- The agent's raw summary agrees with the scoped trace.
- Accepted complete practice: **YES**.
- Native hit edges: 18, at `[10843, 11169, 11477, 11805, 12138, 21298, 21640, 22211, 22970, 23345, 23746, 24120, 24503, 27478, 32219, 51260, 52017, 58999]`.
- Hard no-Bomb verification: **PASS** across 11163 decisions; mask/flag/action violations are all empty.

Bomb-stock changes in the trace are death/respawn state changes. They are not Bomb use: every scoped input mask has bit `0x02` clear, every decision has `bomb=false`, and no action requests Bomb.

## Primary Finding

The authoritative fresh-attempt hit is `EASY-S7-F10843-T1`. It occurred during spell 147 `薬符「壺中の大銀河」` at player (376.000, 420.518), with 625 bullets and 0 lasers. The projectile model reported pipeline clearance -11.144.

The primary class is `modeled_committed_prefix_collision`. This trace contains the retained hit-window geometry for that classification; later post-respawn hits remain discovery evidence rather than fresh independent trials.

## Failure Taxonomy

| Cause | Hits |
| --- | ---: |
| `modeled_committed_prefix_collision` | 8 |
| `observed_laser_overlap` | 5 |
| `observed_bullet_overlap` | 3 |
| `active_laser_without_observed_overlap` | 2 |

Contributing factors:

- `playfield_boundary`: 15
- `action_lag_over_model`: 13
- `corridor_deadline_miss`: 12
- `fast_mode`: 9

## Death Ledger

| Role | Frame | Spell | Player | Active input | Bullets/lasers | Pipeline/min 240f | Pipeline/robust warning | Contact/cause | Planner failure |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| canonical | 10843 | 147 薬符「壺中の大銀河」 | (376.000, 420.518) | `stay` | 625/0 | -11.144/-11.144 | 0f/7f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 11169 | 147 薬符「壺中の大銀河」 | (376.000, 411.847) | `up_right` | 598/0 | -0.477/-0.477 | 0f/0f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 11477 | 147 薬符「壺中の大銀河」 | (8.000, 410.304) | `down_left_fast` | 611/0 | -2.291/-2.291 | 0f/0f | `observed_bullet_overlap` | `missing_pre_hit_alive_decision` |
| discovery | 11805 | 147 薬符「壺中の大銀河」 | (8.000, 423.314) | `down_left_fast` | 553/0 | 6.892/2.039 | 0f/0f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 12138 | 147 薬符「壺中の大銀河」 | (8.000, 359.933) | `up_fast` | 559/0 | -1.836/-1.836 | 0f/0f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 21298 | 151 難題「龍の頸の玉  -五色の弾丸-」 | (8.000, 430.374) | `up_left` | 21/135 | -2.884/-2.884 | 7f/11f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 21640 | 151 難題「龍の頸の玉  -五色の弾丸-」 | (30.627, 432.000) | `down_right_fast` | 17/205 | -4.436/-4.436 | 0f/0f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 22211 | 151 難題「龍の頸の玉  -五色の弾丸-」 | (366.242, 432.000) | `stay` | 22/225 | 2.365/-1.451 | 0f/0f | `active_laser_without_observed_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 22970 | 151 難題「龍の頸の玉  -五色の弾丸-」 | (376.000, 432.000) | `up_left_fast` | 22/225 | -2.274/-3.520 | 23f/23f | `observed_laser_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 23345 | 151 難題「龍の頸の玉  -五色の弾丸-」 | (37.274, 432.000) | `down_right` | 22/205 | -4.984/-4.984 | 0f/0f | `observed_laser_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 23746 | 151 難題「龍の頸の玉  -五色の弾丸-」 | (353.231, 432.000) | `down_left` | 23/210 | -5.137/-5.137 | 0f/0f | `observed_laser_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 24120 | 151 難題「龍の頸の玉  -五色の弾丸-」 | (8.000, 395.200) | `up` | 20/200 | -5.175/-5.175 | 0f/0f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 24503 | 151 難題「龍の頸の玉  -五色の弾丸-」 | (376.000, 429.172) | `up_right_fast` | 17/210 | 5.922/5.922 | 0f/0f | `active_laser_without_observed_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 27478 | nonspell | (20.297, 420.686) | `up_right_fast` | 196/0 | -0.077/-0.077 | 0f/0f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 32219 | 155 難題「仏の御石の鉢  -砕けぬ意思-」 | (367.475, 432.000) | `left_fast` | 84/20 | -3.848/-3.848 | 0f/5f | `observed_laser_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 51260 | 163 難題「燕の子安貝  -永命線-」 | (146.959, 412.514) | `down` | 201/52 | -1.549/-1.549 | 0f/0f | `observed_laser_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 52017 | 163 難題「燕の子安貝  -永命線-」 | (297.624, 415.737) | `up_right` | 198/52 | -4.171/-4.171 | 0f/0f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 58999 | 167 難題「蓬莱の弾の枝  -虹色の弾幕-」 | (350.544, 432.000) | `down_left_fast` | 245/0 | -3.041/-3.041 | 0f/0f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |

## Per-Phase Planner Health

| Phase | Hits | Decisions | Queries | Empty | Support outside | Constrained | Solves | Solve median ms | Bottom alive |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nonspell | 1 | 4952 | 4765 | 1998 | 0 | 0 | 743 | 367.757 | 0.053 |
| 147 薬符「壺中の大銀河」 | 5 | 498 | 474 | 234 | 0 | 0 | 80 | 484.244 | 0.074 |
| 151 難題「龍の頸の玉  -五色の弾丸-」 | 8 | 548 | 535 | 276 | 0 | 0 | 99 | 529.030 | 0.282 |
| 155 難題「仏の御石の鉢  -砕けぬ意思-」 | 1 | 961 | 943 | 575 | 0 | 0 | 243 | 152.432 | 0.158 |
| 159 | 0 | 863 | 853 | 533 | 0 | 0 | 119 | 249.994 | 0.232 |
| 163 難題「燕の子安貝  -永命線-」 | 2 | 762 | 747 | 437 | 0 | 0 | 151 | 321.735 | 0.140 |
| 167 難題「蓬莱の弾の枝  -虹色の弾幕-」 | 1 | 1170 | 1163 | 485 | 0 | 0 | 263 | 180.340 | 0.091 |
| 171 | 0 | 171 | 155 | 82 | 0 | 0 | 24 | 193.767 | 0.103 |
| 175 | 0 | 246 | 233 | 167 | 0 | 0 | 52 | 149.744 | 0.386 |
| 179 | 0 | 307 | 295 | 240 | 0 | 0 | 61 | 85.403 | 0.055 |
| 183 | 0 | 178 | 166 | 112 | 0 | 0 | 28 | 448.653 | 0.145 |
| 187 | 0 | 507 | 454 | 340 | 0 | 0 | 64 | 144.705 | 0.068 |

## Interpretation

- Retained witnesses classify 3 bullet overlaps, 5 laser overlaps, and 0 exact same-epoch enemy-body overlaps; 0 of those enemy slots were absent from the action snapshot.
- The controller decision cadence was 4.000 frames median and 7.000 frames p95. The local plan took 32.700 ms median and 59.542 ms p95.
- The full enemy sensor produced 5630 snapshots; capture read time was `{'median': 117.80780000117375, 'p95': 190.76050000148825, 'max': 373.5046000001603}`, snapshot age was `{'median': 8.0, 'p95': 14.0, 'max': 33.0}` frames, and 20 phase-counter discontinuities were excluded; 10542 decisions retained at least one robust-union body (maximum 31); 8320 decisions contained latent contact-disabled geometry (maximum 31), and 1051 contained bounded inactive-slot memory (maximum 16). 155 body samples retained observed world-motion estimates; world/internal speed and disagreement were `{'median': 1.9291839599609375, 'p95': 9.035268147786459, 'max': 9.167185465494791}` / `{'median': 1.5132293701171875, 'p95': 8.968002319335938, 'max': 9.292816162109375}` / `{'median': 0.14218076070149743, 'p95': 2.66324462890625, 'max': 3.0857482910156246}`.
- The issue-time enemy guard retained 11163 observations, detected 1206 during-plan geometry changes, recertified 1206 decisions, and overrode 13 actions. Read/recertificate timing was `{'median': 2.645499997015577, 'p95': 10.357200000726152, 'max': 59.1398999968078}` / `{'median': 9.02565000069444, 'p95': 25.682499996037222, 'max': 63.21890000253916}` ms; 6803 issue captures contained latent bodies (maximum 31), and 1042 contained dormant bodies (maximum 16). Fresh/global transactions preserved 1193/1206 planned actions, relaxed 0 fresh/global empty intersections, inherited 0 earlier planner relaxations, and recorded 0 silent outside-global selections.
- The synchronous spell-owner guard retained 9877 observations (8353 contact enabled, 1524 anticipatory, 0 errors). 8967 observed owners were outside the ordinary 480-slot async scan; pointer counts were `{'0x0057D2F0': 8967, '0x005826C0': 910}`.
- The terminal-threat heuristic covered 11163 decisions with horizon counts `{'0': 473, '10': 10690}`; it reported 0 collision and 0 sub-safety-clearance warnings, and relaxed 0 coarse constraints at clamped aliases.
- Modeled action hold counts were `{'2': 136, '3': 111, '4': 409, '5': 3391, '6': 7116}` overall.
- Modeled uncontrollable-prefix counts were `{'2': 169, '3': 84, '4': 1400, '5': 6264, '6': 3246}`.
- Adaptive delay supports were `{'2,3': 84, '2,3,4': 44, '2,3,4,5': 26, '2,3,4,5,6': 720, '3,4': 22, '3,4,5': 66, '3,4,5,6': 5026, '4,5': 1, '4,5,6': 5042, '5,6': 130, '6': 2}`; 46 decisions changed their nominal first action, 120 end-to-end transition samples were retained, and the maximum observed overrun/censored counters were 159/121.
- Robust viability supplied 10783 available policy queries (0 had new delay support outside the cached policy), constrained 0 decisions, and exposed 5479 empty queried action sets. Recovery guidance was available/selected on 1289/0 empty-kernel queries; distant-kernel guidance was available/selected on 3401/0. Safe-action count, selected repair-volume, selected recovery-distance, and selected control-reserve deficit statistics were `{'median': 0.0, 'p95': 17.0, 'max': 17.0}`, `{'median': 0.0, 'p95': 0.0, 'max': 0.0}`, `None`, and `None`.
- Queried policy phase offsets within the coarse control layer were `{'0': 1550, '1': 1552, '2': 1411, '3': 1326, '4': 1250, '5': 1198, '6': 1257, '7': 1239}`.
- Global-horizon/local-prefix cross-tab covered 8735 decisions: 0 had a winning global state but unsafe selected prefix, 4410 had a losing global state but safe short prefix, 0 selected globally certified actions contradicted the fresh local prefix checker, and 430 selected actions were outside the reported winning set. 802 newer issue-time hazard versions and 27 deadline-held old inputs were excluded from the aligned comparison.
- The rolling worker produced 1927 unique policies with solve-time statistics `{'median': 276.6988000003039, 'p95': 598.5275999992155, 'max': 901.0699999998906}` and first-observed ages `{'median': 6.0, 'p95': 17.0, 'max': 1810.0}`. Policy status counts were `{'pending_future_epoch': 98, 'queryable': 10795, 'expired': 77}`; 187 robust-mode decisions had no query.
- Of 5950 unambiguous output transitions, 5935 (0.997) were already visible in the next decision snapshot; their snapshot delta had median 1.000 frame.
- Separating physical contact from planner causality gives `{'global_viability_kernel_exhausted_before_hit': 17, 'missing_pre_hit_alive_decision': 1}`. Active input is the game-observed input at collision; the newly issued action on a hit row occurs after hit detection.
- Robust action-set exhaustion supplied 4 hit windows with a positive warning lead; those leads were `[7, 0, 0, 0, 0, 11, 0, 0, 23, 0, 0, 0, 0, 0, 5, 0, 0, 0]` frames.
- Across all phases, bottom-eight-pixel occupancy was 0.432 during the 60 frames preceding a hit versus 0.099 outside those windows.
- Mean selected control-reserve deficit was 0.000 during the 60 frames preceding a hit versus 0.000 outside those windows.
- Soft recovery was selected on 0.000 of alive decisions in the 60-frame pre-hit windows versus 0.000 outside; correlation alone is not a causal acceptance result.
- Later hits cannot estimate an initial-stock clear rate because Power falls from 128 to 5.000 after respawns. They remain valid counterexamples for geometry, latency, boundary use, and spell-specific pressure.

## Next Correction Gate

Treat policy delivery, delay-support coverage, and viability exhaustion as separate gates. The next focused run must keep rolling-policy queries available, reduce unsupported query epochs, and preserve a non-empty action kernel before each former hit window. Compare per-phase position and warning lead, not only aggregate hit count.
