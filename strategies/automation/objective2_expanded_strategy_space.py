from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from objective2_signal_matrix_builder import (
    SCORE_COLUMNS,
    StrategyScoreContext,
    TARGET_DIRECTION_COL,
    TARGET_RETURN_COL,
    adaptive_band_score_df,
    adaptive_volatility_score_df,
    fear_greed_score_df,
    ma_crossover_score_df,
)
from strategy_matrix_builder import DATE_COL, StrategySelection


DEFAULT_FAMILY_HORIZONS = {
    "adaptive_band": "1y",
    "ma_crossover": "6m",
    "adaptive_volatility_band": "3m",
    "fear_greed_candle_volume": "1m",
}

DEFAULT_TOP_N_PER_FAMILY = {
    "adaptive_band": 10,
    "ma_crossover": 10,
    "adaptive_volatility_band": 10,
    "fear_greed_candle_volume": 10,
}


@dataclass(frozen=True)
class ExpandedStrategyBasis:
    strategy_key: str
    horizon_name: str
    rank: int
    params: dict[str, float | int]
    source_csv: Path
    source_kind: str
    total_return: float
    buy_hold_return: float
    excess_vs_bh: float
    score_column: str
    scale_value: float | None = None


@dataclass(frozen=True)
class ExpandedStrategySpaceBundle:
    selection_df: pd.DataFrame
    evaluation_df: pd.DataFrame
    feature_columns: list[str]
    bases: list[ExpandedStrategyBasis]
    target_horizon_days: int


def _family_output_dir(repo_root: Path, strategy_key: str) -> Path:
    mapping = {
        "adaptive_band": repo_root / "outputs" / "11_adaptive_band_strategy_optimization",
        "ma_crossover": repo_root / "outputs" / "21_ma_crossover_optimization",
        "adaptive_volatility_band": repo_root / "outputs" / "31_adaptive_volatility_band_optimization",
        "fear_greed_candle_volume": repo_root / "outputs" / "41_fear_greed_candle_volume_optimization",
    }
    if strategy_key not in mapping:
        raise ValueError(f"Unsupported strategy key: {strategy_key}")
    return mapping[strategy_key]


def _family_output_dir_from_root(output_root: Path, strategy_key: str) -> Path:
    mapping = {
        "adaptive_band": output_root / "11_adaptive_band_strategy_optimization",
        "ma_crossover": output_root / "21_ma_crossover_optimization",
        "adaptive_volatility_band": output_root / "31_adaptive_volatility_band_optimization",
        "fear_greed_candle_volume": output_root / "41_fear_greed_candle_volume_optimization",
    }
    if strategy_key not in mapping:
        raise ValueError(f"Unsupported strategy key: {strategy_key}")
    return mapping[strategy_key]


def _strategy_param_columns(strategy_key: str) -> list[str]:
    mapping = {
        "adaptive_band": ["ma_window", "upper_k", "lower_k"],
        "ma_crossover": ["short_ma", "long_ma"],
        "adaptive_volatility_band": ["vol_window", "upper_k", "lower_k"],
        "fear_greed_candle_volume": ["k_body", "k_volume", "price_zone_window"],
    }
    return mapping[strategy_key]


def _score_column_name(strategy_key: str, rank: int) -> str:
    return f"{strategy_key}_rank{rank:02d}_score"


def load_top_family_selections(
    repo_root: Path,
    family_horizons: dict[str, str] | None = None,
    top_n_per_family: dict[str, int] | None = None,
    family_output_root: Path | None = None,
) -> list[ExpandedStrategyBasis]:
    horizons = family_horizons or DEFAULT_FAMILY_HORIZONS
    top_n_map = top_n_per_family or DEFAULT_TOP_N_PER_FAMILY

    all_bases: list[ExpandedStrategyBasis] = []
    for strategy_key, horizon_name in horizons.items():
        top_n = top_n_map[strategy_key]
        if family_output_root is None:
            output_dir = _family_output_dir(repo_root, strategy_key)
        else:
            output_dir = _family_output_dir_from_root(family_output_root, strategy_key)
        csv_path = output_dir / horizon_name / f"{horizon_name}_all_ranked_results.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"Ranked results CSV not found: {csv_path}")

        df = pd.read_csv(csv_path).head(top_n).copy()
        param_cols = _strategy_param_columns(strategy_key)
        for idx, row in enumerate(df.to_dict(orient="records"), start=1):
            params = {key: row[key] for key in param_cols}
            all_bases.append(
                ExpandedStrategyBasis(
                    strategy_key=strategy_key,
                    horizon_name=horizon_name,
                    rank=idx,
                    params=params,
                    source_csv=csv_path,
                    source_kind=f"optimization_top{top_n}_rank{idx}",
                    total_return=float(row["total_return"]),
                    buy_hold_return=float(row["buy_hold_return"]),
                    excess_vs_bh=float(row["excess_vs_bh"]),
                    score_column=_score_column_name(strategy_key, idx),
                    scale_value=None,
                )
            )

    return all_bases


def _to_strategy_selection(basis: ExpandedStrategyBasis) -> StrategySelection:
    return StrategySelection(
        strategy_key=basis.strategy_key,
        horizon_name=basis.horizon_name,
        params=basis.params,
        total_return=basis.total_return,
        buy_hold_return=basis.buy_hold_return,
        excess_vs_bh=basis.excess_vs_bh,
        source_csv=basis.source_csv,
        source_kind=basis.source_kind,
    )


def _build_score_df_for_basis(
    data_csv: Path,
    basis: ExpandedStrategyBasis,
    start_date: str,
    end_date: str,
    target_horizon_days: int,
    scale_override: float | None = None,
) -> tuple[pd.DataFrame, float | None]:
    selection = _to_strategy_selection(basis)
    base_score_column = SCORE_COLUMNS[basis.strategy_key]

    if basis.strategy_key == "adaptive_band":
        df, _ = adaptive_band_score_df(
            data_csv,
            selection,
            start_date,
            end_date,
            target_horizon_days=target_horizon_days,
        )
        scale_value = None
    elif basis.strategy_key == "ma_crossover":
        df, context = ma_crossover_score_df(
            data_csv,
            selection,
            start_date,
            end_date,
            scale_value=scale_override,
            target_horizon_days=target_horizon_days,
        )
        scale_value = context.scale_value
    elif basis.strategy_key == "adaptive_volatility_band":
        df, _ = adaptive_volatility_score_df(
            data_csv,
            selection,
            start_date,
            end_date,
            target_horizon_days=target_horizon_days,
        )
        scale_value = None
    elif basis.strategy_key == "fear_greed_candle_volume":
        df, _ = fear_greed_score_df(
            data_csv,
            selection,
            start_date,
            end_date,
            target_horizon_days=target_horizon_days,
        )
        scale_value = None
    else:
        raise ValueError(f"Unsupported strategy key: {basis.strategy_key}")

    df = df.rename(columns={base_score_column: basis.score_column})
    return df[[DATE_COL, basis.score_column, TARGET_RETURN_COL, TARGET_DIRECTION_COL]], scale_value


def build_expanded_strategy_space(
    repo_root: Path,
    data_csv: Path,
    selection_start_date: str,
    selection_end_date: str,
    evaluation_start_date: str,
    evaluation_end_date: str,
    target_horizon_days: int = 1,
    family_horizons: dict[str, str] | None = None,
    top_n_per_family: dict[str, int] | None = None,
    family_output_root: Path | None = None,
) -> ExpandedStrategySpaceBundle:
    bases = load_top_family_selections(
        repo_root=repo_root,
        family_horizons=family_horizons,
        top_n_per_family=top_n_per_family,
        family_output_root=family_output_root,
    )

    selection_frames: list[pd.DataFrame] = []
    evaluation_frames: list[pd.DataFrame] = []
    updated_bases: list[ExpandedStrategyBasis] = []

    for basis in bases:
        selection_score_df, scale_value = _build_score_df_for_basis(
            data_csv=data_csv,
            basis=basis,
            start_date=selection_start_date,
            end_date=selection_end_date,
            target_horizon_days=target_horizon_days,
            scale_override=None,
        )
        if selection_score_df.empty:
            continue

        basis_with_scale = ExpandedStrategyBasis(**{**basis.__dict__, "scale_value": scale_value})
        evaluation_score_df, _ = _build_score_df_for_basis(
            data_csv=data_csv,
            basis=basis_with_scale,
            start_date=evaluation_start_date,
            end_date=evaluation_end_date,
            target_horizon_days=target_horizon_days,
            scale_override=basis_with_scale.scale_value,
        )
        if evaluation_score_df.empty:
            continue

        updated_bases.append(basis_with_scale)
        selection_frames.append(selection_score_df)
        evaluation_frames.append(evaluation_score_df)

    if not selection_frames:
        raise ValueError("Expanded selection strategy-space matrix is empty after filtering invalid bases.")
    if not evaluation_frames:
        raise ValueError("Expanded evaluation strategy-space matrix is empty after filtering invalid bases.")

    selection_merged = selection_frames[0].copy()
    for basis, score_df in zip(updated_bases[1:], selection_frames[1:]):
        selection_merged = selection_merged.merge(
            score_df[[DATE_COL, basis.score_column]],
            on=DATE_COL,
            how="inner",
        )
    if selection_merged.empty:
        raise ValueError("Expanded selection strategy-space matrix is empty after merging.")

    evaluation_merged = evaluation_frames[0].copy()
    for basis, score_df in zip(updated_bases[1:], evaluation_frames[1:]):
        evaluation_merged = evaluation_merged.merge(
            score_df[[DATE_COL, basis.score_column]],
            on=DATE_COL,
            how="inner",
        )
    if evaluation_merged.empty:
        raise ValueError("Expanded evaluation strategy-space matrix is empty after merging.")

    feature_columns = [basis.score_column for basis in updated_bases]
    keep_cols = [DATE_COL, TARGET_RETURN_COL, TARGET_DIRECTION_COL, *feature_columns]

    return ExpandedStrategySpaceBundle(
        selection_df=selection_merged[keep_cols].sort_values(DATE_COL).reset_index(drop=True),
        evaluation_df=evaluation_merged[keep_cols].sort_values(DATE_COL).reset_index(drop=True),
        feature_columns=feature_columns,
        bases=updated_bases,
        target_horizon_days=target_horizon_days,
    )
