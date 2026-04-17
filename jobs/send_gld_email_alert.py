from __future__ import annotations

import argparse
import json
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_DIR = REPO_ROOT / "outputs" / "live"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a daily GLD email alert using the latest signal and order payload."
    )
    parser.add_argument("--symbol", type=str, default="GLD", help="Symbol label used in the email.")
    parser.add_argument("--dry-run", action="store_true", help="Print the email preview instead of sending.")
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


def latest_order_payload_path() -> Path | None:
    candidates = sorted(LIVE_DIR.glob("gld_close_order_job_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def load_json_if_exists(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_subject(symbol: str, signal_payload: dict, order_plan: dict, order_payload: dict) -> str:
    signal = signal_payload.get("signal", "UNKNOWN")
    action = order_plan.get("action", "UNKNOWN")
    submitted = order_payload.get("submitted", False)
    sent_text = "SENT" if submitted else "NO_ORDER"
    return f"[QuantTrading] {symbol} {signal} / {action} / {sent_text}"


def build_body(symbol: str, signal_payload: dict, order_payload_full: dict) -> str:
    order_plan = order_payload_full.get("order_plan", {})
    order_payload = order_payload_full.get("order_payload", {})
    quote_payload = order_payload_full.get("quote_payload", {})
    position_payload = order_payload_full.get("position_payload", {})

    lines = [
        f"Symbol: {symbol}",
        "",
        "[Signal]",
        f"As-of date: {signal_payload.get('asof_date')}",
        f"Signal: {signal_payload.get('signal')}",
        f"Signal strength: {signal_payload.get('signal_strength')}",
        f"Target weight: {signal_payload.get('target_weight')}",
        f"Predicted future return: {signal_payload.get('predicted_future_return')}",
        f"Target horizon days: {signal_payload.get('target_horizon_days')}",
        f"Update interval months: {signal_payload.get('update_interval_months')}",
        f"Active anchor date: {signal_payload.get('active_anchor_date')}",
        f"Active model: {signal_payload.get('active_model_name')}",
        f"Dominant family: {signal_payload.get('dominant_family')}",
        f"Dataset staleness days: {signal_payload.get('dataset_staleness_days')}",
        f"Model age days: {signal_payload.get('model_age_days')}",
        "",
        "[Order Plan]",
        f"Action: {order_plan.get('action')}",
        f"Desired position qty: {order_plan.get('desired_position_qty')}",
        f"Current position qty: {order_plan.get('current_position_qty')}",
        f"Delta qty: {order_plan.get('delta_qty')}",
        f"Order side: {order_plan.get('order_side')}",
        f"Order qty: {order_plan.get('order_qty')}",
        f"Reasons: {order_plan.get('reasons')}",
        "",
        "[Order Result]",
        f"Submitted: {order_payload.get('submitted')}",
        f"Reason: {order_payload.get('reason')}",
        f"Order ID: {order_payload.get('order_id')}",
        "",
        "[Quote]",
        f"Bid: {quote_payload.get('bid_price')}",
        f"Ask: {quote_payload.get('ask_price')}",
        f"Quote timestamp: {quote_payload.get('timestamp')}",
        f"Quote error: {quote_payload.get('quote_fetch_error')}",
        "",
        "[Position]",
        f"Position available: {position_payload.get('available')}",
        f"Position qty: {position_payload.get('qty')}",
        f"Position error: {position_payload.get('error')}",
        "",
        "[Top Positive Contributions]",
    ]

    for item in signal_payload.get("top_positive_contributions", [])[:5]:
        lines.append(f"- {item[0]}: {item[1]}")

    lines.extend(["", "[Top Negative Contributions]"])
    for item in signal_payload.get("top_negative_contributions", [])[:5]:
        lines.append(f"- {item[0]}: {item[1]}")

    return "\n".join(lines)


def send_email(config: dict, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config["from_email"]
    msg["To"] = config["to_email"]
    msg.set_content(body)

    with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
        if config["smtp_use_tls"]:
            server.starttls()
        if config["smtp_username"]:
            server.login(config["smtp_username"], config["smtp_password"])
        server.send_message(msg)


def main() -> None:
    args = parse_args()
    config = load_email_config()

    latest_signal_path = LIVE_DIR / "latest_gld_signal.json"
    latest_order_path = latest_order_payload_path()
    signal_payload = load_json_if_exists(latest_signal_path)
    order_payload_full = load_json_if_exists(latest_order_path)

    if not signal_payload:
        print("STATUS: SKIPPED_NO_SIGNAL_FILE")
        return

    order_plan = order_payload_full.get("order_plan", {})
    order_payload = order_payload_full.get("order_payload", {})
    subject = build_subject(args.symbol, signal_payload, order_plan, order_payload)
    body = build_body(args.symbol, signal_payload, order_payload_full)

    if args.dry_run:
        print("STATUS: DRY_RUN_PREVIEW")
        print(subject)
        print("-" * 80)
        print(body)
        return

    required = [
        config["smtp_host"],
        config["from_email"],
        config["to_email"],
    ]
    if not config["enabled"] or any(not item for item in required):
        print("STATUS: SKIPPED_EMAIL_NOT_CONFIGURED")
        return

    send_email(config, subject, body)
    print("STATUS: SENT")
    print(f"TO: {config['to_email']}")
    print(f"SUBJECT: {subject}")


if __name__ == "__main__":
    main()
