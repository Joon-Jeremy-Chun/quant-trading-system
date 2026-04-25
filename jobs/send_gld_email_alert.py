from __future__ import annotations

import argparse
import io
import json
import os
import smtplib
from email.message import EmailMessage
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_DIR = REPO_ROOT / "outputs" / "live"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a daily GLD HTML email report with chart.")
    parser.add_argument("--symbol", type=str, default="GLD")
    parser.add_argument("--dry-run", action="store_true", help="Print preview instead of sending.")
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


def build_chart_png(data_csv: Path, signal_log: Path) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    # Load price data - last 6 months
    df = pd.read_csv(data_csv, parse_dates=["Date"])
    df = df.rename(columns={"Date": "date", "Close": "close"})
    df = df.sort_values("date")
    cutoff = df["date"].max() - pd.DateOffset(months=6)
    df = df[df["date"] >= cutoff].copy()

    # Load signal history
    signals = pd.DataFrame()
    if signal_log.exists():
        signals = pd.read_csv(signal_log, parse_dates=["asof_date"])
        signals = signals[signals["asof_date"] >= cutoff]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
    fig.patch.set_facecolor("#f9f9f9")

    # Price chart
    ax1.plot(df["date"], df["close"], color="#1a5276", linewidth=1.5, label="GLD Close")
    ax1.fill_between(df["date"], df["close"], df["close"].min(), alpha=0.08, color="#1a5276")

    # BUY signal markers
    if not signals.empty:
        buy_signals = signals[signals["signal"] == "BUY"]
        if not buy_signals.empty:
            buy_prices = df.set_index("date")["close"].reindex(
                buy_signals["asof_date"], method="nearest"
            )
            ax1.scatter(
                buy_signals["asof_date"].values,
                buy_prices.values,
                marker="^", color="#27ae60", s=60, zorder=5, label="BUY signal"
            )

    ax1.set_ylabel("Price (USD)", fontsize=10)
    ax1.set_title("GLD - Last 6 Months", fontsize=12, fontweight="bold")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.set_facecolor("white")

    # Target weight chart
    if not signals.empty and "target_weight" in signals.columns:
        ax2.fill_between(signals["asof_date"].values, signals["target_weight"].values, alpha=0.6, color="#2980b9", step="post")
        ax2.set_ylim(0, 1.1)
        ax2.set_ylabel("Weight", fontsize=9)
        ax2.axhline(y=1.0, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
        ax2.grid(True, alpha=0.3)
        ax2.set_facecolor("white")

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    plt.xticks(rotation=30, ha="right", fontsize=8)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def signal_color(signal: str) -> str:
    return "#27ae60" if signal == "BUY" else "#e67e22" if signal == "HOLD" else "#e74c3c"


def weight_bar(weight: float) -> str:
    pct = int(weight * 100)
    filled = int(pct / 5)
    bar = "█" * filled + "░" * (20 - filled)
    return f"{bar} {pct}%"


def build_html(symbol: str, signal_payload: dict, tranche_payload: dict) -> str:
    asof = signal_payload.get("asof_date", "-")
    signal = signal_payload.get("signal", "-")
    strength = signal_payload.get("signal_strength", "-")
    weight = float(signal_payload.get("target_weight", 0))
    pred_return = float(signal_payload.get("predicted_future_return", 0))
    model = signal_payload.get("active_model_name", "-")
    anchor = signal_payload.get("active_anchor_date", "-")
    horizon = signal_payload.get("target_horizon_days", "-")
    model_age = signal_payload.get("model_age_days", "-")

    price = tranche_payload.get("current_price", signal_payload.get("close_price", "-"))
    buy_qty = tranche_payload.get("buy_qty", 0)
    sell_qty = tranche_payload.get("sell_qty", 0)
    net_delta = tranche_payload.get("net_delta", 0)
    net_side = "BUY" if net_delta > 0 else "SELL" if net_delta < 0 else "HOLD"
    allocated = tranche_payload.get("new_tranche", {}).get("allocated_capital", 0) if tranche_payload.get("new_tranche") else 0
    active_tranches = tranche_payload.get("active_tranches_after", "-")
    total_qty = tranche_payload.get("total_qty_held_after", 0)
    dry_run = tranche_payload.get("dry_run", True)
    order_status = "DRY RUN" if dry_run else ("SENT" if tranche_payload.get("order", {}).get("submitted") else "SKIPPED")

    # Top contributions
    pos_contrib = signal_payload.get("top_positive_contributions", [])[:3]
    neg_contrib = signal_payload.get("top_negative_contributions", [])[:3]

    sig_color = signal_color(signal)

    contrib_rows = ""
    for name, val in pos_contrib:
        contrib_rows += f"<tr><td style='padding:3px 8px'>{name}</td><td style='padding:3px 8px;color:#27ae60;text-align:right'>+{val:.4f}</td></tr>"
    for name, val in neg_contrib:
        contrib_rows += f"<tr><td style='padding:3px 8px'>{name}</td><td style='padding:3px 8px;color:#e74c3c;text-align:right'>{val:.4f}</td></tr>"

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;background:#f4f6f9;padding:20px;margin:0">
<div style="max-width:620px;margin:0 auto;background:white;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1)">

  <!-- Header -->
  <div style="background:#1a5276;color:white;padding:20px 24px">
    <h2 style="margin:0;font-size:20px">📊 {symbol} Daily Signal Report</h2>
    <p style="margin:4px 0 0;opacity:0.85;font-size:13px">{asof}</p>
  </div>

  <!-- Signal Summary -->
  <div style="padding:20px 24px;border-bottom:1px solid #eee">
    <table width="100%" cellspacing="0">
      <tr>
        <td style="width:50%;vertical-align:top">
          <div style="font-size:13px;color:#666">TODAY'S SIGNAL</div>
          <div style="font-size:32px;font-weight:bold;color:{sig_color}">{signal}</div>
          <div style="font-size:13px;color:#888">{strength} · weight {weight:.2f}</div>
        </td>
        <td style="width:50%;vertical-align:top;text-align:right">
          <div style="font-size:13px;color:#666">GLD PRICE</div>
          <div style="font-size:28px;font-weight:bold;color:#1a5276">${price:.2f}</div>
          <div style="font-size:12px;color:#888">pred. return {pred_return:+.1%} over {horizon}d</div>
        </td>
      </tr>
    </table>
    <div style="margin-top:12px;font-family:monospace;font-size:12px;color:#555">{weight_bar(weight)}</div>
  </div>

  <!-- Chart -->
  <div style="padding:16px 24px;border-bottom:1px solid #eee">
    <img src="cid:gld_chart" style="width:100%;border-radius:6px" />
  </div>

  <!-- Model Info -->
  <div style="padding:16px 24px;border-bottom:1px solid #eee">
    <div style="font-size:13px;font-weight:bold;color:#333;margin-bottom:8px">MODEL</div>
    <table width="100%" cellspacing="0" style="font-size:13px;color:#444">
      <tr><td style="padding:3px 0;color:#888">Active model</td><td style="text-align:right"><b>{model}</b></td></tr>
      <tr><td style="padding:3px 0;color:#888">Anchor date</td><td style="text-align:right">{anchor}</td></tr>
      <tr><td style="padding:3px 0;color:#888">Model age</td><td style="text-align:right">{model_age} days</td></tr>
    </table>
  </div>

  <!-- Top Contributors -->
  <div style="padding:16px 24px;border-bottom:1px solid #eee">
    <div style="font-size:13px;font-weight:bold;color:#333;margin-bottom:8px">TOP SIGNAL CONTRIBUTORS</div>
    <table width="100%" cellspacing="0" style="font-size:12px">{contrib_rows}</table>
  </div>

  <!-- Order -->
  <div style="padding:16px 24px;border-bottom:1px solid #eee">
    <div style="font-size:13px;font-weight:bold;color:#333;margin-bottom:8px">TODAY'S ORDER</div>
    <table width="100%" cellspacing="0" style="font-size:13px;color:#444">
      <tr><td style="padding:3px 0;color:#888">Expired tranches sold</td><td style="text-align:right">{sell_qty:.4f} shares</td></tr>
      <tr><td style="padding:3px 0;color:#888">New tranche bought</td><td style="text-align:right">{buy_qty:.4f} shares  (${allocated:.2f})</td></tr>
      <tr><td style="padding:3px 0;color:#888">Net order</td><td style="text-align:right"><b>{net_side}  {abs(net_delta):.4f} shares</b></td></tr>
      <tr><td style="padding:3px 0;color:#888">Status</td><td style="text-align:right">{order_status}</td></tr>
    </table>
  </div>

  <!-- Portfolio -->
  <div style="padding:16px 24px">
    <div style="font-size:13px;font-weight:bold;color:#333;margin-bottom:8px">PORTFOLIO</div>
    <table width="100%" cellspacing="0" style="font-size:13px;color:#444">
      <tr><td style="padding:3px 0;color:#888">Active tranches</td><td style="text-align:right">{active_tranches}</td></tr>
      <tr><td style="padding:3px 0;color:#888">Total shares held</td><td style="text-align:right">{total_qty:.4f} shares</td></tr>
      <tr><td style="padding:3px 0;color:#888">Market value</td><td style="text-align:right">${float(total_qty) * float(price):.2f}</td></tr>
    </table>
  </div>

  <!-- Footer -->
  <div style="background:#f4f6f9;padding:12px 24px;text-align:center;font-size:11px;color:#aaa">
    quant-trading-system · GLD live pipeline · {asof}
  </div>

</div>
</body>
</html>"""
    return html


def main() -> None:
    args = parse_args()
    config = load_email_config()

    signal_payload = load_json(LIVE_DIR / "latest_gld_signal.json")
    tranche_path = latest_file("gld_tranche_order_*.json")
    tranche_payload = load_json(tranche_path)

    if not signal_payload:
        print("STATUS: SKIPPED_NO_SIGNAL_FILE")
        return

    # Build chart
    data_csv = REPO_ROOT / "data" / "gld_us_d.csv"
    signal_log = LIVE_DIR / "history" / "gld_signal_log.csv"
    chart_png: bytes | None = None
    try:
        chart_png = build_chart_png(data_csv, signal_log)
    except Exception as exc:
        print(f"[WARN] Chart generation failed: {exc}")

    html_body = build_html(args.symbol, signal_payload, tranche_payload)
    subject = (
        f"[GLD] {signal_payload.get('signal','?')} "
        f"w={float(signal_payload.get('target_weight',0)):.2f} "
        f"${tranche_payload.get('current_price', signal_payload.get('close_price','?')):.2f} "
        f"- {signal_payload.get('asof_date','?')}"
    )

    if args.dry_run:
        print("STATUS: DRY_RUN_PREVIEW")
        print(f"SUBJECT: {subject}")
        print(f"CHART:   {'generated' if chart_png else 'failed'}")
        print(f"HTML:    {len(html_body)} chars")
        return

    required = [config["smtp_host"], config["from_email"], config["to_email"]]
    if not config["enabled"] or any(not item for item in required):
        print("STATUS: SKIPPED_EMAIL_NOT_CONFIGURED")
        return

    # Build multipart/related so Gmail shows inline chart image
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = config["from_email"]
    msg["To"] = config["to_email"]

    html_part = MIMEMultipart("alternative")
    html_part.attach(MIMEText("HTML email - please enable HTML viewing.", "plain"))
    html_part.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(html_part)

    if chart_png:
        img_part = MIMEImage(chart_png, "png")
        img_part.add_header("Content-ID", "<gld_chart>")
        img_part.add_header("Content-Disposition", "inline", filename="gld_chart.png")
        msg.attach(img_part)

    with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
        if config["smtp_use_tls"]:
            server.starttls()
        if config["smtp_username"]:
            server.login(config["smtp_username"], config["smtp_password"])
        server.send_message(msg)

    print("STATUS: SENT")
    print(f"TO:      {config['to_email']}")
    print(f"SUBJECT: {subject}")


if __name__ == "__main__":
    main()
