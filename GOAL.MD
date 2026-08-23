# TH08 Solver Goal

> Workspace status (2026-08-23): active TH08 research has resumed. The user
> explicitly restored Lunatic Sakuya/Remilia Route-2 as the completion target
> and authorized isolated Wine gameplay on this VPS.

## Active completion target

Build a solver and live controller that **physically completes a fresh,
full-game Touhou 8 Lunatic Route-2 run with Sakuya/Remilia as No Miss No Bomb
(NMNB)**.

The minimum achievement witness is one retained, reviewable run that:

- starts from the normal game-start state, including initial Power and
  resources;
- is a full route, not Stage Practice, replay playback, save-state, or a
  native snapshot/root continuation;
- progresses through the real shipped TH08 engine across Stages 1, 2, 3, 4A,
  5, and Final-B to route completion;
- records zero collision hits, zero life losses, and zero Bomb uses;
- uses only ordinary movement, Focus, Shot, and dialogue/menu inputs during
  gameplay;
- preserves enough native trace, replay, resource, stage/phase, input, and
  timing evidence to audit the NMNB claim.

Diagnostic and acceptance runs may use the verified one-byte
no-life-decrement patch only when its exact executable/patch identity is
retained. For an accepted zero-hit run the patched life-decrement branch is
never exercised; native hit edges must independently prove that condition.
This is an original-engine execution claim, not a claim that the executable
bytes were unmodified.

One clean full Lunatic route achieves the active NMNB milestone. Robust Lunatic
closure requires two additional clean full routes on distinct natural RNG
roots: three retained clean full routes total. These repeats are a final
acceptance gate after the first NMNB, not a per-change iteration gate.

Extra is follow-on scope after Lunatic closure. A Hard result or an Extra
workload does not substitute for the active Lunatic target.

## What counts as progress

The primary research metric is a causal improvement to the general solver,
planner, model, or live delivery path that reduces physical Lunatic full-route
hit risk. Lunatic Stage 3, Stage 4A, Stage 5, Final-B, and focused physical trials
are representative workloads used to iterate quickly and test
generalization. Fixed-root wind-tunnel branches are diagnostic only and are
not a promotion gate for the active objective.

A fixed-root no-hit witness, offline/model success, replay success, clean
practice stage, or lower hit count on a different RNG root is valuable
evidence, but none is the completion target by itself. A change is promoted
only through the evidence and physical-validation loop in `STRATEGY.md`.

Prefer general survival, combat, Focus, Power, planning, and delivery
improvements over spell- or stage-specific patches. After a major integrated
gain, pay a fresh full-route Lunatic run to measure whether the work moves
this goal.
