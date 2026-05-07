from __future__ import annotations

import argparse
import io
import json
import os
import smtplib
from datetime import date
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_DIR  = REPO_ROOT / "outputs" / "live"

sys.path.insert(0, str(REPO_ROOT / "strategies" / "automation"))

# Per-symbol metadata: display name, chart color, data/anchor paths.
# anchor_output_root: use models/pi_reference/<SYM> for Pi-built signals (GLD/BRK-B),
#                     or outputs/<sym>/anchor_snapshots for Windows-pushed signals (QQQ/RKLB/...).
_ASSET_META: dict[str, dict] = {
    "GLD":   {"name": "SPDR Gold ETF",            "color": "#c8a020", "data_csv": "data/gld_us_d.csv",   "anchor_output_root": "models/pi_reference/GLD"},
    "BRK-B": {"name": "Berkshire Hathaway Cl. B", "color": "#1a5276", "data_csv": "data/brkb_us_d.csv",  "anchor_output_root": "models/pi_reference/BRK-B"},
    "QQQ":   {"name": "Invesco Nasdaq-100 ETF",   "color": "#1e8449", "data_csv": "data/qqq_us_d.csv",   "anchor_output_root": "outputs/qqq/anchor_snapshots"},
    "RKLB":  {"name": "Rocket Lab USA",           "color": "#922b21", "data_csv": "data/rklb_us_d.csv",  "anchor_output_root": "outputs/rklb/anchor_snapshots"},
    "ITA":   {"name": "iShares US Aerospace & Defense", "color": "#6c3483", "data_csv": "data/ita_us_d.csv", "anchor_output_root": "outputs/ita/anchor_snapshots"},
    "VRT":   {"name": "Vertiv Holdings",          "color": "#117a65", "data_csv": "data/vrt_us_d.csv",   "anchor_output_root": "outputs/vrt/anchor_snapshots"},
}


def _load_active_assets() -> list[dict]:
    """Read active assets from active_universe.json so the report auto-tracks universe changes."""
    universe_path = REPO_ROOT / "models" / "live_assets" / "active_universe.json"
    try:
        with open(universe_path, encoding="utf-8") as f:
            symbols = [s.upper() for s in json.load(f).get("assets", [])]
    except Exception:
        symbols = ["GLD", "BRK-B", "QQQ", "RKLB"]  # fallback

    assets = []
    for sym in symbols:
        meta = _ASSET_META.get(sym)
        if meta is None:
            # Unknown symbol: use sensible defaults so the report doesn't crash
            slug = sym.lower().replace("-", "")
            meta = {"name": sym, "color": "#888888",
                    "data_csv": f"data/{slug}_us_d.csv",
                    "anchor_output_root": f"outputs/{slug}/anchor_snapshots"}
        assets.append({"symbol": sym, "slug": sym.lower().replace("-", ""), **meta})
    return assets


ASSETS = _load_active_assets()


OWNER_EMAIL = "joonchun1000@gmail.com"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send multi-asset daily HTML signal report.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test", action="store_true",
                        help="Send email only to owner (joonchun1000@gmail.com), not all recipients.")
    return parser.parse_args()


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_email_config() -> dict:
    return {
        "enabled": env_bool("EMAIL_ALERT_ENABLED", False),
        "smtp_host": os.getenv("SMTP_HOST", ""),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "smtp_username": os.getenv("SMTP_USERNAME", ""),
        "smtp_password": os.getenv("SMTP_PASSWORD", ""),
        "smtp_use_tls": env_bool("SMTP_USE_TLS", True),
        "from_email": os.getenv("ALERT_EMAIL_FROM", ""),
        "to_email": os.getenv("ALERT_EMAIL_TO", ""),
    }


def load_json(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def latest_file(pattern: str) -> Path | None:
    candidates = sorted(LIVE_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def load_activity_data(signals: dict, weights: dict) -> dict:
    """Load tranche log, past prices, and today's delta orders for the activity section."""
    horizon = int(signals.get("GLD", {}).get("target_horizon_days", 130))

    # Tranche log - rolling weight history
    log_path = LIVE_DIR / "tranche_log.csv"
    if not log_path.exists():
        return {}
    log = pd.read_csv(log_path, parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
    if log.empty:
        return {}

    # Past row: use row at -horizon, or earliest available
    past_idx  = max(0, len(log) - horizon)
    past_row  = log.iloc[past_idx]
    past_date = past_row["Date"].date()
    days_back = len(log) - 1 - past_idx  # actual trading days back in log

    past_weights: dict[str, float] = {}
    for asset in ASSETS:
        col = f"w_{asset['symbol']}"
        past_weights[asset["symbol"]] = float(past_row.get(col, 0.0))

    # Past prices - look up close price on past_date from each asset's CSV
    past_prices: dict[str, float] = {}
    for asset in ASSETS:
        try:
            df = pd.read_csv(REPO_ROOT / asset["data_csv"], parse_dates=["Date"])
            df = df.sort_values("Date")
            row = df[df["Date"].dt.date <= past_date].iloc[-1] if not df.empty else None
            past_prices[asset["symbol"]] = float(row["Close"]) if row is not None else 0.0
        except Exception:
            past_prices[asset["symbol"]] = 0.0

    # Latest delta_tranche output - today's actual orders
    delta_file = latest_file("delta_tranche_*.json")
    delta = load_json(delta_file)
    delta_orders: dict[str, dict] = {}
    for order in delta.get("delta_orders", []):
        sym = order.get("symbol", "")
        if sym:
            delta_orders[sym] = order

    capital = float(delta.get("total_capital", 10_000.0))

    return {
        "horizon":       horizon,
        "past_date":     past_date,
        "days_back":     days_back,
        "past_weights":  past_weights,
        "past_prices":   past_prices,
        "delta_orders":  delta_orders,
        "capital":       capital,
        "weights":       weights,
    }


def activity_section_html(activity: dict, signals: dict) -> str:
    if not activity:
        return ""

    horizon     = activity["horizon"]
    past_date   = activity["past_date"]
    days_back   = activity["days_back"]
    past_w      = activity["past_weights"]
    past_px     = activity["past_prices"]
    delta_ord   = activity["delta_orders"]
    capital     = activity["capital"]
    weights     = activity["weights"]

    past_label = past_date.strftime("%b %d, %Y").replace(" 0", " ") if hasattr(past_date, "strftime") else str(past_date)

    intro = (
        f"Our model is a <b>{horizon}-day forward return predictor</b>. "
        f"Each trading day, positions shift by 1/{horizon}th of the difference between "
        f"today&#39;s target weight and the weight held {horizon} trading days ago - "
        f"gradually accumulating into assets with strong signals and reducing exposure to weakening ones. "
        f"The table below shows where we stood <b>{days_back} trading days ago ({past_label})</b>, "
        f"what today&#39;s model recommends, and the incremental trade executed today."
    )

    import math

    rows_html = ""
    for asset in ASSETS:
        sym   = asset["symbol"]
        color = asset["color"]
        sig   = signals.get(sym, {})
        signal_label = sig.get("signal", "HOLD")

        pw      = past_w.get(sym, 0.0)
        pp      = past_px.get(sym, 0.0)
        tw      = weights.get(sym, 0.0)
        tod_px  = float(sig.get("close_price", 0.0))
        past_pos = pw * capital
        tod_pos  = tw * capital
        delta_dol = tod_pos - past_pos

        order = delta_ord.get(sym, {})
        side  = order.get("side", "HOLD")
        dol   = float(order.get("dollars", 0.0))
        qty   = float(order.get("qty", 0.0))
        lim   = float(order.get("limit_price", 0.0))

        # Past position cell
        past_cell = (
            f"<b>${past_pos:,.0f}</b>"
            + (f"<br><span style='color:#aaa;font-size:10px'>@ ${pp:,.2f}</span>" if pp else "")
        )

        # Today position cell
        sig_color = {"BUY": "#1a7a4a", "SELL": "#c0392b", "HOLD": "#888"}.get(signal_label, "#888")
        sig_badge = (
            f"<span style='background:{sig_color};color:white;padding:1px 6px;"
            f"border-radius:3px;font-size:10px;font-weight:bold'>{signal_label}</span>"
        )
        today_cell = (
            f"<b>${tod_pos:,.0f}</b>"
            + (f"<br><span style='color:#aaa;font-size:10px'>@ ${tod_px:,.2f}</span>" if tod_px else "")
            + f"<br>{sig_badge}"
        )

        # Δ cell
        if delta_dol > 0.5:
            delta_color, delta_text = "#1a7a4a", f"+${delta_dol:,.0f}"
        elif delta_dol < -0.5:
            delta_color, delta_text = "#c0392b", f"&#8722;${abs(delta_dol):,.0f}"
        else:
            delta_color, delta_text = "#aaa", "≈ $0"

        # Actual vs Predicted cell
        pred_ret  = float(sig.get("predicted_future_return", 0.0))
        mse       = float(sig.get("selection_mse", 0.0))
        sigma     = math.sqrt(mse) if mse > 0 else 0.0
        actual_ret = (tod_px - pp) / pp if pp > 0 and tod_px > 0 else None

        actual_str = f"{actual_ret:+.1%}" if actual_ret is not None else "—"
        actual_color = "#1a7a4a" if (actual_ret or 0) >= 0 else "#c0392b"
        pred_str  = f"{pred_ret:+.1%}"
        sigma_str = f"±{sigma:.1%}" if sigma > 0 else ""
        perf_cell = (
            f"<span style='font-size:12px;font-weight:bold;color:{actual_color}'>{actual_str}</span>"
            f"<span style='color:#bbb;font-size:10px'> actual</span><br>"
            f"<span style='font-size:11px;color:#555'>{pred_str}</span>"
            f"<span style='color:#bbb;font-size:10px'> pred {sigma_str}</span>"
        )

        # Final Trade cell
        if side == "BUY":
            trade_color = "#1a7a4a"
            trade_text  = f"<b>BUY</b> +${dol:,.2f}<br><span style='color:#aaa;font-size:10px'>{qty:.4f} sh @ ${lim:.2f}</span>"
        elif side == "SELL":
            trade_color = "#c0392b"
            trade_text  = f"<b>SELL</b> &#8722;${dol:,.2f}<br><span style='color:#aaa;font-size:10px'>{qty:.4f} sh @ ${lim:.2f}</span>"
        else:
            trade_color = "#aaa"
            trade_text  = "<b>HOLD</b><br><span style='color:#ccc;font-size:10px'>no order</span>"

        rows_html += f"""
      <tr style='border-bottom:1px solid #f0f0f0'>
        <td style='padding:8px 6px;font-weight:bold;color:{color};white-space:nowrap'>{sym}</td>
        <td style='padding:8px 6px;text-align:right;font-size:12px;color:#555;line-height:1.5'>{past_cell}</td>
        <td style='padding:8px 6px;text-align:right;font-size:12px;color:#333;line-height:1.5'>{today_cell}</td>
        <td style='padding:8px 6px;text-align:center;font-size:13px;font-weight:bold;color:{delta_color};white-space:nowrap'>{delta_text}</td>
        <td style='padding:8px 6px;text-align:right;font-size:12px;line-height:1.6'>{perf_cell}</td>
        <td style='padding:8px 6px;text-align:right;font-size:12px;color:{trade_color};white-space:nowrap;line-height:1.5'>{trade_text}</td>
      </tr>"""

    return f"""
  <!-- ACTIVITY SECTION -->
  <div style='background:white;padding:18px 24px;border-top:1px solid #eee'>
    <div style='font-size:11px;font-weight:bold;color:#555;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px'>
      Portfolio Activity &nbsp;&middot;&nbsp; {horizon}-Day Rolling Strategy
    </div>
    <p style='font-size:12px;color:#555;line-height:1.7;margin:0 0 14px 0'>{intro}</p>
    <table width='100%' cellspacing='0' style='font-size:12px;border-collapse:collapse'>
      <thead>
        <tr style='background:#f7f8fa;border-bottom:2px solid #e8e8e8'>
          <th style='padding:7px 6px;text-align:left;font-size:11px;color:#888;font-weight:600'>Asset</th>
          <th style='padding:7px 6px;text-align:right;font-size:11px;color:#888;font-weight:600'>{days_back}d Ago<br>Position</th>
          <th style='padding:7px 6px;text-align:right;font-size:11px;color:#888;font-weight:600'>Today<br>Position</th>
          <th style='padding:7px 6px;text-align:center;font-size:11px;color:#888;font-weight:600'>Δ</th>
          <th style='padding:7px 6px;text-align:right;font-size:11px;color:#888;font-weight:600'>Actual / Predicted<br><span style='font-weight:400'>(past {days_back}d vs next {horizon}d ±1σ)</span></th>
          <th style='padding:7px 6px;text-align:right;font-size:11px;color:#888;font-weight:600'>Final Trade<br><span style='font-weight:400'>(1/{horizon} tranche)</span></th>
        </tr>
      </thead>
      <tbody>{rows_html}
      </tbody>
    </table>
    <p style='font-size:11px;color:#bbb;margin:10px 0 0 0'>
      Capital base: ${capital:,.0f} &nbsp;&middot;&nbsp; Limit orders &nbsp;&middot;&nbsp; Extended hours enabled
    </p>
  </div>"""


def back_predict_weights(
    data_csv: Path,
    anchor_output_root: Path,
    anchor_date: str,
    asof_date: str,
    target_horizon_days: int = 130,
    top_n_per_family: int = 20,
    selection_criterion: str = "selection_cv_mse",
    window_months: int = 6,
) -> pd.Series | None:
    """Apply active model to past window_months of data for back-prediction weight series."""
    try:
        from run_objective2_monthly_update_tranche_backtest import fit_month_model, REPO_ROOT as _R
        asof_ts = pd.Timestamp(asof_date)
        window_start = (asof_ts - pd.DateOffset(months=window_months)).normalize()
        month_df, _ = fit_month_model(
            repo_root=_R,
            data_csv=data_csv,
            anchor_output_root=anchor_output_root,
            anchor_date=pd.Timestamp(anchor_date),
            month_start=window_start,
            month_end=asof_ts,
            target_horizon_days=target_horizon_days,
            top_n_per_family=top_n_per_family,
            selection_criterion=selection_criterion,
            scale_quantile=0.95,
        )
        return month_df.set_index("Date")["portfolio_weight"].clip(lower=0)
    except Exception as exc:
        print(f"[WARN] Back-prediction failed for {anchor_date}: {exc}")
        return None


def build_chart_png(data_csv: Path, color: str, live_start: str | None = None,
                    current_weight: float = 0.0,
                    weight_series: pd.Series | None = None) -> bytes | None:
    """Price chart + weight panel. Uses back-predicted weight_series if provided."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates

        df = pd.read_csv(data_csv, parse_dates=["Date"])
        df = df.rename(columns={"Date": "date", "Close": "close"})
        df = df.sort_values("date")
        cutoff = df["date"].max() - pd.DateOffset(months=6)
        df = df[df["date"] >= cutoff].copy()

        live_dt = pd.Timestamp(live_start) if live_start else df["date"].max()

        if weight_series is not None:
            ws = weight_series.copy()
            ws.index = pd.to_datetime(ws.index).normalize()
            df["weight"] = df["date"].map(ws).clip(lower=0).fillna(0)
        else:
            df["weight"] = df["date"].apply(lambda d: current_weight if d >= live_dt else 0.0)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5),
                                        gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
        fig.patch.set_facecolor("#f9f9f9")

        # Price
        ax1.plot(df["date"], df["close"], color=color, linewidth=1.6)
        ax1.fill_between(df["date"], df["close"], df["close"].min(), alpha=0.08, color=color)

        # Live start marker
        live_rows = df[df["date"] >= live_dt]
        if not live_rows.empty:
            ax1.axvline(x=live_dt, color="#27ae60", linewidth=1.0, linestyle="--", alpha=0.6)
            ax1.annotate("Model",
                         xy=(live_dt, live_rows["close"].iloc[0]),
                         xytext=(6, 10), textcoords="offset points",
                         fontsize=7, color="#27ae60")

        ax1.set_ylabel("Price (USD)", fontsize=9)
        ax1.set_title("Last 6 Months", fontsize=10, fontweight="bold", color="#333")
        ax1.grid(True, alpha=0.25)
        ax1.set_facecolor("white")

        # Weight panel - only shows from live_start onward
        ax2.fill_between(df["date"], df["weight"], alpha=0.55, color=color, step="post")
        ax2.set_ylim(0, 1.1)
        ax2.set_ylabel("Weight", fontsize=8)
        ax2.axhline(y=1.0, color="gray", linestyle="--", linewidth=0.7, alpha=0.4)
        ax2.grid(True, alpha=0.25)
        ax2.set_facecolor("white")

        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax2.xaxis.set_major_locator(mdates.MonthLocator())
        plt.xticks(rotation=25, ha="right", fontsize=7)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()
    except Exception as exc:
        print(f"[WARN] Chart failed: {exc}")
        return None


def sig_color(signal: str) -> str:
    return "#27ae60" if signal == "BUY" else "#e67e22" if signal == "HOLD" else "#e74c3c"


def weight_bar(weight: float, bar_color: str) -> str:
    pct = int(weight * 100)
    filled = int(pct / 5)
    return f"<span style='color:{bar_color}'>{'█' * filled}</span><span style='color:#ddd'>{'░' * (20 - filled)}</span> <b>{pct}%</b>"


def alloc_bar_html(asset_weights: list) -> str:
    segments = ""
    total_pct = sum(int(w * 100) for _, w, _ in asset_weights)
    cash_pct = max(0, 100 - total_pct)
    for label, w, color in asset_weights:
        pct = int(w * 100)
        if pct > 0:
            segments += f"<div style='width:{pct}%;background:{color};display:flex;align-items:center;justify-content:center;color:white'>{'<b>' + label + '</b>' if pct >= 8 else ''}</div>"
    if cash_pct > 0:
        segments += f"<div style='width:{cash_pct}%;background:#e8e8e8;display:flex;align-items:center;justify-content:center;color:#999'>{'CASH' if cash_pct >= 8 else ''}</div>"
    return f"<div style='border-radius:6px;overflow:hidden;height:18px;display:flex;font-size:11px;font-weight:bold'>{segments}</div>"


def asset_section_html(asset: dict, signal_payload: dict, tranche_payload: dict,
                       chart_cid: str, weight_final: float, weight_raw: float,
                       normalized: bool) -> str:
    symbol   = asset["symbol"]
    color    = asset["color"]
    name     = asset["name"]

    asof     = signal_payload.get("asof_date", "-")
    signal   = signal_payload.get("signal", "-")
    strength = signal_payload.get("signal_strength", "-")
    pred_ret = float(signal_payload.get("predicted_future_return", 0))
    model    = signal_payload.get("active_model_name", "-")
    anchor   = signal_payload.get("active_anchor_date", "-")
    horizon  = signal_payload.get("target_horizon_days", "-")
    model_age= signal_payload.get("model_age_days", "-")

    price    = tranche_payload.get("current_price", signal_payload.get("close_price", 0))
    buy_qty  = tranche_payload.get("buy_qty", 0)
    sell_qty = tranche_payload.get("sell_qty", 0)
    net_delta= tranche_payload.get("net_delta", 0)
    net_side = "BUY" if net_delta > 0 else "SELL" if net_delta < 0 else "HOLD"
    allocated= tranche_payload.get("new_tranche", {}).get("allocated_capital", 0) if tranche_payload.get("new_tranche") else 0
    active_t = tranche_payload.get("active_tranches_after", "-")
    total_qty= tranche_payload.get("total_qty_held_after", 0)
    dry_run  = tranche_payload.get("dry_run", True)
    order_st = "DRY RUN" if dry_run else ("SENT" if tranche_payload.get("order", {}).get("submitted") else "SKIPPED")

    sc = sig_color(signal)
    norm_note = f"<span style='font-size:10px;color:#e67e22'> (normalized from {weight_raw:.0%})</span>" if normalized else ""

    pos_contrib = signal_payload.get("top_positive_contributions", [])[:3]
    neg_contrib = signal_payload.get("top_negative_contributions", [])[:3]
    contrib_rows = ""
    for nm, val in pos_contrib:
        contrib_rows += f"<tr><td style='padding:2px 8px;font-size:12px'>{nm}</td><td style='padding:2px 8px;color:#27ae60;text-align:right;font-size:12px'>+{val:.4f}</td></tr>"
    for nm, val in neg_contrib:
        contrib_rows += f"<tr><td style='padding:2px 8px;font-size:12px'>{nm}</td><td style='padding:2px 8px;color:#e74c3c;text-align:right;font-size:12px'>{val:.4f}</td></tr>"

    return f"""
  <!-- ══ {symbol} SECTION ══ -->
  <div style='border-top:3px solid {color};margin-top:0'>

    <!-- Asset header -->
    <div style='background:{color};padding:12px 24px;display:flex;align-items:center;justify-content:space-between'>
      <div>
        <span style='color:white;font-size:16px;font-weight:bold'>{symbol}</span>
        <span style='color:rgba(255,255,255,0.75);font-size:12px;margin-left:8px'>{name}</span>
      </div>
      <span style='color:rgba(255,255,255,0.85);font-size:12px'>{asof}</span>
    </div>

    <!-- Signal + Price -->
    <div style='padding:16px 24px;border-bottom:1px solid #eee'>
      <table width='100%' cellspacing='0'>
        <tr>
          <td style='width:50%;vertical-align:top'>
            <div style='font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.5px'>Signal</div>
            <div style='font-size:28px;font-weight:bold;color:{sc}'>{signal}</div>
            <div style='font-size:12px;color:#999'>{strength}</div>
          </td>
          <td style='width:25%;vertical-align:top'>
            <div style='font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.5px'>Price</div>
            <div style='font-size:22px;font-weight:bold;color:#222'>${float(price):.2f}</div>
            <div style='font-size:11px;color:#999'>pred {pred_ret:+.1%} / {horizon}d</div>
          </td>
          <td style='width:25%;vertical-align:top;text-align:right'>
            <div style='font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.5px'>Allocation</div>
            <div style='font-size:22px;font-weight:bold;color:{color}'>{weight_final:.0%}</div>
            <div style='font-size:11px;color:#aaa'>{norm_note}</div>
          </td>
        </tr>
      </table>
      <div style='margin-top:10px;font-family:monospace;font-size:11px'>{weight_bar(weight_final, color)}</div>
    </div>

    <!-- Chart -->
    <div style='padding:14px 24px;border-bottom:1px solid #eee'>
      <img src='cid:{chart_cid}' style='width:100%;border-radius:5px' />
    </div>

    <!-- Model info -->
    <div style='padding:14px 24px;border-bottom:1px solid #eee'>
      <div style='font-size:11px;font-weight:bold;color:#555;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px'>Model</div>
      <table width='100%' cellspacing='0' style='font-size:12px;color:#444'>
        <tr><td style='padding:2px 0;color:#999'>Active model</td><td style='text-align:right'><b>{model}</b></td></tr>
        <tr><td style='padding:2px 0;color:#999'>Anchor date</td><td style='text-align:right'>{anchor}</td></tr>
        <tr><td style='padding:2px 0;color:#999'>Model age</td><td style='text-align:right'>{model_age} days</td></tr>
      </table>
    </div>

    <!-- Top contributors -->
    <div style='padding:14px 24px;border-bottom:1px solid #eee'>
      <div style='font-size:11px;font-weight:bold;color:#555;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px'>Top Contributors</div>
      <table width='100%' cellspacing='0'>{contrib_rows}</table>
    </div>

    <!-- Order -->
    <div style='padding:14px 24px'>
      <div style='font-size:11px;font-weight:bold;color:#555;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px'>Today's Order</div>
      <table width='100%' cellspacing='0' style='font-size:12px;color:#444'>
        <tr><td style='padding:2px 0;color:#999'>Expired -> sold</td><td style='text-align:right'>{sell_qty:.4f} shares</td></tr>
        <tr><td style='padding:2px 0;color:#999'>New -> bought</td><td style='text-align:right'>{buy_qty:.4f} shares (${allocated:.2f})</td></tr>
        <tr><td style='padding:2px 0;color:#999'>Net order</td><td style='text-align:right'><b>{net_side} {abs(net_delta):.4f}</b></td></tr>
        <tr><td style='padding:2px 0;color:#999'>Active tranches</td><td style='text-align:right'>{active_t}</td></tr>
        <tr><td style='padding:2px 0;color:#999'>Total held</td><td style='text-align:right'>{float(total_qty):.4f} shares</td></tr>
        <tr><td style='padding:2px 0;color:#999'>Status</td><td style='text-align:right'><b>{order_st}</b></td></tr>
      </table>
    </div>

  </div>"""


def build_html(signals: dict, tranches: dict, weights: dict, normalized: bool, asof: str, activity: dict | None = None) -> str:
    total_raw = sum(float(signals.get(a["symbol"], {}).get("target_weight", 0)) for a in ASSETS)
    cash_pct = max(0.0, 1.0 - sum(weights.get(a["symbol"], 0.0) for a in ASSETS))

    # Portfolio overview table (dynamic N assets)
    def _hcell(a: dict) -> str:
        c = a["color"]
        return f"<td style='text-align:center;font-size:13px;color:#444'><span style='color:{c};font-weight:bold'>{a['symbol']}</span></td>"
    def _wcell(a: dict) -> str:
        c = a["color"]
        w = weights.get(a["symbol"], 0)
        return f"<td style='text-align:center;font-size:18px;font-weight:bold;color:{c}'>{w:.0%}</td>"
    header_cells = "".join(_hcell(a) for a in ASSETS) + "<td style='text-align:right;font-size:13px;color:#999'>Cash</td>"
    weight_cells = "".join(_wcell(a) for a in ASSETS) + f"<td style='text-align:right;font-size:18px;font-weight:bold;color:#bbb'>{cash_pct:.0%}</td>"

    norm_banner = ""
    if normalized:
        details = " | ".join(
            f"{a['symbol']} {float(signals.get(a['symbol'],{}).get('target_weight',0)):.0%} -> {weights.get(a['symbol'],0):.0%}"
            for a in ASSETS if weights.get(a["symbol"], 0) > 0
        )
        norm_banner = f"""
  <div style='background:#fff3cd;border-left:4px solid #e67e22;padding:10px 24px;font-size:12px;color:#856404'>
    [!] <b>Normalization applied</b> - combined raw weight {total_raw:.0%} &gt; 100%. {details}
  </div>"""

    asset_sections = ""
    for asset in ASSETS:
        sym = asset["symbol"]
        sig = signals.get(sym, {})
        tr  = tranches.get(sym, {})
        w   = weights.get(sym, 0.0)
        raw = float(sig.get("target_weight", w))
        asset_sections += asset_section_html(asset, sig, tr, f"chart_{asset['slug']}", w, raw, normalized and raw != w)

    bar_data = [(a["symbol"], weights.get(a["symbol"], 0.0), a["color"]) for a in ASSETS]

    return f"""<!DOCTYPE html>
<html>
<head><meta charset='utf-8'></head>
<body style='font-family:Arial,sans-serif;background:#f0f2f5;padding:20px;margin:0'>
<div style='max-width:640px;margin:0 auto;border-radius:12px;overflow:hidden;box-shadow:0 3px 12px rgba(0,0,0,0.12)'>

  <!-- MAIN HEADER -->
  <div style='background:linear-gradient(135deg,#0f2860 0%,#1a5276 100%);padding:22px 28px'>
    <div style='color:rgba(255,255,255,0.6);font-size:11px;text-transform:uppercase;letter-spacing:1px'>Quant Trading System</div>
    <div style='color:white;font-size:22px;font-weight:bold;margin-top:2px'>Daily Signal Report</div>
    <div style='color:rgba(255,255,255,0.7);font-size:12px;margin-top:4px'>{asof}</div>
  </div>

  <!-- PORTFOLIO OVERVIEW -->
  <div style='background:white;padding:18px 24px;border-bottom:1px solid #eee'>
    <div style='font-size:11px;font-weight:bold;color:#555;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px'>Portfolio Allocation</div>
    <table width='100%' cellspacing='0' style='margin-bottom:10px'>
      <tr>{header_cells}</tr>
      <tr>{weight_cells}</tr>
    </table>
    {alloc_bar_html(bar_data)}
  </div>
  {norm_banner}

  <!-- ASSET SECTIONS -->
  {asset_sections}

  {activity_section_html(activity, signals) if activity else ""}

  <!-- FOOTER -->
  <div style='background:#f4f6f9;padding:12px 24px;text-align:center;font-size:10px;color:#bbb'>
    quant-trading-system - {len(ASSETS)}-asset pipeline - {asof}
  </div>

</div>
</body>
</html>"""


def main() -> None:
    args = parse_args()
    config = load_email_config()

    # Load signals for all assets
    signals: dict = {}
    for asset in ASSETS:
        sig = load_json(LIVE_DIR / f"latest_{asset['slug']}_signal.json")
        if sig:
            signals[asset["symbol"]] = sig

    if not signals.get("GLD"):
        print("STATUS: SKIPPED_NO_SIGNAL_FILE")
        return

    asof = signals["GLD"].get("asof_date", "-")

    # Load tranche payloads
    tranches: dict = {}
    for asset in ASSETS:
        tranches[asset["symbol"]] = load_json(latest_file(f"{asset['slug']}_tranche_order_*.json"))

    # Compute normalized weights (re-normalize raw weights > 100%)
    raw_weights = {
        a["symbol"]: float(signals.get(a["symbol"], {}).get("target_weight", 0) or 0)
        for a in ASSETS
    }
    total_raw = sum(raw_weights.values())
    if total_raw > 1.005:
        weights = {sym: w / total_raw for sym, w in raw_weights.items()}
        normalized = True
    else:
        weights = dict(raw_weights)
        normalized = False

    # Use tranche weight_override if available (pipeline may have applied normalization)
    for asset in ASSETS:
        sym = asset["symbol"]
        tr = tranches.get(sym, {})
        if tr and tr.get("target_weight") is not None:
            weights[sym] = float(tr["target_weight"])

    # Build charts - back-predict weight for full 6-month window using active model
    charts: dict[str, bytes | None] = {}
    for asset in ASSETS:
        data_csv = REPO_ROOT / asset["data_csv"]
        sig = signals.get(asset["symbol"], {})
        asof_ts = pd.Timestamp(sig.get("asof_date", asof))
        update_interval = int(sig.get("update_interval_months", 1))
        month_index = ((asof_ts.month - 1) // update_interval) * update_interval + 1
        period_start = pd.Timestamp(year=asof_ts.year, month=month_index, day=1).strftime("%Y-%m-%d")

        anchor_date = sig.get("active_anchor_date")
        weight_series = None
        if anchor_date:
            weight_series = back_predict_weights(
                data_csv=data_csv,
                anchor_output_root=REPO_ROOT / asset["anchor_output_root"],
                anchor_date=anchor_date,
                asof_date=sig.get("asof_date", asof),
                target_horizon_days=int(sig.get("target_horizon_days", 130)),
                selection_criterion=sig.get("selection_criterion", "selection_cv_mse"),
            )

        charts[asset["symbol"]] = build_chart_png(
            data_csv, asset["color"],
            live_start=period_start,
            current_weight=raw_weights.get(asset["symbol"], 0.0),
            weight_series=weight_series,
        )

    activity  = load_activity_data(signals, weights)
    html_body = build_html(signals, tranches, weights, normalized, asof, activity)

    # Subject: show all non-HOLD assets with weight
    gld_price = tranches.get("GLD", {}).get("current_price") or signals.get("GLD", {}).get("close_price", "?")
    active_parts = [
        f"[{a['symbol']} {signals.get(a['symbol'],{}).get('signal','?')} {weights.get(a['symbol'],0):.0%}]"
        for a in ASSETS
        if signals.get(a["symbol"], {}).get("signal", "HOLD") != "HOLD"
    ]
    subject = " ".join(active_parts) + f" ${float(gld_price):.2f} - {date.today()}  (signal: {asof})"

    if args.dry_run:
        print("STATUS: DRY_RUN_PREVIEW")
        print(f"SUBJECT: {subject}")
        for asset in ASSETS:
            sym = asset["symbol"]
            ok = "generated" if charts.get(sym) else "failed"
            print(f"{sym} chart: {ok}  weight={weights.get(sym, 0):.0%}")
        print(f"NORMALIZED: {normalized}  total_raw={sum(raw_weights.values()):.0%}")
        return

    required = [config["smtp_host"], config["from_email"], config["to_email"]]
    if not config["enabled"] or any(not item for item in required):
        print("STATUS: SKIPPED_EMAIL_NOT_CONFIGURED")
        return

    to_email = OWNER_EMAIL if args.test else config["to_email"]
    if args.test:
        subject = "[TEST] " + subject

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"]    = config["from_email"]
    msg["To"]      = to_email

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText("HTML email - please enable HTML viewing.", "plain"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    for asset in ASSETS:
        png = charts.get(asset["symbol"])
        if png:
            img = MIMEImage(png, "png")
            img.add_header("Content-ID", f"<chart_{asset['slug']}>")
            img.add_header("Content-Disposition", "inline", filename=f"{asset['slug']}_chart.png")
            msg.attach(img)

    with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
        if config["smtp_use_tls"]:
            server.starttls()
        if config["smtp_username"]:
            server.login(config["smtp_username"], config["smtp_password"])
        server.send_message(msg)

    print("STATUS: SENT")
    print(f"TO:      {to_email}")
    print(f"SUBJECT: {subject}")


if __name__ == "__main__":
    main()
