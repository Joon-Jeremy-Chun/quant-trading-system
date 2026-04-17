from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_INPUT_DIR = REPO_ROOT / "outputs" / "objective2_monthly_update_tranche_backtest"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "objective2_block_behavior_analysis"
DEFAULT_FIGURE_DIR = REPO_ROOT / "figures" / "objective2_block_behavior"

TAG_RE = re.compile(
    r"monthly_update_tranche_backtest_summary_"
    r"(?P<update_prefix>monthly_update|bimonthly_update|quarterly_update|semiannual_update)_"
    r"(?P<year>\d{4})_h(?P<hold_days>\d+)\.json$"
)

UPDATE_LABELS = {
    "monthly_update": "1M",
    "bimonthly_update": "2M",
    "quarterly_update": "3M",
    "semiannual_update": "6M",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze block-level behavior of Objective 2 tranche backtests."
    )
    parser.add_argument("--input-dir", type=str, default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--figure-dir", type=str, default=str(DEFAULT_FIGURE_DIR))
    parser.add_argument("--block-days", type=str, default="45,130")
    parser.add_argument("--tag", type=str, default="2026-04-16")
    return parser.parse_args()


def parse_block_days(raw: str) -> list[int]:
    values = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        values.append(int(token))
    values = sorted(set(values))
    if not values:
        raise ValueError("At least one block size must be provided.")
    return values


def discover_runs(input_dir: Path) -> list[dict]:
    runs: list[dict] = []
    for path in input_dir.glob("monthly_update_tranche_backtest_summary_*.json"):
        match = TAG_RE.match(path.name)
        if not match:
            continue
        update_prefix = match.group("update_prefix")
        year = int(match.group("year"))
        hold_days = int(match.group("hold_days"))
        tag_stub = f"{update_prefix}_{year}_h{hold_days}"
        runs.append(
            {
                "summary_path": path,
                "daily_path": input_dir / f"monthly_update_tranche_backtest_daily_signals_{tag_stub}.csv",
                "equity_path": input_dir / f"monthly_update_tranche_backtest_equity_curve_{tag_stub}.csv",
                "update_prefix": update_prefix,
                "update_label": UPDATE_LABELS[update_prefix],
                "year": year,
                "hold_days": hold_days,
                "tag_stub": tag_stub,
            }
        )
    runs = sorted(runs, key=lambda x: (x["hold_days"], x["year"], x["update_prefix"]))
    if not runs:
        raise FileNotFoundError(f"No matching summary files found under {input_dir}")
    return runs


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def build_block_rows_for_run(run: dict, block_days_list: list[int]) -> tuple[list[dict], dict]:
    summary = load_json(run["summary_path"])
    daily_df = pd.read_csv(run["daily_path"], parse_dates=["Date"])
    equity_df = pd.read_csv(run["equity_path"], parse_dates=["Date"])

    df = daily_df.merge(
        equity_df[["Date", "gross_exposure", "net_equity"]],
        on="Date",
        how="inner",
        suffixes=("", "_equity"),
    ).sort_values("Date").reset_index(drop=True)

    overall_exposure = float(summary["average_gross_exposure_fraction"])
    overall_return = float(summary["strategy_return"])
    buy_hold_return = float(summary["buy_hold_return"])
    overall_efficiency = overall_return / overall_exposure if overall_exposure > 0 else np.nan

    run_level = {
        "year": run["year"],
        "hold_days": run["hold_days"],
        "update_label": run["update_label"],
        "buy_hold_return": buy_hold_return,
        "strategy_return": overall_return,
        "average_exposure": overall_exposure,
        "hundred_pct_equivalent_return": overall_efficiency,
        "beats_buy_hold": overall_return > buy_hold_return,
        "beats_buy_hold_efficiency_proxy": overall_efficiency > buy_hold_return,
    }

    block_rows: list[dict] = []
    for block_days in block_days_list:
        for start_idx in range(0, len(df), block_days):
            block = df.iloc[start_idx : start_idx + block_days].copy()
            if len(block) < 2:
                continue
            start_price = float(block["price"].iloc[0])
            end_price = float(block["price"].iloc[-1])
            start_equity = float(block["net_equity"].iloc[0])
            end_equity = float(block["net_equity"].iloc[-1])
            bh_return = end_price / start_price - 1.0
            strat_return = end_equity / start_equity - 1.0
            avg_exposure = float((block["gross_exposure"] / block["net_equity"]).mean())
            avg_weight = float(block["portfolio_weight"].mean())
            block_rows.append(
                {
                    "year": run["year"],
                    "hold_days": run["hold_days"],
                    "update_label": run["update_label"],
                    "block_days": block_days,
                    "block_index": start_idx // block_days + 1,
                    "block_start": block["Date"].iloc[0].strftime("%Y-%m-%d"),
                    "block_end": block["Date"].iloc[-1].strftime("%Y-%m-%d"),
                    "rows_in_block": len(block),
                    "block_buy_hold_return": bh_return,
                    "block_strategy_return": strat_return,
                    "block_avg_exposure": avg_exposure,
                    "block_avg_weight": avg_weight,
                    "block_efficiency_proxy": strat_return / avg_exposure if avg_exposure > 0 else np.nan,
                }
            )

    return block_rows, run_level


def build_run_behavior_summary(block_df: pd.DataFrame, run_df: pd.DataFrame) -> pd.DataFrame:
    summary_rows: list[dict] = []
    group_cols = ["year", "hold_days", "update_label", "block_days"]
    for keys, grp in block_df.groupby(group_cols):
        negative = grp[grp["block_buy_hold_return"] < 0]
        positive = grp[grp["block_buy_hold_return"] > 0]
        neg_exp = float(negative["block_avg_exposure"].mean()) if not negative.empty else np.nan
        pos_exp = float(positive["block_avg_exposure"].mean()) if not positive.empty else np.nan
        neg_strat = float(negative["block_strategy_return"].mean()) if not negative.empty else np.nan
        pos_strat = float(positive["block_strategy_return"].mean()) if not positive.empty else np.nan
        summary_rows.append(
            {
                "year": keys[0],
                "hold_days": keys[1],
                "update_label": keys[2],
                "block_days": keys[3],
                "negative_bh_blocks": int(len(negative)),
                "positive_bh_blocks": int(len(positive)),
                "avg_exposure_when_bh_negative": neg_exp,
                "avg_exposure_when_bh_positive": pos_exp,
                "exposure_gap_positive_minus_negative": pos_exp - neg_exp if pd.notna(pos_exp) and pd.notna(neg_exp) else np.nan,
                "avg_strategy_return_when_bh_negative": neg_strat,
                "avg_strategy_return_when_bh_positive": pos_strat,
                "strategy_return_gap_positive_minus_negative": pos_strat - neg_strat if pd.notna(pos_strat) and pd.notna(neg_strat) else np.nan,
                "corr_block_bh_vs_exposure": float(grp["block_buy_hold_return"].corr(grp["block_avg_exposure"]))
                if len(grp) >= 2
                else np.nan,
            }
        )
    summary_df = pd.DataFrame(summary_rows)
    return summary_df.merge(run_df, on=["year", "hold_days", "update_label"], how="left")


def plot_exposure_gap(behavior_df: pd.DataFrame, figure_path: Path) -> None:
    block_45 = behavior_df[behavior_df["block_days"] == 45].copy()
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    for ax, hold_days in zip(axes, sorted(block_45["hold_days"].unique())):
        subset = block_45[block_45["hold_days"] == hold_days].copy()
        subset["label"] = subset["year"].astype(str) + "-" + subset["update_label"]
        ax.bar(subset["label"], subset["exposure_gap_positive_minus_negative"] * 100.0)
        ax.set_title(f"Exposure Gap by Run (block=45, hold={hold_days})")
        ax.set_ylabel("Positive-BH Exposure minus Negative-BH Exposure (%)")
        ax.tick_params(axis="x", rotation=60)
        ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_block_scatter(block_df: pd.DataFrame, figure_path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharex=False, sharey=False)
    for ax, hold_days in zip(axes, sorted(block_df["hold_days"].unique())):
        subset = block_df[(block_df["hold_days"] == hold_days) & (block_df["block_days"] == hold_days)]
        for update_label in sorted(subset["update_label"].unique(), key=lambda x: ["1M", "2M", "3M", "6M"].index(x)):
            grp = subset[subset["update_label"] == update_label]
            ax.scatter(
                grp["block_buy_hold_return"] * 100.0,
                grp["block_avg_exposure"] * 100.0,
                label=update_label,
                alpha=0.7,
            )
        ax.axvline(0.0, color="gray", linestyle="--", linewidth=1)
        ax.set_title(f"Block B&H vs Exposure (hold={hold_days}, block={hold_days})")
        ax.set_xlabel("Block Buy & Hold Return (%)")
        ax.set_ylabel("Average Exposure (%)")
        ax.grid(True, alpha=0.3)
    axes[1].legend(title="Update")
    fig.tight_layout()
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    out_dir = Path(args.out_dir)
    figure_dir = Path(args.figure_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    block_days_list = parse_block_days(args.block_days)
    runs = discover_runs(input_dir)

    all_block_rows: list[dict] = []
    all_run_rows: list[dict] = []
    for run in runs:
        block_rows, run_row = build_block_rows_for_run(run, block_days_list)
        all_block_rows.extend(block_rows)
        all_run_rows.append(run_row)

    block_df = pd.DataFrame(all_block_rows)
    run_df = pd.DataFrame(all_run_rows)
    behavior_df = build_run_behavior_summary(block_df, run_df)

    run_csv = out_dir / f"objective2_run_level_summary_{args.tag}.csv"
    block_csv = out_dir / f"objective2_block_level_summary_{args.tag}.csv"
    behavior_csv = out_dir / f"objective2_block_behavior_summary_{args.tag}.csv"
    run_df.to_csv(run_csv, index=False)
    block_df.to_csv(block_csv, index=False)
    behavior_df.to_csv(behavior_csv, index=False)

    plot_exposure_gap(
        behavior_df=behavior_df,
        figure_path=figure_dir / f"block_exposure_gap_45dayblocks_{args.tag}.png",
    )
    plot_block_scatter(
        block_df=block_df,
        figure_path=figure_dir / f"block_bh_vs_exposure_scatter_{args.tag}.png",
    )

    print("=" * 80)
    print("OBJECTIVE 2 BLOCK BEHAVIOR ANALYSIS")
    print("=" * 80)
    print(f"[OK] Saved run summary:      {run_csv}")
    print(f"[OK] Saved block summary:    {block_csv}")
    print(f"[OK] Saved behavior summary: {behavior_csv}")
    print(f"[OK] Saved figure:           {figure_dir / f'block_exposure_gap_45dayblocks_{args.tag}.png'}")
    print(f"[OK] Saved figure:           {figure_dir / f'block_bh_vs_exposure_scatter_{args.tag}.png'}")


if __name__ == "__main__":
    main()
