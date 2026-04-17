from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_SUMMARY_ROOT = REPO_ROOT / "outputs" / "objective2_monthly_update_tranche_backtest"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "objective2_update_frequency_comparison"
DEFAULT_FIGURE_DIR = REPO_ROOT / "figures" / "objective2_update_frequency"

UPDATE_CONFIG = [
    (1, "1M", "monthly_update"),
    (2, "2M", "bimonthly_update"),
    (3, "3M", "quarterly_update"),
    (6, "6M", "semiannual_update"),
]
HOLDS = [45, 130]
YEARS = [2020, 2021, 2022, 2023, 2024]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a combined update-frequency summary for Objective 2 hold-based backtests."
    )
    parser.add_argument("--summary-root", type=str, default=str(DEFAULT_SUMMARY_ROOT))
    parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--figure-dir", type=str, default=str(DEFAULT_FIGURE_DIR))
    parser.add_argument("--tag", type=str, default="2026-04-16")
    return parser.parse_args()


def summary_path(summary_root: Path, prefix: str, year: int, hold_days: int) -> Path:
    return summary_root / f"monthly_update_tranche_backtest_summary_{prefix}_{year}_h{hold_days}.json"


def load_summary(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def build_long_rows(summary_root: Path) -> pd.DataFrame:
    rows: list[dict] = []
    for hold_days in HOLDS:
        for year in YEARS:
            buy_hold = None
            for update_interval_months, update_label, prefix in UPDATE_CONFIG:
                path = summary_path(summary_root, prefix, year, hold_days)
                if not path.exists():
                    raise FileNotFoundError(f"Missing summary JSON: {path}")
                payload = load_summary(path)
                if buy_hold is None:
                    buy_hold = float(payload["buy_hold_return"])
                strategy_return = float(payload["strategy_return"])
                exposure = float(payload["average_gross_exposure_fraction"])
                eff = strategy_return / exposure if exposure > 0 else np.nan
                rows.append(
                    {
                        "year": year,
                        "hold_days": hold_days,
                        "update_interval_months": update_interval_months,
                        "update_label": update_label,
                        "buy_hold_return": buy_hold,
                        "strategy_return": strategy_return,
                        "average_exposure": exposure,
                        "hundred_pct_equivalent_return": eff,
                        "summary_path": str(path),
                    }
                )
    return pd.DataFrame(rows)


def format_pct(value: float) -> str:
    if pd.isna(value):
        return "NA"
    return f"{value * 100:.4f}%"


def build_wide_table(long_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for hold_days in HOLDS:
        for year in YEARS:
            subset = long_df[(long_df["hold_days"] == hold_days) & (long_df["year"] == year)].sort_values(
                "update_interval_months"
            )
            if subset.empty:
                continue
            row = {
                "Hold Days": hold_days,
                "Year": year,
                "Buy & Hold": format_pct(float(subset["buy_hold_return"].iloc[0])),
            }
            for _, rec in subset.iterrows():
                label = rec["update_label"]
                row[f"{label} Return"] = format_pct(float(rec["strategy_return"]))
                row[f"{label} Exposure"] = format_pct(float(rec["average_exposure"]))
                row[f"{label} 100%-Eq"] = format_pct(float(rec["hundred_pct_equivalent_return"]))
            rows.append(row)
    return pd.DataFrame(rows)


def plot_metric_by_hold(
    long_df: pd.DataFrame,
    metric_col: str,
    y_label: str,
    title: str,
    figure_path: Path,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharex=True)
    for ax, hold_days in zip(axes, HOLDS):
        subset = long_df[long_df["hold_days"] == hold_days]
        for year in YEARS:
            year_df = subset[subset["year"] == year].sort_values("update_interval_months")
            ax.plot(
                year_df["update_interval_months"],
                year_df[metric_col] * 100.0,
                marker="o",
                linewidth=2,
                label=str(year),
            )
        ax.set_title(f"Hold = {hold_days} days")
        ax.set_xlabel("Update Interval (months)")
        ax.set_ylabel(y_label)
        ax.grid(True, alpha=0.3)
        ax.set_xticks([cfg[0] for cfg in UPDATE_CONFIG])
    axes[1].legend(title="Year", loc="best")
    fig.suptitle(title)
    fig.tight_layout()
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    summary_root = Path(args.summary_root)
    out_dir = Path(args.out_dir)
    figure_dir = Path(args.figure_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    long_df = build_long_rows(summary_root)
    long_csv = out_dir / f"objective2_hold_update_frequency_long_{args.tag}.csv"
    wide_csv = out_dir / f"objective2_hold_update_frequency_wide_{args.tag}.csv"
    long_df.to_csv(long_csv, index=False)

    wide_df = build_wide_table(long_df)
    wide_df.to_csv(wide_csv, index=False)

    plot_metric_by_hold(
        long_df=long_df,
        metric_col="strategy_return",
        y_label="Strategy Return (%)",
        title="Update Frequency vs Strategy Return",
        figure_path=figure_dir / f"update_frequency_strategy_return_{args.tag}.png",
    )
    plot_metric_by_hold(
        long_df=long_df,
        metric_col="average_exposure",
        y_label="Average Exposure (%)",
        title="Update Frequency vs Average Exposure",
        figure_path=figure_dir / f"update_frequency_average_exposure_{args.tag}.png",
    )
    plot_metric_by_hold(
        long_df=long_df,
        metric_col="hundred_pct_equivalent_return",
        y_label="100%-Equivalent Return (%)",
        title="Update Frequency vs Exposure-Adjusted Proxy",
        figure_path=figure_dir / f"update_frequency_efficiency_proxy_{args.tag}.png",
    )

    print("=" * 80)
    print("OBJECTIVE 2 HOLD/UPDATE FREQUENCY SUMMARY")
    print("=" * 80)
    print(f"[OK] Saved long CSV: {long_csv}")
    print(f"[OK] Saved wide CSV: {wide_csv}")
    print(f"[OK] Saved figure:   {figure_dir / f'update_frequency_strategy_return_{args.tag}.png'}")
    print(f"[OK] Saved figure:   {figure_dir / f'update_frequency_average_exposure_{args.tag}.png'}")
    print(f"[OK] Saved figure:   {figure_dir / f'update_frequency_efficiency_proxy_{args.tag}.png'}")


if __name__ == "__main__":
    main()
