# Interrupted Route Attempt 20260824_122318

- Mode: isolated Wine, Sakuya/Remilia Lunatic full route, hard no-Bomb.
- Repository: `69462830e7277fb9393c8bca177efd6f56128cd2` (clean).
- Duration contract: agent 86,400 seconds; supervisor 86,700 seconds.
- Disposition: intentionally cancelled by the operator after about 79 seconds
  so global planning could be repaired and validated on Stage 5 first.
- Host result: `KeyboardInterrupt`, not duration/stall timeout and not a solver
  counterexample.
- Cleanup: exact TH08 prefix processes `[]`; prefix `wineserver -k` returned 0.
  Unrelated Wine prefixes/displays were not signalled or modified.
- Evidence: ignored
  `artifacts/wine-th08/full-route-20260824T122318Z/report.json`.

This attempt is excluded from hit, latency, route-completion, and policy
comparisons. It exists only to prevent a user-directed cancellation from
being misclassified as a timeout or failed solver route.
