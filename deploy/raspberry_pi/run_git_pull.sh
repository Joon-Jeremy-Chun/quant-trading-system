#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${REPO_ROOT}"

# Discard local data CSV changes before pull.
# Pi re-fetches fresh prices from Alpaca at 09:05 via run_price_update.sh,
# so discarding stale tracked CSVs is safe.
git restore data/ 2>/dev/null || true

git pull --ff-only
echo "[git-pull] Done -- $(date)"
