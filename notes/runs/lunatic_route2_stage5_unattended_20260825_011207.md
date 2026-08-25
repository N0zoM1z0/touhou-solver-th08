# TH08 Stage 5 No-Bomb Practice Review: lunatic_route2_stage5_unattended_20260825_011207

## Scope And Integrity

- Valid practice scope: `3..43173` (7475 decisions).
- Selected frame epoch: 0 of 1; 0 earlier decisions were excluded.
- Scope terminator: `raw_trace_end`; 0 reset-tail decisions were excluded.
- The agent's raw summary agrees with the scoped trace.
- Accepted complete practice: **YES**.
- Native hit edges: 22, at `[2010, 4208, 14423, 23014, 24029, 28720, 29070, 29511, 29810, 30171, 30585, 31008, 31308, 36128, 37391, 38135, 38881, 39635, 40892, 41529, 42187, 43060]`.
- Hard no-Bomb verification: **PASS** across 7475 decisions; mask/flag/action violations are all empty.

Bomb-stock changes in the trace are death/respawn state changes. They are not Bomb use: every scoped input mask has bit `0x02` clear, every decision has `bomb=false`, and no action requests Bomb.

## Primary Finding

The authoritative fresh-attempt hit is `LUN-S5-F2010-T1`. It occurred during a nonspell phase at player (356.201, 432.000), with 757 bullets and 0 lasers. The projectile model reported pipeline clearance -0.710.

The primary class is `modeled_committed_prefix_collision`. This trace contains the retained hit-window geometry for that classification; later post-respawn hits remain discovery evidence rather than fresh independent trials.

## Failure Taxonomy

| Cause | Hits |
| --- | ---: |
| `modeled_committed_prefix_collision` | 10 |
| `observed_bullet_overlap` | 10 |
| `sensor_gap_or_unmodeled_hazard` | 2 |

Contributing factors:

- `action_lag_over_model`: 13
- `playfield_boundary`: 9
- `pool_density_over_1000`: 9
- `corridor_deadline_miss`: 8
- `fast_mode`: 8

## Death Ledger

| Role | Frame | Spell | Player | Active input | Bullets/lasers | Pipeline/min 240f | Pipeline/robust warning | Contact/cause | Planner failure |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| canonical | 2010 | nonspell | (356.201, 432.000) | `down_right` | 757/0 | -0.710/-0.710 | 0f/0f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 4208 | nonspell | (376.000, 432.000) | `up` | 531/0 | -2.800/-2.800 | 0f/7f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 14423 | nonspell | (8.000, 432.000) | `down_right_fast` | 450/0 | -1.629/-1.629 | 0f/11f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 23014 | 103 幻波「赤眼催眠(マインドブローイング)」 | (301.482, 432.000) | `up_fast` | 1133/0 | -0.569/-0.569 | 0f/0f | `modeled_committed_prefix_collision` | `late_collision_after_positive_causal_margin` |
| discovery | 24029 | 103 幻波「赤眼催眠(マインドブローイング)」 | (175.462, 390.634) | `down_right_fast` | 1013/0 | 2.896/0.656 | 0f/0f | `observed_bullet_overlap` | `late_collision_after_positive_causal_margin` |
| discovery | 28720 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (139.812, 416.000) | `left` | 878/0 | -7.513/-7.513 | 25f/25f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 29070 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (177.140, 432.000) | `down_left` | 997/0 | -5.018/-7.659 | 0f/11f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 29511 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (154.546, 432.000) | `down_right_fast` | 1000/0 | -2.662/-7.046 | 10f/10f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 29810 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (198.939, 401.099) | `stay` | 1008/0 | -7.855/-7.855 | 0f/0f | `modeled_committed_prefix_collision` | `missing_pre_hit_alive_decision` |
| discovery | 30171 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (192.000, 384.000) | `stay` | 997/0 | -0.631/-6.135 | 12f/27f | `modeled_committed_prefix_collision` | `robust_action_set_exhausted_before_hit` |
| discovery | 30585 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (98.981, 118.981) | `up_left` | 993/0 | -5.364/-7.262 | 0f/13f | `observed_bullet_overlap` | `robust_action_set_exhausted_before_hit` |
| discovery | 31008 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (184.010, 412.000) | `stay` | 1004/0 | -4.983/-7.321 | 0f/12f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 31308 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (192.000, 384.000) | `stay` | 1000/0 | -2.476/-7.192 | 0f/0f | `modeled_committed_prefix_collision` | `missing_pre_hit_alive_decision` |
| discovery | 36128 | nonspell | (8.000, 432.000) | `right_fast` | 423/0 | -0.504/-0.504 | 0f/5f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 37391 | 111 懶惰「生神停止(マインドストッパー)」 | (8.000, 400.854) | `left_fast` | 978/0 | 0.765/-2.122 | 0f/0f | `sensor_gap_or_unmodeled_hazard` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 38135 | 111 懶惰「生神停止(マインドストッパー)」 | (56.146, 349.776) | `up_right` | 991/0 | -2.497/-2.497 | 0f/0f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 38881 | 111 懶惰「生神停止(マインドストッパー)」 | (41.819, 405.550) | `down_fast` | 1059/0 | -1.018/-1.018 | 0f/0f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 39635 | 111 懶惰「生神停止(マインドストッパー)」 | (361.866, 404.295) | `stay` | 1056/0 | 0.491/-11.140 | 0f/0f | `sensor_gap_or_unmodeled_hazard` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 40892 | 115 散符「真実の月(インビジブルフルムーン)」 | (136.800, 429.172) | `up_left_fast` | 1086/0 | 1.609/-0.844 | 5f/10f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 41529 | 115 散符「真実の月(インビジブルフルムーン)」 | (188.214, 407.342) | `stay` | 956/0 | 1.107/1.107 | 0f/0f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 42187 | 115 散符「真実の月(インビジブルフルムーン)」 | (261.251, 391.484) | `down_right` | 955/0 | 30.390/9.045 | 0f/0f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 43060 | 115 散符「真実の月(インビジブルフルムーン)」 | (269.547, 409.056) | `stay` | 956/0 | -1.791/-1.791 | 0f/0f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |

## Per-Phase Planner Health

| Phase | Hits | Decisions | Queries | Empty | Support outside | Constrained | Solves | Solve median ms | Bottom alive |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nonspell | 4 | 5058 | 4592 | 3144 | 0 | 0 | 942 | 127.657 | 0.306 |
| 103 幻波「赤眼催眠(マインドブローイング)」 | 2 | 387 | 283 | 73 | 0 | 0 | 27 | 310.699 | 0.160 |
| 107 狂視「狂視調律(イリュージョンシーカー)」 | 8 | 525 | 369 | 176 | 0 | 0 | 44 | 378.572 | 0.059 |
| 111 懶惰「生神停止(マインドストッパー)」 | 4 | 744 | 593 | 290 | 0 | 0 | 58 | 235.717 | 0.000 |
| 115 散符「真実の月(インビジブルフルムーン)」 | 4 | 761 | 735 | 535 | 0 | 0 | 165 | 77.670 | 0.229 |

## Interpretation

- Retained witnesses classify 10 bullet overlaps, 0 laser overlaps, and 0 exact same-epoch enemy-body overlaps; 0 of those enemy slots were absent from the action snapshot.
- The controller decision cadence was 4.000 frames median and 6.000 frames p95. The local plan took 39.754 ms median and 76.006 ms p95.
- The full enemy sensor produced 6081 snapshots; capture read time was `{'median': 39.039299939759076, 'p95': 74.92599997203797, 'max': 236.52329994365573}`, snapshot age was `{'median': 6.0, 'p95': 9.0, 'max': 28.0}` frames, and 6 phase-counter discontinuities were excluded; 7005 decisions retained at least one robust-union body (maximum 42); 5407 decisions contained latent contact-disabled geometry (maximum 42), and 2518 contained bounded inactive-slot memory (maximum 36). 570 body samples retained observed world-motion estimates; world/internal speed and disagreement were `{'median': 0.0, 'p95': 3.734710693359375, 'max': 6.9842987060546875}` / `{'median': 0.0, 'p95': 3.7381935119628906, 'max': 4.710216522216797}` / `{'median': 0.0, 'p95': 1.0, 'max': 5.259615071614584}`.
- The issue-time enemy guard retained 7475 observations, detected 2841 during-plan geometry changes, recertified 2841 decisions, and overrode 16 actions. Read/recertificate timing was `{'median': 1.4949999749660492, 'p95': 2.709199907258153, 'max': 24.258699966594577}` / `{'median': 4.147199913859367, 'p95': 15.683499979786575, 'max': 96.46870009601116}` ms; 5385 issue captures contained latent bodies (maximum 42), and 2521 contained dormant bodies (maximum 37). Fresh/global transactions preserved 2825/2841 planned actions, relaxed 0 fresh/global empty intersections, inherited 0 earlier planner relaxations, and recorded 0 silent outside-global selections.
- The synchronous spell-owner guard retained 5250 observations (5225 contact enabled, 25 anticipatory, 0 errors). 5250 observed owners were outside the ordinary 480-slot async scan; pointer counts were `{'0x0057D2F0': 5250}`.
- The terminal-threat heuristic covered 7475 decisions with horizon counts `{'0': 396, '10': 7079}`; it reported 0 collision and 0 sub-safety-clearance warnings, and relaxed 0 coarse constraints at clamped aliases.
- Modeled action hold counts were `{'2': 270, '3': 271, '4': 1734, '5': 2695, '6': 2505}` overall.
- Modeled uncontrollable-prefix counts were `{'2': 224, '3': 294, '4': 2645, '5': 3151, '6': 1161}`.
- Adaptive delay supports were `{'1,2,3': 72, '1,2,3,4,5': 81, '1,2,3,4,5,6': 187, '2,3': 5, '2,3,4': 51, '2,3,4,5': 70, '2,3,4,5,6': 1609, '3,4': 115, '3,4,5': 162, '3,4,5,6': 3597, '4,5': 144, '4,5,6': 1365, '5,6': 17}`; 86 decisions changed their nominal first action, 120 end-to-end transition samples were retained, and the maximum observed overrun/censored counters were 88/160.
- Robust viability supplied 6572 available policy queries (0 had new delay support outside the cached policy), constrained 0 decisions, and exposed 4218 empty queried action sets. Recovery guidance was available/selected on 300/0 empty-kernel queries; distant-kernel guidance was available/selected on 2867/0. Safe-action count, selected repair-volume, selected recovery-distance, and selected control-reserve deficit statistics were `{'median': 0.0, 'p95': 17.0, 'max': 17.0}`, `{'median': 0.0, 'p95': 0.0, 'max': 0.0}`, `None`, and `None`.
- Queried policy phase offsets within the coarse control layer were `{'0': 1109, '1': 956, '2': 789, '3': 641, '4': 878, '5': 757, '6': 787, '7': 655}`.
- Global-horizon/local-prefix cross-tab covered 3251 decisions: 0 had a winning global state but unsafe selected prefix, 1997 had a losing global state but safe short prefix, 0 selected globally certified actions contradicted the fresh local prefix checker, and 37 selected actions were outside the reported winning set. 1973 newer issue-time hazard versions and 11 deadline-held old inputs were excluded from the aligned comparison.
- The rolling worker produced 1236 unique policies with solve-time statistics `{'median': 124.81134996050969, 'p95': 327.73560006171465, 'max': 2851.843300042674}` and first-observed ages `{'median': 5.0, 'p95': 10.0, 'max': 1788.0}`. Policy status counts were `{'pending_future_epoch': 218, 'queryable': 6524, 'expired': 683}`; 853 robust-mode decisions had no query.
- Of 3558 unambiguous output transitions, 3499 (0.983) were already visible in the next decision snapshot; their snapshot delta had median 1.000 frame.
- Separating physical contact from planner causality gives `{'global_viability_kernel_exhausted_before_hit': 16, 'late_collision_after_positive_causal_margin': 2, 'missing_pre_hit_alive_decision': 2, 'robust_action_set_exhausted_before_hit': 2}`. Active input is the game-observed input at collision; the newly issued action on a hit row occurs after hit detection.
- Robust action-set exhaustion supplied 10 hit windows with a positive warning lead; those leads were `[0, 7, 11, 0, 0, 25, 11, 10, 0, 27, 13, 12, 0, 5, 0, 0, 0, 0, 10, 0, 0, 0]` frames.
- Across all phases, bottom-eight-pixel occupancy was 0.285 during the 60 frames preceding a hit versus 0.262 outside those windows.
- Mean selected control-reserve deficit was 0.000 during the 60 frames preceding a hit versus 0.000 outside those windows.
- Soft recovery was selected on 0.000 of alive decisions in the 60-frame pre-hit windows versus 0.000 outside; correlation alone is not a causal acceptance result.
- Later hits cannot estimate an initial-stock clear rate because Power falls from 128 to 0.000 after respawns. They remain valid counterexamples for geometry, latency, boundary use, and spell-specific pressure.

## Next Correction Gate

Treat policy delivery, delay-support coverage, and viability exhaustion as separate gates. The next focused run must keep rolling-policy queries available, reduce unsupported query epochs, and preserve a non-empty action kernel before each former hit window. Compare per-phase position and warning lead, not only aggregate hit count.
