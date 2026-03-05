import random
import json
from pathlib import Path
from datetime import datetime

def main():
    # outputs 폴더 경로
    root = Path(__file__).resolve().parents[1]
    outputs_dir = root / "outputs" / "params"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # 가짜 튜닝 결과 (나중에 네 heavy backtest 코드로 교체)
    params = {
        "lookback": random.choice([20, 30, 50, 100]),
        "k": round(random.uniform(1.0, 3.0), 3),
        "threshold": round(random.uniform(0.2, 0.8), 3)
    }

    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "symbol": "SPY",
        "params": params
    }

    file_path = outputs_dir / "latest_params.json"

    with open(file_path, "w") as f:
        json.dump(payload, f, indent=4)

    print("✅ Tuning complete")
    print("Saved to:", file_path)

if __name__ == "__main__":
    main()