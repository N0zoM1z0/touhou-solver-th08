# TH08 Final B / Kaguya No-Bomb Practice Review: easy_route2_stage6b_unattended_20260826_063823

## Scope And Integrity

- Valid practice scope: `2..74364` (13083 decisions).
- Selected frame epoch: 0 of 1; 0 earlier decisions were excluded.
- Scope terminator: `raw_trace_end`; 0 reset-tail decisions were excluded.
- The agent's raw summary agrees with the scoped trace.
- Accepted complete practice: **YES**.
- Native hit edges: 11, at `[7864, 12292, 12959, 13301, 13609, 21312, 22868, 23875, 48190, 51014, 57594]`.
- Hard no-Bomb verification: **PASS** across 13083 decisions; mask/flag/action violations are all empty.
- Ignored raw trace: 458,867,409 bytes, SHA-256
  `d0f97d1d2505fb91378904af07f036f6e628b95f5fff5b56c6d5ef25698400a8`.
- Isolated host report SHA-256:
  `fe768fa4eb9645f3fe67b8efa8140870d61f6129fc8b21a4aae1e891864e61af`;
  controller exit 0 and `leftover_prefix_processes=[]`.

Bomb-stock changes in the trace are death/respawn state changes. They are not Bomb use: every scoped input mask has bit `0x02` clear, every decision has `bomb=false`, and no action requests Bomb.

## Primary Finding

The authoritative fresh-attempt hit is `EASY-S7-F7864-T1`. It occurred during a nonspell phase at player (48.042, 425.100), with 156 bullets and 0 lasers. The projectile model reported pipeline clearance 4.410.

The primary class is `observed_bullet_overlap`. This trace contains the retained hit-window geometry for that classification; later post-respawn hits remain discovery evidence rather than fresh independent trials.

## Failure Taxonomy

| Cause | Hits |
| --- | ---: |
| `observed_laser_overlap` | 5 |
| `modeled_committed_prefix_collision` | 3 |
| `observed_bullet_overlap` | 3 |

Contributing factors:

- `playfield_boundary`: 6
- `action_lag_over_model`: 4
- `fast_mode`: 4

## Death Ledger

| Role | Frame | Spell | Player | Active input | Bullets/lasers | Pipeline/min 240f | Pipeline/robust warning | Contact/cause | Planner failure |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| canonical | 7864 | nonspell | (48.042, 425.100) | `up` | 156/0 | 4.410/-0.445 | 5f/5f | `observed_bullet_overlap` | `robust_action_set_exhausted_before_hit` |
| discovery | 12292 | 147 薬符「壺中の大銀河」 | (359.902, 432.000) | `right` | 751/0 | -3.041/-3.041 | 8f/8f | `modeled_committed_prefix_collision` | `robust_action_set_exhausted_before_hit` |
| discovery | 12959 | 147 薬符「壺中の大銀河」 | (376.000, 432.000) | `down_right` | 572/0 | -2.627/-2.627 | 0f/8f | `observed_bullet_overlap` | `robust_action_set_exhausted_before_hit` |
| discovery | 13301 | 147 薬符「壺中の大銀河」 | (40.294, 274.068) | `down_right` | 521/0 | -1.773/-1.773 | 0f/0f | `modeled_committed_prefix_collision` | `late_collision_after_positive_causal_margin` |
| discovery | 13609 | 147 薬符「壺中の大銀河」 | (173.737, 432.000) | `right` | 614/0 | -2.705/-5.982 | 7f/7f | `modeled_committed_prefix_collision` | `robust_action_set_exhausted_before_hit` |
| discovery | 21312 | 151 難題「龍の頸の玉  -五色の弾丸-」 | (376.000, 432.000) | `down_left` | 20/205 | -2.051/-3.025 | 6f/11f | `observed_laser_overlap` | `robust_action_set_exhausted_before_hit` |
| discovery | 22868 | 151 難題「龍の頸の玉  -五色の弾丸-」 | (8.000, 431.940) | `right_fast` | 24/205 | -3.478/-3.478 | 0f/11f | `observed_laser_overlap` | `robust_action_set_exhausted_before_hit` |
| discovery | 23875 | 151 難題「龍の頸の玉  -五色の弾丸-」 | (12.000, 432.000) | `right_fast` | 20/225 | -3.615/-3.615 | 7f/48f | `observed_laser_overlap` | `robust_action_set_exhausted_before_hit` |
| discovery | 48190 | 163 難題「燕の子安貝  -永命線-」 | (216.030, 271.547) | `up_left` | 202/52 | -0.416/-1.873 | 5f/10f | `observed_laser_overlap` | `robust_action_set_exhausted_before_hit` |
| discovery | 51014 | 163 難題「燕の子安貝  -永命線-」 | (34.116, 361.979) | `left_fast` | 199/52 | -2.671/-2.671 | 0f/6f | `observed_laser_overlap` | `robust_action_set_exhausted_before_hit` |
| discovery | 57594 | 167 難題「蓬莱の弾の枝  -虹色の弾幕-」 | (362.803, 403.721) | `down_left_fast` | 243/0 | 7.231/-2.598 | 4f/4f | `observed_bullet_overlap` | `robust_action_set_exhausted_before_hit` |

## Per-Phase Planner Health

| Phase | Hits | Decisions | Queries | Empty | Support outside | Constrained | Solves | Solve median ms | Bottom alive |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nonspell | 1 | 5781 | 0 | 0 | 0 | 0 | 0 | - | 0.006 |
| 147 薬符「壺中の大銀河」 | 4 | 521 | 0 | 0 | 0 | 0 | 0 | - | 0.040 |
| 151 難題「龍の頸の玉  -五色の弾丸-」 | 3 | 846 | 0 | 0 | 0 | 0 | 0 | - | 0.023 |
| 155 | 0 | 982 | 0 | 0 | 0 | 0 | 0 | - | 0.001 |
| 159 | 0 | 1013 | 0 | 0 | 0 | 0 | 0 | - | 0.000 |
| 163 難題「燕の子安貝  -永命線-」 | 2 | 955 | 0 | 0 | 0 | 0 | 0 | - | 0.020 |
| 167 難題「蓬莱の弾の枝  -虹色の弾幕-」 | 1 | 1371 | 0 | 0 | 0 | 0 | 0 | - | 0.020 |
| 171 | 0 | 266 | 0 | 0 | 0 | 0 | 0 | - | 0.079 |
| 175 | 0 | 170 | 0 | 0 | 0 | 0 | 0 | - | 0.103 |
| 179 | 0 | 332 | 0 | 0 | 0 | 0 | 0 | - | 0.012 |
| 183 | 0 | 269 | 0 | 0 | 0 | 0 | 0 | - | 0.011 |
| 187 | 0 | 577 | 0 | 0 | 0 | 0 | 0 | - | 0.008 |

## Interpretation

- Retained witnesses classify 3 bullet overlaps, 5 laser overlaps, and 0 exact same-epoch enemy-body overlaps; 0 of those enemy slots were absent from the action snapshot.
- The controller decision cadence was 4.000 frames median and 5.000 frames p95. The local plan took 32.855 ms median and 51.678 ms p95.
- The full enemy sensor produced 6627 snapshots; capture read time was `{'median': 91.54290000151377, 'p95': 134.25590000406373, 'max': 207.1326000004774}`, snapshot age was `{'median': 7.0, 'p95': 11.0, 'max': 17.0}` frames, and 25 phase-counter discontinuities were excluded; 12372 decisions retained at least one robust-union body (maximum 32); 10008 decisions contained latent contact-disabled geometry (maximum 32), and 1381 contained bounded inactive-slot memory (maximum 16). 105 body samples retained observed world-motion estimates; world/internal speed and disagreement were `{'median': 7.768473307291667, 'p95': 10.27252197265625, 'max': 10.669601440429688}` / `{'median': 7.95440673828125, 'p95': 10.41485595703125, 'max': 10.743927001953125}` / `{'median': 0.27733612060546875, 'p95': 0.5357462565104167, 'max': 8.370933532714844}`.
- The issue-time enemy guard retained 13083 observations, detected 1019 during-plan geometry changes, recertified 1019 decisions, and overrode 12 actions. Read/recertificate timing was `{'median': 2.551999998104293, 'p95': 4.971800000930671, 'max': 17.032600000675302}` / `{'median': 7.9528999995091, 'p95': 19.99660000001313, 'max': 40.902400003687944}` ms; 8261 issue captures contained latent bodies (maximum 32), and 1378 contained dormant bodies (maximum 16). Fresh/global transactions preserved 1007/1019 planned actions, relaxed 0 fresh/global empty intersections, inherited 0 earlier planner relaxations, and recorded 0 silent outside-global selections.
- The synchronous spell-owner guard retained 11623 observations (9859 contact enabled, 1764 anticipatory, 0 errors). 11623 observed owners were outside the ordinary 480-slot async scan; pointer counts were `{'0x0057D2F0': 11623}`.
- The terminal-threat heuristic covered 13083 decisions with horizon counts `{'0': 585, '10': 12498}`; it reported 0 collision and 0 sub-safety-clearance warnings, and relaxed 0 coarse constraints at clamped aliases.
- Modeled action hold counts were `{'2': 214, '3': 229, '4': 5750, '5': 5678, '6': 1212}` overall.
- Modeled uncontrollable-prefix counts were `{'2': 166, '3': 220, '4': 9462, '5': 2860, '6': 375}`.
- Adaptive delay supports were `{'2': 40, '2,3': 45, '2,3,4': 314, '2,3,4,5': 270, '2,3,4,5,6': 1137, '3,4': 185, '3,4,5': 1270, '3,4,5,6': 9103, '4,5,6': 719}`; 42 decisions changed their nominal first action, 120 end-to-end transition samples were retained, and the maximum observed overrun/censored counters were 55/98.
- Robust viability supplied 0 available policy queries (0 had new delay support outside the cached policy), constrained 0 decisions, and exposed 0 empty queried action sets. Recovery guidance was available/selected on 0/0 empty-kernel queries; distant-kernel guidance was available/selected on 0/0. Safe-action count, selected repair-volume, selected recovery-distance, and selected control-reserve deficit statistics were `None`, `None`, `None`, and `None`.
- Queried policy phase offsets within the coarse control layer were `{}`.
- Global-horizon/local-prefix cross-tab covered 0 decisions: 0 had a winning global state but unsafe selected prefix, 0 had a losing global state but safe short prefix, 0 selected globally certified actions contradicted the fresh local prefix checker, and 0 selected actions were outside the reported winning set. 0 newer issue-time hazard versions and 0 deadline-held old inputs were excluded from the aligned comparison.
- The rolling worker produced 0 unique policies with solve-time statistics `None` and first-observed ages `None`. Policy status counts were `{}`; 0 robust-mode decisions had no query.
- Of 6465 unambiguous output transitions, 6445 (0.997) were already visible in the next decision snapshot; their snapshot delta had median 1.000 frame.
- Separating physical contact from planner causality gives `{'robust_action_set_exhausted_before_hit': 10, 'late_collision_after_positive_causal_margin': 1}`. Active input is the game-observed input at collision; the newly issued action on a hit row occurs after hit detection.
- Robust action-set exhaustion supplied 10 hit windows with a positive warning lead; those leads were `[5, 8, 8, 0, 7, 11, 11, 48, 10, 6, 4]` frames.
- Across all phases, bottom-eight-pixel occupancy was 0.228 during the 60 frames preceding a hit versus 0.010 outside those windows.
- Mean selected control-reserve deficit was 0.000 during the 60 frames preceding a hit versus 0.000 outside those windows.
- Soft recovery was selected on 0.000 of alive decisions in the 60-frame pre-hit windows versus 0.000 outside; correlation alone is not a causal acceptance result.
- Later hits cannot estimate an initial-stock clear rate because Power falls from 128 to 14.000 after respawns. They remain valid counterexamples for geometry, latency, boundary use, and spell-specific pressure.

## Next Correction Gate

This is an accepted observability falsifier, not a survival promotion: 11 hits
is worse than the retained nine-hit checkpoint.  The age correction is active
because no contact remains in the old sensing-gap class, but ten of eleven
contacts reach short-horizon robust action-set exhaustion first.  The next
generic offline gate is AUD-094.  Mutually exclusive ages now use one
outward-rounded AABB hull per bullet instead of summed duplicate trajectories;
exact contacts, latency, and stateful differentials pass.  Next make the
configured 10..32 frame constant-tail local threat check actually run without
global guidance.
Do not add a difficulty/stage/spell branch or re-enable global work for Easy.
