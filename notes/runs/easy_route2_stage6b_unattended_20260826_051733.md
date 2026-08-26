# TH08 Final B / Kaguya No-Bomb Practice Review: easy_route2_stage6b_unattended_20260826_051733

## Scope And Integrity

- Valid practice scope: `3..72320` (12394 decisions).
- Selected frame epoch: 0 of 1; 0 earlier decisions were excluded.
- Scope terminator: `raw_trace_end`; 0 reset-tail decisions were excluded.
- The agent's raw summary agrees with the scoped trace.
- Accepted complete practice: **YES**.
- Native hit edges: 9, at `[10519, 10843, 11417, 11818, 19278, 19846, 35028, 53738, 62118]`.
- Hard no-Bomb verification: **PASS** across 12394 decisions; mask/flag/action violations are all empty.

Bomb-stock changes in the trace are death/respawn state changes. They are not Bomb use: every scoped input mask has bit `0x02` clear, every decision has `bomb=false`, and no action requests Bomb.

## Primary Finding

The authoritative fresh-attempt hit is `EASY-S7-F10519-T1`. It occurred during spell 147 `薬符「壺中の大銀河」` at player (8.000, 345.418), with 665 bullets and 0 lasers. The projectile model reported pipeline clearance -0.269.

The primary class is `observed_bullet_overlap`. This trace contains the retained hit-window geometry for that classification; later post-respawn hits remain discovery evidence rather than fresh independent trials.

## Failure Taxonomy

| Cause | Hits |
| --- | ---: |
| `modeled_committed_prefix_collision` | 5 |
| `sensor_gap_or_unmodeled_hazard` | 2 |
| `observed_bullet_overlap` | 1 |
| `observed_laser_overlap` | 1 |

Contributing factors:

- `playfield_boundary`: 7
- `fast_mode`: 6

## Death Ledger

| Role | Frame | Spell | Player | Active input | Bullets/lasers | Pipeline/min 240f | Pipeline/robust warning | Contact/cause | Planner failure |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| canonical | 10519 | 147 薬符「壺中の大銀河」 | (8.000, 345.418) | `up_fast` | 665/0 | -0.269/-0.612 | 0f/13f | `observed_bullet_overlap` | `robust_action_set_exhausted_before_hit` |
| discovery | 10843 | 147 薬符「壺中の大銀河」 | (376.000, 410.858) | `up_right` | 580/0 | 0.229/0.229 | 0f/7f | `modeled_committed_prefix_collision` | `robust_action_set_exhausted_before_hit` |
| discovery | 11417 | 147 薬符「壺中の大銀河」 | (15.319, 414.625) | `down_right_fast` | 385/0 | 1.174/1.174 | 0f/0f | `sensor_gap_or_unmodeled_hazard` | `unresolved_planner_failure` |
| discovery | 11818 | 147 薬符「壺中の大銀河」 | (344.000, 432.000) | `left_fast` | 603/0 | 1.620/-7.819 | 13f/13f | `modeled_committed_prefix_collision` | `robust_action_set_exhausted_before_hit` |
| discovery | 19278 | 151 難題「龍の頸の玉  -五色の弾丸-」 | (376.000, 432.000) | `left_fast` | 21/195 | -4.262/-4.262 | 0f/11f | `observed_laser_overlap` | `robust_action_set_exhausted_before_hit` |
| discovery | 19846 | 151 難題「龍の頸の玉  -五色の弾丸-」 | (349.267, 429.700) | `up` | 29/215 | -0.140/-0.140 | 0f/7f | `modeled_committed_prefix_collision` | `robust_action_set_exhausted_before_hit` |
| discovery | 35028 | nonspell | (367.085, 429.172) | `up_left_fast` | 369/0 | -1.067/-1.067 | 0f/4f | `modeled_committed_prefix_collision` | `robust_action_set_exhausted_before_hit` |
| discovery | 53738 | 167 難題「蓬莱の弾の枝  -虹色の弾幕-」 | (16.132, 363.647) | `up_fast` | 305/0 | 1.248/0.028 | 0f/0f | `sensor_gap_or_unmodeled_hazard` | `unresolved_planner_failure` |
| discovery | 62118 | 175 「永夜返し  -子の刻-」 | (56.572, 429.700) | `up` | 892/0 | -5.533/-5.533 | 5f/9f | `modeled_committed_prefix_collision` | `robust_action_set_exhausted_before_hit` |

## Per-Phase Planner Health

| Phase | Hits | Decisions | Queries | Empty | Support outside | Constrained | Solves | Solve median ms | Bottom alive |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nonspell | 1 | 5183 | 0 | 0 | 0 | 0 | 0 | - | 0.009 |
| 147 薬符「壺中の大銀河」 | 4 | 554 | 0 | 0 | 0 | 0 | 0 | - | 0.026 |
| 151 難題「龍の頸の玉  -五色の弾丸-」 | 2 | 843 | 0 | 0 | 0 | 0 | 0 | - | 0.018 |
| 155 | 0 | 1166 | 0 | 0 | 0 | 0 | 0 | - | 0.055 |
| 159 | 0 | 969 | 0 | 0 | 0 | 0 | 0 | - | 0.018 |
| 163 | 0 | 611 | 0 | 0 | 0 | 0 | 0 | - | 0.000 |
| 167 難題「蓬莱の弾の枝  -虹色の弾幕-」 | 1 | 1392 | 0 | 0 | 0 | 0 | 0 | - | 0.012 |
| 171 | 0 | 281 | 0 | 0 | 0 | 0 | 0 | - | 0.039 |
| 175 「永夜返し  -子の刻-」 | 1 | 216 | 0 | 0 | 0 | 0 | 0 | - | 0.126 |
| 179 | 0 | 334 | 0 | 0 | 0 | 0 | 0 | - | 0.009 |
| 183 | 0 | 284 | 0 | 0 | 0 | 0 | 0 | - | 0.032 |
| 187 | 0 | 561 | 0 | 0 | 0 | 0 | 0 | - | 0.020 |

## Interpretation

- Retained witnesses classify 1 bullet overlaps, 1 laser overlaps, and 0 exact same-epoch enemy-body overlaps; 0 of those enemy slots were absent from the action snapshot.
- The controller decision cadence was 4.000 frames median and 5.000 frames p95. The local plan took 34.647 ms median and 47.296 ms p95.
- The full enemy sensor produced 6178 snapshots; capture read time was `{'median': 104.01144999923417, 'p95': 141.0334000029252, 'max': 240.1283999934094}`, snapshot age was `{'median': 7.0, 'p95': 11.0, 'max': 19.0}` frames, and 22 phase-counter discontinuities were excluded; 11862 decisions retained at least one robust-union body (maximum 35); 9619 decisions contained latent contact-disabled geometry (maximum 35), and 1167 contained bounded inactive-slot memory (maximum 16). 93 body samples retained observed world-motion estimates; world/internal speed and disagreement were `{'median': 6.417378743489583, 'p95': 9.02520751953125, 'max': 9.0848388671875}` / `{'median': 6.55621337890625, 'p95': 9.084259033203125, 'max': 9.17547607421875}` / `{'median': 0.34876505533854196, 'p95': 0.4777119954427083, 'max': 0.49092610677083326}`.
- The issue-time enemy guard retained 12394 observations, detected 991 during-plan geometry changes, recertified 991 decisions, and overrode 7 actions. Read/recertificate timing was `{'median': 2.4939499999163672, 'p95': 4.747500002849847, 'max': 19.14270000270335}` / `{'median': 7.543400002759881, 'p95': 17.121199998655356, 'max': 36.54100000130711}` ms; 7815 issue captures contained latent bodies (maximum 35), and 1178 contained dormant bodies (maximum 16). Fresh/global transactions preserved 984/991 planned actions, relaxed 0 fresh/global empty intersections, inherited 0 earlier planner relaxations, and recorded 0 silent outside-global selections.
- The synchronous spell-owner guard retained 10994 observations (9186 contact enabled, 1808 anticipatory, 0 errors). 10994 observed owners were outside the ordinary 480-slot async scan; pointer counts were `{'0x0057D2F0': 10994}`.
- The terminal-threat heuristic covered 12394 decisions with horizon counts `{'0': 434, '10': 11960}`; it reported 0 collision and 0 sub-safety-clearance warnings, and relaxed 0 coarse constraints at clamped aliases.
- Modeled action hold counts were `{'2': 250, '3': 169, '4': 8786, '5': 2635, '6': 554}` overall.
- Modeled uncontrollable-prefix counts were `{'2': 174, '3': 111, '4': 10334, '5': 1770, '6': 5}`.
- Adaptive delay supports were `{'2,3': 6, '2,3,4': 43, '2,3,4,5': 366, '2,3,4,5,6': 934, '3,4': 595, '3,4,5': 2460, '3,4,5,6': 4454, '4': 53, '4,5': 614, '4,5,6': 2868, '5,6': 1}`; 54 decisions changed their nominal first action, 120 end-to-end transition samples were retained, and the maximum observed overrun/censored counters were 34/108.
- Robust viability supplied 0 available policy queries (0 had new delay support outside the cached policy), constrained 0 decisions, and exposed 0 empty queried action sets. Recovery guidance was available/selected on 0/0 empty-kernel queries; distant-kernel guidance was available/selected on 0/0. Safe-action count, selected repair-volume, selected recovery-distance, and selected control-reserve deficit statistics were `None`, `None`, `None`, and `None`.
- Queried policy phase offsets within the coarse control layer were `{}`.
- Global-horizon/local-prefix cross-tab covered 0 decisions: 0 had a winning global state but unsafe selected prefix, 0 had a losing global state but safe short prefix, 0 selected globally certified actions contradicted the fresh local prefix checker, and 0 selected actions were outside the reported winning set. 0 newer issue-time hazard versions and 0 deadline-held old inputs were excluded from the aligned comparison.
- The rolling worker produced 0 unique policies with solve-time statistics `None` and first-observed ages `None`. Policy status counts were `{}`; 0 robust-mode decisions had no query.
- Of 6310 unambiguous output transitions, 6287 (0.996) were already visible in the next decision snapshot; their snapshot delta had median 1.000 frame.
- Separating physical contact from planner causality gives `{'robust_action_set_exhausted_before_hit': 7, 'unresolved_planner_failure': 2}`. Active input is the game-observed input at collision; the newly issued action on a hit row occurs after hit detection.
- Robust action-set exhaustion supplied 7 hit windows with a positive warning lead; those leads were `[13, 7, 0, 13, 11, 7, 4, 0, 9]` frames.
- Across all phases, bottom-eight-pixel occupancy was 0.230 during the 60 frames preceding a hit versus 0.017 outside those windows.
- Mean selected control-reserve deficit was 0.000 during the 60 frames preceding a hit versus 0.000 outside those windows.
- Soft recovery was selected on 0.000 of alive decisions in the 60-frame pre-hit windows versus 0.000 outside; correlation alone is not a causal acceptance result.
- Later hits cannot estimate an initial-stock clear rate because Power falls from 128 to 9.000 after respawns. They remain valid counterexamples for geometry, latency, boundary use, and spell-specific pressure.

## Next Correction Gate

The paired run halves hits without any global query, so Easy does not yet justify a more complex corridor solver. First audit the two positive-clearance/no-warning contacts at frames 11417 and 53738 against hit-edge sensing order and source-known future births. Then use the seven modeled losing-prefix witnesses to evaluate a cheap generic local viable-continuation signal during their existing warning lead. Preserve the global framework for authoritative harder-mode roots; do not add a stage, spell, or difficulty branch from this result.
