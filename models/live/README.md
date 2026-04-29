# Live Model Artifact Handoff

This directory is the lightweight GitHub handoff between the workstation and
the Raspberry Pi.

The workstation owns research, full data refreshes, plots, backtests, and model
selection. Those heavy artifacts stay local and should not be committed.

The Raspberry Pi owns daily execution. It pulls this repository, refreshes its
own daily market data, reads the latest live model manifest when present, builds
today's signal locally, then submits/logs the Alpaca order.

Expected private handoff files:

```text
models/live/latest_model_manifest.json
models/live/<optional small per-symbol model artifacts>
```

`latest_model_manifest.json` may override the built-in per-symbol data path,
anchor/model artifact root, and live signal parameters. If the manifest is
missing, the Pi falls back to the checked-in defaults unless
`REQUIRE_LIVE_MODEL_MANIFEST=true` is set.

Do not put generated research folders, full optimization outputs, figures, or
local credentials here.
