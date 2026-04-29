# Pi Model Artifact Handoff

Date: 2026-04-28

## Purpose

This note records the deployment architecture chosen after separating the
research workflow from the Raspberry Pi execution workflow.

The main idea is:

1. the workstation does heavy research and model selection,
2. GitHub carries only small live model handoff artifacts,
3. the Raspberry Pi pulls the latest handoff, refreshes its own daily data,
4. the Raspberry Pi builds today's signal locally and sends the Alpaca order.

## Why This Split

The repository should not carry generated research folders, full optimization
outputs, plots, or large historical analysis artifacts. Those are reproducible
and belong on the workstation.

The Raspberry Pi only needs enough information to run the live operating path:

- code,
- small live model artifact metadata,
- current live model pointers,
- local environment secrets,
- daily market data fetched at runtime,
- small live signal and execution logs.

This keeps GitHub pushes small and avoids repeating the large-pack failure that
happened when generated `outputs/` and `figures/` history entered a branch.

## Operating Roles

### Workstation

The workstation owns:

- data archive refresh for research,
- backtests and model comparisons,
- graph/report generation,
- live model selection,
- publishing the latest `models/live` handoff files.

The workstation should not push generated research output folders unless there
is a deliberate reason.

### GitHub

GitHub is the lightweight synchronization layer.

Expected live handoff location:

```text
models/live/latest_model_manifest.json
models/live/<optional small per-symbol model artifacts>
```

Large folders such as `outputs/`, `figures/`, `research/**/outputs/`, and
`models/research/` are treated as local or reproducible artifacts.

### Raspberry Pi

The Raspberry Pi owns:

- `git pull --ff-only`,
- reading `models/live/latest_model_manifest.json`,
- refreshing GLD/BRK-B daily data independently,
- building today's live signals locally,
- submitting or logging Alpaca orders,
- sending the email report.

The Pi should push only small execution records when needed. It should not
become the source of truth for research data.

## Current Implementation

The implementation is on branch:

```text
codex/pi-model-artifact-handoff
```

Main commit:

```text
fbef645a Add Pi model artifact handoff pipeline
```

Key files:

- `jobs/gld_daily_pipeline.py`
- `deploy/raspberry_pi/quant-trading.env.example`
- `deploy/raspberry_pi/run_daily_pipeline.sh`
- `models/live/README.md`
- `models/live/latest_model_manifest.json`
- `models/live/latest_model_manifest.example.json`

The pipeline now reads `LIVE_MODEL_MANIFEST`, defaulting to:

```text
models/live/latest_model_manifest.json
```

If the manifest exists, it can override per-symbol paths and signal parameters
before the Pi builds live signals. If it is missing, the Pi falls back to the
checked-in defaults unless:

```text
REQUIRE_LIVE_MODEL_MANIFEST=true
```

## Safety Rules

- Do not push `outputs/` or `figures/` for normal operation.
- Do not push `research/**/outputs/`.
- Do not push `models/research/`.
- Do not push real Alpaca keys or local env files.
- Keep `ALPACA_DRY_RUN=true` until the Pi logs, email, and paper orders are
  verified.
- Prefer a clean branch from `origin/main` for deployment fixes when the main
  working tree has generated output changes.

## Next Step

The next engineering step is to make the workstation export a real compact
live model bundle into `models/live/`, rather than relying on the current
anchor-snapshot compatibility path. The Pi-side manifest loading is now ready
for that transition.
