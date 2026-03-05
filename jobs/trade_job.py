import json
from pathlib import Path
from datetime import datetime
import random

def utc_now():
    return datetime.utcnow().isoformat(timespec="seconds")

def log_line(root: Path, msg: str):
    log_dir = root / "outputs" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    f = log_dir / "trade.log"
    with open(f, "a", encoding="utf-8") as fp:
        fp.write(f"[{utc_now()}] {msg}\n")

def main():
    root = Path(__file__).resolve().parents[1]
    param_file = root / "outputs" / "params" / "latest_params.json"

    if not param_file.exists():
        print("❌ latest_params.json 없음. 먼저 tuning_job.py 실행해줘.")
        return

    # 1) 파라미터 읽기
    with open(param_file, "r", encoding="utf-8") as f:
        blob = json.load(f)

    symbol = blob.get("symbol", "SPY")
    params = blob.get("params", {})
    lookback = params.get("lookback", 20)
    k = params.get("k", 2.0)
    threshold = params.get("threshold", 0.5)

    # 2) (지금은 데모) 현재 가격 가져오기
    # 나중에 여기만 API로 교체하면 됨
    base = 500.0 if symbol.upper() == "SPY" else 100.0
    price = round(base + random.uniform(-3, 3), 2)

    # 3) (지금은 데모) 신호 만들기
    # 나중에 네 수식으로 교체
    score = price - int(price)  # 0~1
    if score > threshold:
        signal = "BUY"
    elif score < (1 - threshold):
        signal = "SELL"
    else:
        signal = "HOLD"

    msg = f"{symbol} price={price} signal={signal} params={params} (lookback={lookback}, k={k}, threshold={threshold})"
    print("✅", msg)
    log_line(root, msg)

if __name__ == "__main__":
    main()