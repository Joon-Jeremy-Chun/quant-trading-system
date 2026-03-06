# code_02_build_bands_and_plots.py
# Load saved gold price data, normalize, compute MA + asymmetric sigma bands,
# add break indicators, and save 4 clean plots to ./figures/

from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# PARAMETERS (Edit only this block to change the entire pipeline)
# ============================================================

CSV_PATH = Path("./data/gold_prices.csv")   # CSV file saved by code_01
FIG_DIR  = Path("./figures")                # Directory to save figures

START_DATE = "2018-01-01"   # Analysis start date
END_DATE   = "2025-12-31"   # Analysis end date (inclusive)

NORMALIZE_MODE = "zscore"   # "zscore" | "minmax" | "none"

MA_WINDOW = 20              # Moving average window size
UPPER_K = 2.0               # Upper band sigma multiplier
LOWER_K = 1.2               # Lower band sigma multiplier (asymmetric allowed)

# Zoom plot range (optional)
ZOOM_START = "2018-06-01"
ZOOM_END   = "2020-06-01"

# Output filenames (4 plots)
FULL_NO_MARKERS = "gold_full_nomarkers.png"
FULL_WITH_MARKS = "gold_full_withmarks.png"
ZOOM_NO_MARKERS = "gold_zoom_nomarkers.png"
ZOOM_WITH_MARKS = "gold_zoom_withmarks.png"

SHOW_PLOTS = False          # True if you want figures to pop up in Spyder

# ============================================================


def ensure_figures_dir(fig_dir: Path) -> None:
    fig_dir.mkdir(parents=True, exist_ok=True)


def load_data(csv_path: Path, start_date: str, end_date: str) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)

    required = {"Date", "Price"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing columns: {missing}. Expected at least: {sorted(required)}")

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.dropna(subset=["Price"]).sort_values("Date").reset_index(drop=True)

    # Filter by date range (inclusive)
    s = pd.to_datetime(start_date)
    e = pd.to_datetime(end_date)
    df = df[(df["Date"] >= s) & (df["Date"] <= e)].reset_index(drop=True)

    if df.empty:
        raise ValueError(f"No data after filtering dates: {start_date} ~ {end_date}")

    return df


def add_features(df: pd.DataFrame, ma_window: int, upper_k: float, lower_k: float, normalize_mode: str) -> pd.DataFrame:
    out = df.copy()
    x = out["Price"].astype(float).values

    # Normalization
    if normalize_mode == "zscore":
        mu = np.nanmean(x)
        sd = np.nanstd(x, ddof=0)
        if sd == 0:
            raise ValueError("Standard deviation is 0; cannot z-score normalize.")
        out["Price_Norm"] = (out["Price"] - mu) / sd
    elif normalize_mode == "minmax":
        xmin, xmax = np.nanmin(x), np.nanmax(x)
        if xmax == xmin:
            raise ValueError("All prices identical; cannot min-max normalize.")
        out["Price_Norm"] = (out["Price"] - xmin) / (xmax - xmin)
    elif normalize_mode == "none":
        out["Price_Norm"] = out["Price"]
    else:
        raise ValueError("normalize_mode must be one of: zscore, minmax, none")

    # Rolling stats
    out["MA"] = out["Price_Norm"].rolling(window=ma_window, min_periods=ma_window).mean()
    out["Sigma"] = out["Price_Norm"].rolling(window=ma_window, min_periods=ma_window).std(ddof=0)

    # Asymmetric bands
    out["Upper"] = out["MA"] + upper_k * out["Sigma"]
    out["Lower"] = out["MA"] - lower_k * out["Sigma"]

    # Break indicators (0/1)
    out["UpperBreak"] = (out["Price_Norm"] > out["Upper"]).astype(int)
    out["LowerBreak"] = (out["Price_Norm"] < out["Lower"]).astype(int)

    return out


def plot_series(
    df: pd.DataFrame,
    fig_path: Path,
    title: str,
    add_marks: bool = False,
    show: bool = False,
) -> Path:
    # Bigger canvas + axes API helps avoid clipping
    fig, ax = plt.subplots(figsize=(12, 7))

    ax.plot(df["Date"], df["Price_Norm"], label="Normalized Price")
    ax.plot(df["Date"], df["MA"], label="MA (center)")
    ax.plot(df["Date"], df["Upper"], label="Upper band")
    ax.plot(df["Date"], df["Lower"], label="Lower band")

    if add_marks:
        upper_idx = df["UpperBreak"] == 1
        lower_idx = df["LowerBreak"] == 1

        # ▼ upper break, ▲ lower break (cleaner than arrows)
        ax.scatter(df.loc[upper_idx, "Date"], df.loc[upper_idx, "Price_Norm"],
                   marker="v", s=50, label="UpperBreak", zorder=6)
        ax.scatter(df.loc[lower_idx, "Date"], df.loc[lower_idx, "Price_Norm"],
                   marker="^", s=50, label="LowerBreak", zorder=6)

    # Use a 2-line title to keep it readable and prevent clipping
    ax.set_title(title, fontsize=12, pad=10)
    ax.set_xlabel("Date")
    ax.set_ylabel("Normalized Price")
    ax.legend()

    # Leave room for the title, then save with tight bounding box (prevents truncation)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(fig_path, dpi=200, bbox_inches="tight", pad_inches=0.2)

    if show:
        plt.show()

    plt.close(fig)
    return fig_path


def main():
    ensure_figures_dir(FIG_DIR)

    try:
        df = load_data(CSV_PATH, START_DATE, END_DATE)
        df_feat = add_features(df, MA_WINDOW, UPPER_K, LOWER_K, NORMALIZE_MODE)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    # Drop early rows where rolling stats are NaN
    df_plot = df_feat.dropna(subset=["MA", "Sigma", "Upper", "Lower"]).copy()
    if df_plot.empty:
        print("[ERROR] Not enough data after rolling window. Try smaller MA_WINDOW or more data.",
              file=sys.stderr)
        sys.exit(1)

    # Title (2 lines)
    title_base = (
        f"Gold Bands | {START_DATE}~{END_DATE} | normalize={NORMALIZE_MODE}\n"
        f"MA={MA_WINDOW} | upper_k={UPPER_K} | lower_k={LOWER_K}"
    )

    # -----------------------------
    # 4 plots
    # -----------------------------
    p1 = plot_series(df_plot, FIG_DIR / FULL_NO_MARKERS, title_base + "\nFULL", add_marks=False, show=SHOW_PLOTS)
    print(f"[OK] Saved: {p1.resolve()}")

    p2 = plot_series(df_plot, FIG_DIR / FULL_WITH_MARKS, title_base + "\nFULL + MARKERS", add_marks=True, show=SHOW_PLOTS)
    print(f"[OK] Saved: {p2.resolve()}")

    if ZOOM_START and ZOOM_END:
        z0 = pd.to_datetime(ZOOM_START)
        z1 = pd.to_datetime(ZOOM_END)
        zoom_df = df_plot[(df_plot["Date"] >= z0) & (df_plot["Date"] <= z1)].copy()

        if zoom_df.empty:
            print(f"[WARN] Zoom range empty: {ZOOM_START} ~ {ZOOM_END}", file=sys.stderr)
        else:
            p3 = plot_series(
                zoom_df,
                FIG_DIR / ZOOM_NO_MARKERS,
                title_base + f"\nZOOM {ZOOM_START}~{ZOOM_END}",
                add_marks=False,
                show=SHOW_PLOTS
            )
            print(f"[OK] Saved: {p3.resolve()}")

            p4 = plot_series(
                zoom_df,
                FIG_DIR / ZOOM_WITH_MARKS,
                title_base + f"\nZOOM {ZOOM_START}~{ZOOM_END} + MARKERS",
                add_marks=True,
                show=SHOW_PLOTS
            )
            print(f"[OK] Saved: {p4.resolve()}")

    # Save features CSV
    out_features = CSV_PATH.with_name(CSV_PATH.stem + "_features.csv")
    df_feat.to_csv(out_features, index=False)
    print(f"[OK] Saved features CSV: {out_features.resolve()}")

    # Debug prints (inside main so df_feat exists)
    print(df_feat[["Date", "Price_Norm", "MA", "Sigma", "Upper", "Lower", "UpperBreak", "LowerBreak"]].tail(10))
    print("UpperBreak count:", int(df_feat["UpperBreak"].sum()))
    print("LowerBreak count:", int(df_feat["LowerBreak"].sum()))


if __name__ == "__main__":
    main()