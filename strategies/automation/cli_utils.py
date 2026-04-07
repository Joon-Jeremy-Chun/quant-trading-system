from __future__ import annotations

import argparse
from pathlib import Path


def parse_horizon_tokens(raw: str | None) -> list[str]:
    if not raw:
        return []

    tokens = []
    for part in raw.split(","):
        token = part.strip().lower()
        if token:
            tokens.append(token)

    if not tokens:
        raise ValueError("Horizon override was provided but no valid tokens were found.")

    return tokens


def horizon_token_to_offset(token: str) -> dict[str, int]:
    if len(token) < 2:
        raise ValueError(f"Invalid horizon token: {token}")

    unit = token[-1]
    try:
        value = int(token[:-1])
    except ValueError as exc:
        raise ValueError(f"Invalid horizon token: {token}") from exc

    if value <= 0:
        raise ValueError(f"Horizon value must be positive: {token}")

    if unit == "m":
        return {"months": value}
    if unit == "y":
        return {"years": value}

    raise ValueError(f"Unsupported horizon unit in token: {token}")


def build_horizon_config(raw: str | None, fallback: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    tokens = parse_horizon_tokens(raw)
    if not tokens:
        return fallback

    return {token: horizon_token_to_offset(token) for token in tokens}


def build_horizon_list(raw: str | None, fallback: list[str]) -> list[str]:
    tokens = parse_horizon_tokens(raw)
    if not tokens:
        return fallback
    return tokens


def resolve_override_path(raw: str | None, base_dir: Path) -> Path | None:
    if not raw:
        return None

    path = Path(raw)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def add_common_optimization_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--data-csv", type=str, default=None, help="Override input dataset CSV path.")
    parser.add_argument("--train-end-date", type=str, default=None, help="Override training end date (YYYY-MM-DD).")
    parser.add_argument("--horizons", type=str, default=None, help="Comma-separated horizons such as 1m,3m,6m,1y.")
    parser.add_argument("--top-n", type=int, default=None, help="Override top-N results to save.")
    return parser


def add_common_forward_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--data-csv", type=str, default=None, help="Override input dataset CSV path.")
    parser.add_argument("--optimization-dir", type=str, default=None, help="Override optimization results directory.")
    parser.add_argument("--train-end-date", type=str, default=None, help="Override training end date (YYYY-MM-DD).")
    parser.add_argument("--test-start-date", type=str, default=None, help="Override forward-test start date (YYYY-MM-DD).")
    parser.add_argument("--test-end-date", type=str, default=None, help="Override forward-test end date (YYYY-MM-DD).")
    parser.add_argument("--horizons", type=str, default=None, help="Comma-separated horizons such as 1m,3m,6m,1y.")
    parser.add_argument("--top-n", type=int, default=None, help="Override top-N parameter sets to load.")
    return parser
