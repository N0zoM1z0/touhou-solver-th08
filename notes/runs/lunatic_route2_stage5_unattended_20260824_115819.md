# TH08 Stage 5 No-Bomb Practice Review: lunatic_route2_stage5_unattended_20260824_115819

## Scope And Integrity

- Valid practice scope: `2..45254` (7792 decisions).
- Selected frame epoch: 0 of 1; 0 earlier decisions were excluded.
- Scope terminator: `raw_trace_end`; 0 reset-tail decisions were excluded.
- The agent's raw summary agrees with the scoped trace.
- Accepted complete practice: **YES**.
- Native hit edges: 28, at `[4163, 10831, 12423, 14117, 23150, 24438, 27523, 29244, 29648, 30086, 30505, 30805, 31164, 31470, 31860, 32244, 32551, 32911, 33214, 36891, 37589, 38365, 39793, 40538, 41644, 42795, 43868, 44602]`.
- Hard no-Bomb verification: **PASS** across 7792 decisions; mask/flag/action violations are all empty.

Bomb-stock changes in the trace are death/respawn state changes. They are not Bomb use: every scoped input mask has bit `0x02` clear, every decision has `bomb=false`, and no action requests Bomb.

## Primary Finding

The authoritative fresh-attempt hit is `LUN-S5-F4163-T1`. It occurred during a nonspell phase at player (361.858, 432.000), with 475 bullets and 0 lasers. The projectile model reported pipeline clearance 8.365.

The primary class is `observed_bullet_overlap`. This trace contains the retained hit-window geometry for that classification; later post-respawn hits remain discovery evidence rather than fresh independent trials.

## Failure Taxonomy

| Cause | Hits |
| --- | ---: |
| `modeled_committed_prefix_collision` | 16 |
| `observed_bullet_overlap` | 11 |
| `sensor_gap_or_unmodeled_hazard` | 1 |

Contributing factors:

- `playfield_boundary`: 18
- `action_lag_over_model`: 17
- `pool_density_over_1000`: 13
- `fast_mode`: 8
- `corridor_deadline_miss`: 3

## Death Ledger

| Role | Frame | Spell | Player | Active input | Bullets/lasers | Pipeline/min 240f | Pipeline/robust warning | Contact/cause | Planner failure |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| canonical | 4163 | nonspell | (361.858, 432.000) | `left_fast` | 475/0 | 8.365/0.653 | 0f/10f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 10831 | nonspell | (376.000, 399.900) | `right` | 905/0 | -0.782/-0.782 | 0f/6f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 12423 | nonspell | (376.000, 432.000) | `stay` | 327/0 | -0.048/-0.048 | 0f/9f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 14117 | nonspell | (376.000, 422.800) | `up_fast` | 330/0 | -5.074/-5.074 | 0f/9f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 23150 | 103 幻波「赤眼催眠(マインドブローイング)」 | (376.000, 432.000) | `up_fast` | 879/0 | -1.461/-1.461 | 0f/5f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 24438 | 103 幻波「赤眼催眠(マインドブローイング)」 | (8.000, 432.000) | `down_right` | 1074/0 | -0.871/-0.871 | 0f/6f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 27523 | nonspell | (165.267, 432.000) | `up_right` | 1038/0 | -0.239/-0.239 | 0f/12f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 29244 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (100.018, 432.000) | `down_left` | 738/0 | -1.120/-1.120 | 0f/10f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 29648 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (340.101, 55.164) | `stay` | 989/0 | -7.704/-10.299 | 12f/34f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 30086 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (99.298, 312.702) | `down_fast` | 1007/0 | -5.661/-25.701 | 127f/127f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 30505 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (8.000, 123.701) | `left` | 1002/0 | -6.695/-7.141 | 22f/22f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 30805 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (8.000, 16.000) | `up_left` | 998/0 | -7.139/-8.203 | 0f/0f | `modeled_committed_prefix_collision` | `missing_pre_hit_alive_decision` |
| discovery | 31164 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (8.000, 357.188) | `up_left` | 1005/0 | -8.018/-8.041 | 56f/56f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 31470 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (192.000, 384.000) | `stay` | 1010/0 | -6.315/-8.139 | 0f/0f | `modeled_committed_prefix_collision` | `missing_pre_hit_alive_decision` |
| discovery | 31860 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (192.000, 384.000) | `stay` | 1015/0 | -3.523/-6.075 | 71f/82f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 32244 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (325.583, 92.275) | `stay` | 1013/0 | -2.468/-7.567 | 26f/78f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 32551 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (192.000, 384.000) | `stay` | 1019/0 | -7.533/-9.468 | 0f/0f | `modeled_committed_prefix_collision` | `missing_pre_hit_alive_decision` |
| discovery | 32911 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (190.656, 375.078) | `up_left` | 1001/0 | -6.722/-6.739 | 28f/39f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 33214 | 107 狂視「狂視調律(イリュージョンシーカー)」 | (8.000, 16.000) | `up_left` | 1014/0 | -6.101/-9.064 | 0f/0f | `observed_bullet_overlap` | `missing_pre_hit_alive_decision` |
| discovery | 36891 | nonspell | (64.230, 432.000) | `left` | 468/0 | -2.860/-2.860 | 0f/0f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 37589 | nonspell | (369.495, 432.000) | `left_fast` | 476/0 | -2.274/-2.274 | 4f/12f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 38365 | nonspell | (8.000, 432.000) | `right_fast` | 414/0 | -1.768/-1.768 | 4f/9f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 39793 | 111 懶惰「生神停止(マインドストッパー)」 | (178.912, 219.317) | `up_left_fast` | 375/0 | -2.254/-2.254 | 11f/18f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 40538 | 111 懶惰「生神停止(マインドストッパー)」 | (221.854, 184.875) | `right` | 341/0 | -1.820/-1.820 | 0f/0f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 41644 | 111 懶惰「生神停止(マインドストッパー)」 | (221.363, 207.014) | `up_right` | 357/0 | -2.260/-2.260 | 0f/0f | `modeled_committed_prefix_collision` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 42795 | 115 散符「真実の月(インビジブルフルムーン)」 | (115.487, 432.000) | `down_left_fast` | 1076/0 | -7.679/-7.679 | 0f/12f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 43868 | 115 散符「真実の月(インビジブルフルムーン)」 | (241.769, 432.000) | `down_right` | 884/0 | 0.872/-0.220 | 0f/0f | `sensor_gap_or_unmodeled_hazard` | `global_viability_kernel_exhausted_before_hit` |
| discovery | 44602 | 115 散符「真実の月(インビジブルフルムーン)」 | (278.537, 432.000) | `down_left` | 1137/0 | 0.533/-1.119 | 4f/14f | `observed_bullet_overlap` | `global_viability_kernel_exhausted_before_hit` |

## Per-Phase Planner Health

| Phase | Hits | Decisions | Queries | Empty | Support outside | Constrained | Solves | Solve median ms | Bottom alive |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nonspell | 8 | 5074 | 4964 | 3717 | 0 | 0 | 1057 | 146.265 | 0.273 |
| 103 幻波「赤眼催眠(マインドブローイング)」 | 2 | 647 | 637 | 306 | 0 | 0 | 145 | 275.328 | 0.380 |
| 107 狂視「狂視調律(イリュージョンシーカー)」 | 12 | 623 | 611 | 455 | 0 | 0 | 242 | 218.463 | 0.143 |
| 111 懶惰「生神停止(マインドストッパー)」 | 3 | 716 | 707 | 253 | 0 | 0 | 167 | 157.387 | 0.000 |
| 115 散符「真実の月(インビジブルフルムーン)」 | 3 | 732 | 724 | 521 | 0 | 0 | 176 | 101.948 | 0.342 |

## Interpretation

- Retained witnesses classify 11 bullet overlaps, 0 laser overlaps, and 0 exact same-epoch enemy-body overlaps; 0 of those enemy slots were absent from the action snapshot.
- The controller decision cadence was 4.000 frames median and 8.000 frames p95. The local plan took 39.657 ms median and 103.971 ms p95.
- The full enemy sensor produced 6274 snapshots; capture read time was `{'median': 40.05770001094788, 'p95': 65.14409999363124, 'max': 117.50819999724627}`, snapshot age was `{'median': 6.0, 'p95': 12.0, 'max': 24.0}` frames, and 8 phase-counter discontinuities were excluded; 7319 decisions retained at least one robust-union body (maximum 42); 5565 decisions contained latent contact-disabled geometry (maximum 42), and 2743 contained bounded inactive-slot memory (maximum 37). 781 body samples retained observed world-motion estimates; world/internal speed and disagreement were `{'median': 0.0, 'p95': 2.467559814453125, 'max': 5.249580383300781}` / `{'median': 0.0, 'p95': 1.9904861450195312, 'max': 4.678527355194092}` / `{'median': 0.0, 'p95': 1.0, 'max': 5.077038972274117}`.
- The issue-time enemy guard retained 7792 observations, detected 2995 during-plan geometry changes, recertified 2995 decisions, and overrode 35 actions. Read/recertificate timing was `{'median': 1.4886000426486135, 'p95': 2.7446000603958964, 'max': 24.156500003300607}` / `{'median': 4.1316000279039145, 'p95': 64.22260007821023, 'max': 83.79029994830489}` ms; 5541 issue captures contained latent bodies (maximum 42), and 2754 contained dormant bodies (maximum 37). Fresh/global transactions preserved 2960/2995 planned actions, relaxed 0 fresh/global empty intersections, inherited 0 earlier planner relaxations, and recorded 0 silent outside-global selections.
- The synchronous spell-owner guard retained 5576 observations (5554 contact enabled, 22 anticipatory, 0 errors). 5576 observed owners were outside the ordinary 480-slot async scan; pointer counts were `{'0x0057D2F0': 5576}`.
- The terminal-threat heuristic covered 7792 decisions with horizon counts `{'0': 386, '10': 7406}`; it reported 0 collision and 0 sub-safety-clearance warnings, and relaxed 0 coarse constraints at clamped aliases.
- Modeled action hold counts were `{'2': 265, '3': 199, '4': 1755, '5': 3296, '6': 2277}` overall.
- Modeled uncontrollable-prefix counts were `{'2': 251, '3': 240, '4': 3220, '5': 2270, '6': 1811}`.
- Adaptive delay supports were `{'1,2': 72, '1,2,3': 81, '1,2,3,4': 58, '1,2,3,4,5': 80, '1,2,3,4,5,6': 124, '2,3': 6, '2,3,4': 1, '2,3,4,5': 6, '2,3,4,5,6': 1496, '3,4': 37, '3,4,5': 967, '3,4,5,6': 3637, '4,5,6': 1227}`; 156 decisions changed their nominal first action, 120 end-to-end transition samples were retained, and the maximum observed overrun/censored counters were 72/133.
- Robust viability supplied 7643 available policy queries (0 had new delay support outside the cached policy), constrained 0 decisions, and exposed 5252 empty queried action sets. Recovery guidance was available/selected on 278/0 empty-kernel queries; distant-kernel guidance was available/selected on 3429/0. Safe-action count, selected repair-volume, selected recovery-distance, and selected control-reserve deficit statistics were `{'median': 0.0, 'p95': 17.0, 'max': 17.0}`, `{'median': 0.0, 'p95': 0.0, 'max': 0.0}`, `None`, and `None`.
- Queried policy phase offsets within the coarse control layer were `{'0': 1334, '1': 1043, '2': 914, '3': 818, '4': 1030, '5': 805, '6': 936, '7': 763}`.
- Global-horizon/local-prefix cross-tab covered 3484 decisions: 0 had a winning global state but unsafe selected prefix, 2271 had a losing global state but safe short prefix, 0 selected globally certified actions contradicted the fresh local prefix checker, and 40 selected actions were outside the reported winning set. 2121 newer issue-time hazard versions and 8 deadline-held old inputs were excluded from the aligned comparison.
- The rolling worker produced 1787 unique policies with solve-time statistics `{'median': 181.2641000142321, 'p95': 311.66420003864914, 'max': 404.091399977915}` and first-observed ages `{'median': 5.0, 'p95': 15.0, 'max': 1807.0}`. Policy status counts were `{'pending_future_epoch': 93, 'queryable': 7645, 'expired': 15}`; 110 robust-mode decisions had no query.
- Of 3806 unambiguous output transitions, 3731 (0.980) were already visible in the next decision snapshot; their snapshot delta had median 1.000 frame.
- Separating physical contact from planner causality gives `{'global_viability_kernel_exhausted_before_hit': 24, 'missing_pre_hit_alive_decision': 4}`. Active input is the game-observed input at collision; the newly issued action on a hit row occurs after hit detection.
- Robust action-set exhaustion supplied 20 hit windows with a positive warning lead; those leads were `[10, 6, 9, 9, 5, 6, 12, 10, 34, 127, 22, 0, 56, 0, 82, 78, 0, 39, 0, 0, 12, 9, 18, 0, 0, 12, 0, 14]` frames.
- Across all phases, bottom-eight-pixel occupancy was 0.517 during the 60 frames preceding a hit versus 0.250 outside those windows.
- Mean selected control-reserve deficit was 0.000 during the 60 frames preceding a hit versus 0.000 outside those windows.
- Soft recovery was selected on 0.000 of alive decisions in the 60-frame pre-hit windows versus 0.000 outside; correlation alone is not a causal acceptance result.
- Later hits cannot estimate an initial-stock clear rate because Power falls from 128 to 2.000 after respawns. They remain valid counterexamples for geometry, latency, boundary use, and spell-specific pressure.

## Next Correction Gate

Treat policy delivery, delay-support coverage, and viability exhaustion as separate gates. The next focused run must keep rolling-policy queries available, reduce unsupported query epochs, and preserve a non-empty action kernel before each former hit window. Compare per-phase position and warning lead, not only aggregate hit count.
