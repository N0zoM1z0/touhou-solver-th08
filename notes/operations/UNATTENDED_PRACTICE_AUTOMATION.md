# TH08 Physical Trial Protocol

Use only with explicit user authorization. The original Windows game receives
real keyboard input and may be terminated by the supervisor.

## Launch

From Windows:

```bat
run_th08_practice_agent.bat --stage 3
run_th08_practice_agent.bat --stage 4a
run_th08_practice_agent.bat --stage 5
run_th08_practice_agent.bat --stage 6b
run_th08_full_route_agent.bat
```

The wrappers select Windows Python and add `--armed`. Practice accepts
`--difficulty`, `--repeat`, and `--save-replay-slot 1..15`. A prepared runtime
whose score lacks the requested team/difficulty clear bit may explicitly add
`--unlock-requested-stage`; after exact menu/route/difficulty validation it
sets and rereads only that source-defined Practice availability bit. The
full-route wrapper pins the decoded Final-B ECL image and enables the exact
scale schedule authority.

The diagnostic root-only scale continuation is explicit:

```bat
run_th08_practice_agent.bat --stage 5 --diagnostic-continue-root-only-scale
```

It is unknown-direction and cannot be combined with exact Final-B schedule
authority.

## Preflight

Before input injection verify:

- exact executable identity and supported no-life-decrement patch;
- no old TH08/controller/supervisor/replay/test process;
- correct foreground window and keyboard ownership;
- Sakuya/Remilia, Route 2, difficulty, and requested stage;
- native gameplay state;
- hard no-Bomb configuration;
- adequate disk space for one raw trace and replay copy.

The daemon is warm before menu selection. F8 starts, F9 stops, and F10 exits.
Do not use Windows CLI probes during gameplay because they may steal
foreground.

## Supervision

WSL process launch return is not completion. Monitor:

- exact interop/Windows process;
- trace growth and manager-frame progress;
- terminal supervisor status;
- hit/Bomb/deadline/fallback counters;
- dialogue/transition progress.

On stall, foreground loss, identity mismatch, timeout, or error, stop and
release every injected key. Never leave the game or a suspended native-root
session unattended.

## Retention

For a completed trial retain compact:

- repository/model/policy identity;
- route/difficulty/team/stage and physical mode;
- frames/decisions/hits/Bombs and first hit;
- lives/Bombs/Power/items and stage/phase attribution;
- deadline, fallback, sensing, transition, and foreground health;
- raw trace SHA/path (local/ignored);
- replay SHA/manifest when accepted;
- exact cleanup status.

Keep the two newest compatible replay-capable raw bundles for each active
workload until two newer compact reports exist.

Practice replay saving resolves the live result object, archives the old slot,
writes the chosen slot, decodes it, and verifies route/difficulty/stage and an
empty Bomb list. Full-route Final-B may unload before a saveable result object
exists; fail closed and do not repeat a complete run solely to obtain a
replay.

## Interpretation

The first hit is the canonical causal witness. Later hits remain useful for
geometry/planner attribution but are not independent clean-route samples.

Different-RNG totals are observational. A strategy promotion needs same-root
native evidence plus repeated rotated physical validation.

Use one focused stage for a named hypothesis, rotate the next gate, and run a
full route only after a material integrated improvement or when global
resource/transition carry is the question.
