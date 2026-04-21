#!/usr/bin/env bash
# Full backtest suite: Obj2 + Baseline B + Baseline A
# Runs all years (2020-2024), hold days (130, 45), update intervals (1M/2M/3M/6M)
set -e
cd "$(dirname "$0")"

YEARS=("2020" "2021" "2022" "2023" "2024")

echo "========================================"
echo "STAGE C: Objective 2 (ML-Guided)"
echo "========================================"

for YEAR in "${YEARS[@]}"; do
  START="${YEAR}-01-01"
  END="${YEAR}-12-31"

  for INTERVAL in 1 2 3 6; do
    # h130
    echo "[Obj2] ${YEAR} ${INTERVAL}M h130"
    /c/Users/joonc/anaconda3/python.exe run_objective2_monthly_update_tranche_backtest.py \
      --evaluation-start-date "$START" --evaluation-end-date "$END" \
      --hold-days 130 --update-interval-months "$INTERVAL" \
      --tag "${YEAR}_${INTERVAL}m_h130"

    # h45 (1M only for core comparison; all intervals for full analysis)
    echo "[Obj2] ${YEAR} ${INTERVAL}M h45"
    /c/Users/joonc/anaconda3/python.exe run_objective2_monthly_update_tranche_backtest.py \
      --evaluation-start-date "$START" --evaluation-end-date "$END" \
      --hold-days 45 --update-interval-months "$INTERVAL" \
      --tag "${YEAR}_${INTERVAL}m_h45"
  done
done

echo "========================================"
echo "STAGE B: Baseline Ensemble (Obj1 Combination)"
echo "========================================"

for YEAR in "${YEARS[@]}"; do
  START="${YEAR}-01-01"
  END="${YEAR}-12-31"

  for INTERVAL in 1 2 3 6; do
    echo "[Baseline B] ${YEAR} ${INTERVAL}M h130"
    /c/Users/joonc/anaconda3/python.exe run_objective1_combination_tranche_backtest.py \
      --evaluation-start-date "$START" --evaluation-end-date "$END" \
      --hold-days 130 --update-interval-months "$INTERVAL" \
      --tag "${YEAR}_${INTERVAL}m_h130"

    echo "[Baseline B] ${YEAR} ${INTERVAL}M h45"
    /c/Users/joonc/anaconda3/python.exe run_objective1_combination_tranche_backtest.py \
      --evaluation-start-date "$START" --evaluation-end-date "$END" \
      --hold-days 45 --update-interval-months "$INTERVAL" \
      --tag "${YEAR}_${INTERVAL}m_h45"
  done
done

echo "========================================"
echo "STAGE A: Baseline Single Strategy"
echo "========================================"

STRATEGIES=("best" "adaptive_band" "ma_crossover" "adaptive_volatility_band" "fear_greed_candle_volume")

for YEAR in "${YEARS[@]}"; do
  START="${YEAR}-01-01"
  END="${YEAR}-12-31"

  for STRATEGY in "${STRATEGIES[@]}"; do
    echo "[Baseline A] ${YEAR} 1M h130 strategy=${STRATEGY}"
    /c/Users/joonc/anaconda3/python.exe run_objective1_single_strategy_tranche_backtest.py \
      --evaluation-start-date "$START" --evaluation-end-date "$END" \
      --hold-days 130 --update-interval-months 1 \
      --strategy-key "$STRATEGY" \
      --tag "${YEAR}_1m_h130_${STRATEGY}"

    echo "[Baseline A] ${YEAR} 1M h45 strategy=${STRATEGY}"
    /c/Users/joonc/anaconda3/python.exe run_objective1_single_strategy_tranche_backtest.py \
      --evaluation-start-date "$START" --evaluation-end-date "$END" \
      --hold-days 45 --update-interval-months 1 \
      --strategy-key "$STRATEGY" \
      --tag "${YEAR}_1m_h45_${STRATEGY}"
  done
done

echo "========================================"
echo "ALL BACKTESTS COMPLETE"
echo "========================================"
