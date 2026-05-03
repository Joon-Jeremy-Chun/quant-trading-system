# run_pending_anchors.ps1
# Chains: (0) GLD remaining 2 anchors -> (1) ITA all 111 anchors -> (2) VRT all 81 anchors
# Run from repo root: .\run_pending_anchors.ps1

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ROOT

Write-Host "============================================================"
Write-Host " PENDING ANCHOR RUNS - $(Get-Date)"
Write-Host "============================================================"


# ============================================================
# STEP 0: GLD - eval for anchor_2026-03-31 and anchor_2026-04-29
# ============================================================
Write-Host "`n[STEP 0] GLD remaining anchors (2026-03-31, 2026-04-29)" -ForegroundColor Cyan

$gldRoot = "outputs\objective1_anchor_date_multi_horizon_evaluation"
Copy-Item "$gldRoot\master_summary.json" "$gldRoot\master_summary_backup_70.json" -Force
Copy-Item "$gldRoot\master_summary.csv"  "$gldRoot\master_summary_backup_70.csv"  -Force
Write-Host "  Backed up master_summary (70 rows)"

python strategies\automation\run_objective1_anchor_date_multi_horizon_evaluation.py `
    --anchor-dates "2026-03-31,2026-04-29" `
    --data-csv "C:/Users/joonc/my_github/quant-trading-system/data/gld_us_d.csv" `
    --anchor-output-root outputs/objective1_anchor_date_multi_horizon_evaluation `
    --top-n 20 `
    --n-jobs -1 `
    --reuse-existing-optimization-snapshots 2>&1 | Tee-Object outputs\anchor_run_gld_2026_remaining.log

if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] GLD step failed" -ForegroundColor Red; exit 1 }

# Merge: write merge script to temp file then run
@'
import json, pandas as pd, sys
root = sys.argv[1]
old  = json.load(open(root + r"\master_summary_backup_70.json"))
new  = json.load(open(root + r"\master_summary.json"))
rows = old + new
rows.sort(key=lambda x: (x["anchor_date"], x["evaluation_horizon"]))
with open(root + r"\master_summary.json", "w") as f:
    json.dump(rows, f, indent=2)
pd.DataFrame(rows).to_csv(root + r"\master_summary.csv", index=False)
print(f"[OK] GLD master_summary: {len(rows)} rows (was 70, added {len(new)})")
'@ | Out-File -FilePath "outputs\_merge_gld.py" -Encoding utf8

python outputs\_merge_gld.py $gldRoot
Remove-Item "outputs\_merge_gld.py" -ErrorAction SilentlyContinue

Write-Host "[STEP 0] GLD done." -ForegroundColor Green


# ============================================================
# STEP 1: ITA - all 111 anchors (reuse first 19 completed)
# ============================================================
Write-Host "`n[STEP 1] ITA anchors (all 111, reuse first 19)" -ForegroundColor Cyan

# Remove empty crashed anchor dir (only if it's empty)
$crashedDir = "outputs\ita\anchor_snapshots\anchor_2018-07-31"
if (Test-Path $crashedDir) {
    $items = Get-ChildItem $crashedDir -Recurse -ErrorAction SilentlyContinue
    if (-not $items) {
        Remove-Item $crashedDir -Recurse -Force
        Write-Host "  Removed empty crashed dir: anchor_2018-07-31"
    }
}

$ITA_DATES = "2016-12-30,2017-01-31,2017-02-28,2017-03-31,2017-04-28,2017-05-31,2017-06-30,2017-07-31,2017-08-31,2017-09-29,2017-10-31,2017-11-30,2017-12-29,2018-01-31,2018-02-28,2018-03-29,2018-04-30,2018-05-31,2018-06-29,2018-07-31,2018-08-31,2018-09-28,2018-10-31,2018-11-30,2018-12-31,2019-01-31,2019-02-28,2019-03-29,2019-04-30,2019-05-31,2019-06-28,2019-07-31,2019-08-30,2019-09-30,2019-10-31,2019-11-29,2019-12-31,2020-01-31,2020-02-28,2020-03-31,2020-04-30,2020-05-29,2020-06-30,2020-07-31,2020-08-31,2020-09-30,2020-10-30,2020-11-30,2020-12-31,2021-01-29,2021-02-26,2021-03-31,2021-04-30,2021-05-28,2021-06-30,2021-07-30,2021-08-31,2021-09-30,2021-10-29,2021-11-30,2021-12-31,2022-01-31,2022-02-28,2022-03-31,2022-04-29,2022-05-31,2022-06-30,2022-07-29,2022-08-31,2022-09-30,2022-10-31,2022-11-30,2022-12-30,2023-01-31,2023-02-28,2023-03-31,2023-04-28,2023-05-31,2023-06-30,2023-07-31,2023-08-31,2023-09-29,2023-10-31,2023-11-30,2023-12-29,2024-01-31,2024-02-29,2024-03-28,2024-04-30,2024-05-31,2024-06-28,2024-07-31,2024-08-30,2024-09-30,2024-10-31,2024-11-29,2024-12-31,2025-01-31,2025-02-28,2025-03-31,2025-04-30,2025-05-30,2025-06-30,2025-07-31,2025-08-29,2025-09-30,2025-10-31,2025-11-28,2025-12-31,2026-01-30,2026-02-27"

python strategies\automation\run_objective1_anchor_date_multi_horizon_evaluation.py `
    --anchor-dates $ITA_DATES `
    --data-csv "C:/Users/joonc/my_github/quant-trading-system/data/ita_us_d.csv" `
    --anchor-output-root outputs/ita/anchor_snapshots `
    --top-n 20 `
    --n-jobs -1 `
    --reuse-existing-optimization-snapshots 2>&1 | Tee-Object outputs\anchor_run_ita_resume.log

if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] ITA step failed" -ForegroundColor Red; exit 1 }
Write-Host "[STEP 1] ITA done." -ForegroundColor Green


# ============================================================
# STEP 2: VRT - all 81 anchors (fresh, 2019-07-31 to 2026-03-31)
# ============================================================
Write-Host "`n[STEP 2] VRT anchors (81 fresh anchors)" -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path "outputs\vrt\anchor_snapshots" | Out-Null

$VRT_DATES = "2019-07-31,2019-08-30,2019-09-30,2019-10-31,2019-11-29,2019-12-31,2020-01-31,2020-02-28,2020-03-31,2020-04-30,2020-05-29,2020-06-30,2020-07-31,2020-08-31,2020-09-30,2020-10-30,2020-11-30,2020-12-31,2021-01-29,2021-02-26,2021-03-31,2021-04-30,2021-05-31,2021-06-30,2021-07-30,2021-08-31,2021-09-30,2021-10-29,2021-11-30,2021-12-31,2022-01-31,2022-02-28,2022-03-31,2022-04-29,2022-05-31,2022-06-30,2022-07-29,2022-08-31,2022-09-30,2022-10-31,2022-11-30,2022-12-30,2023-01-31,2023-02-28,2023-03-31,2023-04-28,2023-05-31,2023-06-30,2023-07-31,2023-08-31,2023-09-29,2023-10-31,2023-11-30,2023-12-29,2024-01-31,2024-02-29,2024-03-29,2024-04-30,2024-05-31,2024-06-28,2024-07-31,2024-08-30,2024-09-30,2024-10-31,2024-11-29,2024-12-31,2025-01-31,2025-02-28,2025-03-31,2025-04-30,2025-05-30,2025-06-30,2025-07-31,2025-08-29,2025-09-30,2025-10-31,2025-11-28,2025-12-31,2026-01-30,2026-02-27,2026-03-31"

python strategies\automation\run_objective1_anchor_date_multi_horizon_evaluation.py `
    --anchor-dates $VRT_DATES `
    --data-csv "C:/Users/joonc/my_github/quant-trading-system/data/vrt_us_d.csv" `
    --anchor-output-root outputs/vrt/anchor_snapshots `
    --top-n 20 `
    --n-jobs -1 2>&1 | Tee-Object outputs\anchor_run_vrt.log

if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] VRT step failed" -ForegroundColor Red; exit 1 }
Write-Host "[STEP 2] VRT done." -ForegroundColor Green


Write-Host "`n============================================================"
Write-Host " ALL STEPS COMPLETE - $(Get-Date)"
Write-Host "  GLD log : outputs\anchor_run_gld_2026_remaining.log"
Write-Host "  ITA log : outputs\anchor_run_ita_resume.log"
Write-Host "  VRT log : outputs\anchor_run_vrt.log"
Write-Host "============================================================"
