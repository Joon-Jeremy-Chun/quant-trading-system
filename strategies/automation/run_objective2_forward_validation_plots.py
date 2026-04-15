from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_ALL_MODELS_CSV = (
    REPO_ROOT
    / "outputs"
    / "objective2_expanded_strategy_forward_validation"
    / "expanded_strategy_forward_validation_all_models_forward_2024_to_2025.csv"
)
DEFAULT_SELECTED_CSV = (
    REPO_ROOT
    / "outputs"
    / "objective2_expanded_strategy_forward_validation"
    / "expanded_strategy_forward_validation_selected_models_forward_2024_to_2025.csv"
)
DEFAULT_OUT_DIR = REPO_ROOT / "figures" / "objective2_forward_validation"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate plots for Objective 2 forward-validation results.")
    parser.add_argument("--all-models-csv", type=str, default=str(DEFAULT_ALL_MODELS_CSV), help="Path to all-models forward-validation CSV.")
    parser.add_argument("--selected-csv", type=str, default=str(DEFAULT_SELECTED_CSV), help="Path to selected-models forward-validation CSV.")
    parser.add_argument("--tag", type=str, default=None, help="Optional tag added to figure filenames.")
    return parser.parse_args()


def maybe_tagged_path(base_dir: Path, stem: str, tag: str | None) -> Path:
    if tag:
        return base_dir / f"{stem}_{tag}.png"
    return base_dir / f"{stem}.png"


def main() -> None:
    args = parse_args()
    all_models_path = Path(args.all_models_csv)
    selected_path = Path(args.selected_csv)
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    all_df = pd.read_csv(all_models_path)
    selected_df = pd.read_csv(selected_path).sort_values("target_horizon_days").reset_index(drop=True)

    # 1. Selected model: selection vs evaluation correlation
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(selected_df["target_horizon_days"], selected_df["selection_correlation"], label="Selection Corr", linewidth=2)
    ax.plot(selected_df["target_horizon_days"], selected_df["evaluation_correlation"], label="Evaluation Corr", linewidth=2)
    best_idx = selected_df["evaluation_correlation"].idxmax()
    best_row = selected_df.loc[best_idx]
    ax.scatter([best_row["target_horizon_days"]], [best_row["evaluation_correlation"]], color="red", zorder=5)
    ax.annotate(
        f"Best eval: h={int(best_row['target_horizon_days'])}, corr={best_row['evaluation_correlation']:.3f}",
        (best_row["target_horizon_days"], best_row["evaluation_correlation"]),
        xytext=(10, 10),
        textcoords="offset points",
    )
    ax.set_title("Selected Model Correlation by Horizon")
    ax.set_xlabel("Target Horizon (days)")
    ax.set_ylabel("Correlation")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(maybe_tagged_path(out_dir, "selected_model_correlation_by_horizon", args.tag), dpi=180)
    plt.close(fig)

    # 2. Selected model: directional accuracy and long-short return
    fig, axes = plt.subplots(2, 1, figsize=(11, 9), sharex=True)
    axes[0].plot(selected_df["target_horizon_days"], selected_df["selection_directional_accuracy"], label="Selection DirAcc", linewidth=2)
    axes[0].plot(selected_df["target_horizon_days"], selected_df["evaluation_directional_accuracy"], label="Evaluation DirAcc", linewidth=2)
    axes[0].set_ylabel("Directional Accuracy")
    axes[0].set_title("Selected Model Directional Accuracy by Horizon")
    axes[0].grid(alpha=0.3)
    axes[0].legend()

    axes[1].plot(selected_df["target_horizon_days"], selected_df["selection_long_short_strategy_return"], label="Selection LS Return", linewidth=2)
    axes[1].plot(selected_df["target_horizon_days"], selected_df["evaluation_long_short_strategy_return"], label="Evaluation LS Return", linewidth=2)
    axes[1].set_xlabel("Target Horizon (days)")
    axes[1].set_ylabel("Long-Short Strategy Return")
    axes[1].grid(alpha=0.3)
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(maybe_tagged_path(out_dir, "selected_model_accuracy_and_lsreturn_by_horizon", args.tag), dpi=180)
    plt.close(fig)

    # 3. Evaluation correlation heatmap across models and horizons
    pivot = all_df.pivot(index="target_horizon_days", columns="model_name", values="evaluation_correlation").sort_index()
    fig, ax = plt.subplots(figsize=(9, 10))
    im = ax.imshow(pivot.to_numpy(), aspect="auto", origin="lower", cmap="viridis")
    ax.set_title("Evaluation Correlation Heatmap by Horizon and Model")
    ax.set_xlabel("Model")
    ax.set_ylabel("Target Horizon (days)")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=30, ha="right")
    y_positions = list(range(0, len(pivot.index), max(1, len(pivot.index) // 10)))
    ax.set_yticks(y_positions)
    ax.set_yticklabels([str(int(pivot.index[i])) for i in y_positions])
    fig.colorbar(im, ax=ax, label="Evaluation Correlation")
    fig.tight_layout()
    fig.savefig(maybe_tagged_path(out_dir, "evaluation_correlation_heatmap", args.tag), dpi=180)
    plt.close(fig)

    # 4. Information / CV criteria if available
    optional_cols = [col for col in ["selection_aic", "selection_bic", "selection_cv_mse"] if col in selected_df.columns]
    if optional_cols:
        fig, axes = plt.subplots(len(optional_cols), 1, figsize=(11, 3.5 * len(optional_cols)), sharex=True)
        if len(optional_cols) == 1:
            axes = [axes]
        for ax, col in zip(axes, optional_cols):
            ax.plot(selected_df["target_horizon_days"], selected_df[col], linewidth=2)
            ax.set_title(f"{col} by Horizon")
            ax.set_ylabel(col)
            ax.grid(alpha=0.3)
        axes[-1].set_xlabel("Target Horizon (days)")
        fig.tight_layout()
        fig.savefig(maybe_tagged_path(out_dir, "selection_criteria_curves", args.tag), dpi=180)
        plt.close(fig)

    print(f"[OK] Saved figures in: {out_dir}")


if __name__ == "__main__":
    main()
