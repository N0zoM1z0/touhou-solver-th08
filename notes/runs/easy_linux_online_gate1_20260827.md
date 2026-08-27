# Native-Linux Online Easy Delivery Gate 1

## Result

This authorized bounded physical diagnostic completed normally, but **failed
the online future/global integration gate**.

- Solver checkpoint at launch: `48a14a7826cc4980118a6a71dcb1ee7eed84ab00`.
- Authored runtime checkpoint: `e0c181ec42b3f6968bf9c7e1fb42d87c7ed55fd2`.
- Runtime ELF SHA-256:
  `141cb3b69040626cf51e1837acad4600a409f332acd8ccfe1ae8cca5396c2995`.
- Workload: normal-start Sakuya/Remilia Easy Route 2, bounded after 3,600
  coherent gameplay observations; retained lives; hard no-Bomb.
- Display and ownership: isolated warm Xvfb `:121`, one 640x480 TH08 window,
  exact native child owned by the Python supervisor.
- Finish: `diagnostic-gameplay-epoch-cap`, no supervisor/runtime exception,
  102.051 seconds wall time.
- Stage coverage: Stage 1 only.
- Native phase-2 hit edges: **7**. First hit was Stage-1 ordinary at manager
  frame 1,429 / source input epoch 1,565, player `(192, 384)`.
- Bomb: no Bomb bit was observed in any native request or solver response.
  This bounded diagnostic produced no replay.

The compact report is
`artifacts/runtime_reports/easy_linux_online_gate1_20260827.json`, SHA-256
`b1b29176a99bb3a11462ddfc28e9b142a8270d13a1faee52e19689bab81372ff`.

## Delivery evidence

| Metric | Observed |
| --- | ---: |
| Bridge publications | 4,942 |
| Publications drained to a newer root | 712 |
| Coherent gameplay captures | 3,600 |
| Gameplay actions sent on time | 1,176 |
| Stale capture abandons | 1,205 |
| Stale plan abandons | 2,424 |
| Native deadline-miss counter delta | 4,341 |
| Native late-response / dropped-request delta | 0 / 0 |
| Response-queue drops | 0 |
| Clock-certified / rejected observations | 2,866 / 718 |
| Clock delta mismatches | 0 |

Every on-time gameplay decision selected complete mask `0x05` (Shot+Focus,
no direction). This is not evidence that `stay` is a useful policy. The
successful timing population is strongly selected toward roots whose complete
foreground transaction happened to finish before the next input epoch.

For those 1,176 successful rows, publication age was 5.18 ms mean / 13.97 ms
p95 and complete decision time was 11.74 / 13.53 ms. Pool read, decode, and
local plan were respectively 5.88/6.55, 0.37/0.68, and 0.78/1.47 ms
mean/p95. Failed capture/plan transactions are absent from those timing
summaries, so these numbers must not be presented as the unconditional online
cost.

The runner did not retain final lives/Bombs/Power/items or the maximum
consecutive held-fallback length. Lives were configured as preserved and Bomb
was attested on the wire, but the missing resource/fallback fields are a
telemetry defect to correct before another physical promotion gate.

## Future/global evidence

The input/manager cadence boundary itself activated: runtime ECL identity was
accepted once, 2,866 observations were clock-certified, and no unequal clock
delta occurred. Everything after that boundary failed:

| Producer/consumer metric | Observed |
| --- | ---: |
| Future submissions | 574 |
| Future completions | 0 |
| Future rejections | 574 |
| Corridor submissions/completions | 0 / 0 |
| Authority queries/allowed queries | 0 / 0 |
| Globally constrained actions | 0 |

All retained on-time rows report
`scale_status=root_only_source_inventory_unknown`; future work reports
`capture-error`. **Observed:** the transitional producer never supplied one
complete future root or scale certificate. **Inferred from the implementation:**
the future capture still requires its roughly 10 MiB enemy/source transaction
and supporting reads to fit inside one unchanged manager/update-serial
bracket, while the no-scale-writer authority synchronously retries its own
complete source inventory in the foreground. At continuous cadence the former
crosses the frame and the latter consumes the action deadline. The current
telemetry did not retain the exact exception/status subreason, so this
mechanism should be confirmed by deterministic instrumentation rather than
claimed as a captured exception trace.

## Decision

Gate 1 is failed. Do not tune corridor lead, objectives, grid size, or local
beam width on this result. The next implementation boundary is the already
proposed runtime-owned packed post-update root/certificate (or an equivalent
double-buffered immutable publication) and a foreground path that performs no
large source inventory. Future projection and the immediate shield must
consume that versioned root; `/proc` frame-stability luck is not an online
producer contract.

The initial invocation also failed before process creation because the new
route tool named the obsolete `ResultScreen::OnUpdate(void*)` mangling. The
authored function is `ResultScreen::OnUpdate(ResultScreen*)`, exported as
`_ZN4th0812ResultScreen8OnUpdateEPS0_` at `0x080d779c`. The constant and a
focused regression were corrected before this sole gameplay trial; no solver
flags or acceptance criteria changed.

## Retention and cleanup

- Task-scoped raw data copy: `/tmp/th08-online-gate1.SJ5zFJ` (332 KiB,
  intentionally retained because the gate failed).
- Runtime log SHA-256:
  `eee0ca8d970757b2f41cf322ebb5370ab06b940371331a03de97ee4871cf8613`.
- Loaded-file trace SHA-256:
  `a2fc962ae47191c577f4ceb98376b593865d1342035c63be6afa7acdf0771831`.
- Cleanup observed: supervisor, exact TH08 child, socket helper, and window all
  exited; Xvfb `:121` returned to an empty window tree. No Wine/controller
  process was started and no injected key remained held.
