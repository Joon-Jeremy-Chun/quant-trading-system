from __future__ import annotations

import argparse
import io
import json
import os
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_DIR = REPO_ROOT / "outputs" / "live"

ASSETS = [
    {"symbol": "GLD",   "slug": "gld",   "name": "SPDR Gold ETF",            "color": "#c8a020", "data_csv": "data/gld_us_d.csv"},
    {"symbol": "BRK-B", "slug": "brkb",  "name": "Berkshire Hathaway Cl. B", "color": "#1a5276", "data_csv": "data/brkb_us_d.csv"},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send multi-asset daily HTML signal report.")
    parser.add_argument("--dry-run", action="store_true")
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


def build_chart_png(data_csv: Path, color: str, live_start: str | None = None,
                    current_weight: float = 0.0) -> bytes | None:
    """Price chart + weight panel showing allocation only from live_start onward."""
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

        # Build weight series: 0 before live_start, current_weight from live_start onward
        live_dt = pd.Timestamp(live_start) if live_start else df["date"].max()
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
            ax1.annotate("Live",
                         xy=(live_dt, live_rows["close"].iloc[0]),
                         xytext=(6, 10), textcoords="offset points",
                         fontsize=7, color="#27ae60")

        ax1.set_ylabel("Price (USD)", fontsize=9)
        ax1.set_title("Last 6 Months", fontsize=10, fontweight="bold", color="#333")
        ax1.grid(True, alpha=0.25)
        ax1.set_facecolor("white")

        # Weight panel — only shows from live_start onward
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


def alloc_bar_html(gld_w: float, brkb_w: float) -> str:
    gld_pct = int(gld_w * 100)
    brkb_pct = int(brkb_w * 100)
    cash_pct = max(0, 100 - gld_pct - brkb_pct)
    return f"""
    <div style='border-radius:6px;overflow:hidden;height:18px;display:flex;font-size:11px;font-weight:bold'>
      <div style='width:{gld_pct}%;background:#c8a020;display:flex;align-items:center;justify-content:center;color:white'>
        {'GLD' if gld_pct >= 8 else ''}
      </div>
      <div style='width:{brkb_pct}%;background:#1a5276;display:flex;align-items:center;justify-content:center;color:white'>
        {'BRK' if brkb_pct >= 8 else ''}
      </div>
      <div style='width:{cash_pct}%;background:#e8e8e8;display:flex;align-items:center;justify-content:center;color:#999'>
        {'CASH' if cash_pct >= 8 else ''}
      </div>
    </div>"""


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
        <tr><td style='padding:2px 0;color:#999'>Expired → sold</td><td style='text-align:right'>{sell_qty:.4f} shares</td></tr>
        <tr><td style='padding:2px 0;color:#999'>New → bought</td><td style='text-align:right'>{buy_qty:.4f} shares (${allocated:.2f})</td></tr>
        <tr><td style='padding:2px 0;color:#999'>Net order</td><td style='text-align:right'><b>{net_side} {abs(net_delta):.4f}</b></td></tr>
        <tr><td style='padding:2px 0;color:#999'>Active tranches</td><td style='text-align:right'>{active_t}</td></tr>
        <tr><td style='padding:2px 0;color:#999'>Total held</td><td style='text-align:right'>{float(total_qty):.4f} shares</td></tr>
        <tr><td style='padding:2px 0;color:#999'>Status</td><td style='text-align:right'><b>{order_st}</b></td></tr>
      </table>
    </div>

  </div>"""


def build_html(signals: dict, tranches: dict, weights: dict, normalized: bool, asof: str) -> str:
    gld_sig  = signals.get("GLD", {})
    brkb_sig = signals.get("BRK-B", {})

    gld_w  = weights.get("GLD", float(gld_sig.get("target_weight", 0)))
    brkb_w = weights.get("BRK-B", float(brkb_sig.get("target_weight", 0)))
    gld_raw  = float(gld_sig.get("target_weight", gld_w))
    brkb_raw = float(brkb_sig.get("target_weight", brkb_w))
    cash_pct = max(0.0, 1.0 - gld_w - brkb_w)

    norm_banner = ""
    if normalized:
        norm_banner = f"""
  <div style='background:#fff3cd;border-left:4px solid #e67e22;padding:10px 24px;font-size:12px;color:#856404'>
    ⚡ <b>Normalization applied</b> — combined raw weight {gld_raw+brkb_raw:.0%} &gt; 100%.
    GLD scaled {gld_raw:.0%} → {gld_w:.0%} &nbsp;|&nbsp; BRK-B scaled {brkb_raw:.0%} → {brkb_w:.0%}
  </div>"""

    gld_section  = asset_section_html(ASSETS[0], gld_sig,  tranches.get("GLD", {}),  "chart_gld",  gld_w,  gld_raw,  normalized and gld_raw != gld_w)
    brkb_section = asset_section_html(ASSETS[1], brkb_sig, tranches.get("BRK-B", {}), "chart_brkb", brkb_w, brkb_raw, normalized and brkb_raw != brkb_w)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset='utf-8'></head>
<body style='font-family:Arial,sans-serif;background:#f0f2f5;padding:20px;margin:0'>
<div style='max-width:640px;margin:0 auto;border-radius:12px;overflow:hidden;box-shadow:0 3px 12px rgba(0,0,0,0.12)'>

  <!-- ── MAIN HEADER ── -->
  <div style='background:linear-gradient(135deg,#0f2860 0%,#1a5276 100%);padding:22px 28px'>
    <div style='color:rgba(255,255,255,0.6);font-size:11px;text-transform:uppercase;letter-spacing:1px'>Quant Trading System</div>
    <div style='color:white;font-size:22px;font-weight:bold;margin-top:2px'>📊 Daily Signal Report</div>
    <div style='color:rgba(255,255,255,0.7);font-size:12px;margin-top:4px'>{asof}</div>
  </div>

  <!-- ── PORTFOLIO OVERVIEW ── -->
  <div style='background:white;padding:18px 24px;border-bottom:1px solid #eee'>
    <div style='font-size:11px;font-weight:bold;color:#555;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px'>Portfolio Allocation</div>
    <table width='100%' cellspacing='0' style='margin-bottom:10px'>
      <tr>
        <td style='font-size:13px;color:#444'><span style='color:#c8a020;font-weight:bold'>GLD</span></td>
        <td style='text-align:center;font-size:13px;color:#444'><span style='color:#1a5276;font-weight:bold'>BRK-B</span></td>
        <td style='text-align:right;font-size:13px;color:#999'>Cash</td>
      </tr>
      <tr>
        <td style='font-size:20px;font-weight:bold;color:#c8a020'>{gld_w:.0%}</td>
        <td style='text-align:center;font-size:20px;font-weight:bold;color:#1a5276'>{brkb_w:.0%}</td>
        <td style='text-align:right;font-size:20px;font-weight:bold;color:#bbb'>{cash_pct:.0%}</td>
      </tr>
    </table>
    {alloc_bar_html(gld_w, brkb_w)}
  </div>
  {norm_banner}

  <!-- ── ASSET SECTIONS ── -->
  {gld_section}
  {brkb_section}

  <!-- ── FOOTER ── -->
  <div style='background:#f4f6f9;padding:12px 24px;text-align:center;font-size:10px;color:#bbb'>
    quant-trading-system · multi-asset pipeline · {asof}
  </div>

</div>
</body>
</html>"""


def main() -> None:
    args = parse_args()
    config = load_email_config()

    # Load signals
    gld_signal  = load_json(LIVE_DIR / "latest_gld_signal.json")
    brkb_signal = load_json(LIVE_DIR / "latest_brkb_signal.json")
    signals = {"GLD": gld_signal, "BRK-B": brkb_signal}

    if not gld_signal:
        print("STATUS: SKIPPED_NO_SIGNAL_FILE")
        return

    # Load tranche payloads
    gld_tranche  = load_json(latest_file("gld_tranche_order_*.json"))
    brkb_tranche = load_json(latest_file("brkb_tranche_order_*.json"))
    tranches = {"GLD": gld_tranche, "BRK-B": brkb_tranche}

    # Reconstruct normalized weights from tranche payloads (weight_override was applied)
    gld_w_final  = float(gld_tranche.get("target_weight",  gld_signal.get("target_weight", 0)))
    brkb_w_final = float(brkb_tranche.get("target_weight", brkb_signal.get("target_weight", 0)) if brkb_tranche else brkb_signal.get("target_weight", 0))
    gld_raw  = float(gld_signal.get("target_weight", gld_w_final))
    brkb_raw = float(brkb_signal.get("target_weight", brkb_w_final))
    normalized = (gld_raw + brkb_raw) > 1.005
    weights = {"GLD": gld_w_final, "BRK-B": brkb_w_final}

    asof = gld_signal.get("asof_date", "-")

    # Build charts — weight panel shows only from asof_date onward (actual live start)
    live_start = asof
    charts: dict[str, bytes | None] = {}
    weight_map = {"GLD": gld_w_final, "BRK-B": brkb_w_final}
    for asset in ASSETS:
        data_csv = REPO_ROOT / asset["data_csv"]
        charts[asset["symbol"]] = build_chart_png(
            data_csv, asset["color"],
            live_start=live_start,
            current_weight=weight_map.get(asset["symbol"], 0.0),
        )

    html_body = build_html(signals, tranches, weights, normalized, asof)

    # Subject line
    gld_sig_str  = gld_signal.get("signal", "?")
    brkb_sig_str = brkb_signal.get("signal", "?") if brkb_signal else "?"
    gld_price    = gld_tranche.get("current_price", gld_signal.get("close_price", "?"))
    subject = (
        f"[GLD {gld_sig_str} {gld_w_final:.0%}] "
        f"[BRK-B {brkb_sig_str} {brkb_w_final:.0%}] "
        f"${float(gld_price):.2f} · {asof}"
    )

    if args.dry_run:
        print("STATUS: DRY_RUN_PREVIEW")
        print(f"SUBJECT: {subject}")
        print(f"GLD chart:  {'generated' if charts.get('GLD') else 'failed'}")
        print(f"BRK chart:  {'generated' if charts.get('BRK-B') else 'failed'}")
        print(f"NORMALIZED: {normalized}")
        print(f"GLD  raw={gld_raw:.2%} → final={gld_w_final:.2%}")
        print(f"BRKB raw={brkb_raw:.2%} → final={brkb_w_final:.2%}")
        return

    required = [config["smtp_host"], config["from_email"], config["to_email"]]
    if not config["enabled"] or any(not item for item in required):
        print("STATUS: SKIPPED_EMAIL_NOT_CONFIGURED")
        return

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"]    = config["from_email"]
    msg["To"]      = config["to_email"]

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText("HTML email — please enable HTML viewing.", "plain"))
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
    print(f"TO:      {config['to_email']}")
    print(f"SUBJECT: {subject}")


if __name__ == "__main__":
    main()
