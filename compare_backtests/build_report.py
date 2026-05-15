from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


TICKER_MAP: dict[str, str] = {
    "rts": "RTS",
    "mix": "MIX",
    "ng": "NG",
    "si": "Si",
    "spyf": "SPYF",
}

DEFAULT_WALK_RESULTS_DIR = Path("walk_forward/results")
DEFAULT_OUTPUT_HTML = Path("compare_backtests/results/backtest_vs_walk_forward.html")


@dataclass(frozen=True)
class ComparisonPair:
    ticker_lc: str
    walk_ticker: str
    model_dir: str
    ordinary_path: Path
    walk_path: Path


@dataclass
class PairComparison:
    pair: ComparisonPair
    ordinary: pd.DataFrame
    walk: pd.DataFrame
    metrics: dict[str, Any]
    error: str | None = None


REQUIRED_COLUMNS = {
    "source_date",
    "sentiment",
    "action",
    "direction",
    "next_body",
    "quantity",
    "pnl",
    "cum_pnl",
}


def walk_ticker_for(ticker_lc: str) -> str:
    key = ticker_lc.lower()
    if key not in TICKER_MAP:
        raise KeyError(f"Неизвестный тикер: {ticker_lc}")
    return TICKER_MAP[key]


def discover_pairs(
    *,
    root: Path,
    walk_results_dir: Path,
    tickers: list[str] | None = None,
    models: list[str] | None = None,
) -> list[ComparisonPair]:
    selected_tickers = [item.lower() for item in tickers] if tickers else sorted(TICKER_MAP)
    selected_models = set(models or [])
    pairs: list[ComparisonPair] = []

    for ticker_lc in selected_tickers:
        walk_ticker = walk_ticker_for(ticker_lc)
        ticker_dir = walk_results_dir / walk_ticker
        if not ticker_dir.exists():
            continue
        for model_path in sorted(item for item in ticker_dir.iterdir() if item.is_dir()):
            if selected_models and model_path.name not in selected_models:
                continue
            walk_path = model_path / "trades.xlsx"
            ordinary_path = root / ticker_lc / model_path.name / "backtest" / "sentiment_backtest_results.xlsx"
            pairs.append(
                ComparisonPair(
                    ticker_lc=ticker_lc,
                    walk_ticker=walk_ticker,
                    model_dir=model_path.name,
                    ordinary_path=ordinary_path,
                    walk_path=walk_path,
                )
            )

    return sorted(pairs, key=lambda item: (item.ticker_lc, item.model_dir))


def normalize_trades(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    missing = REQUIRED_COLUMNS - set(result.columns)
    if missing:
        raise ValueError(f"Нет обязательных колонок: {sorted(missing)}")

    result["source_date"] = pd.to_datetime(result["source_date"], errors="coerce").dt.date
    for column in ("sentiment", "next_body", "quantity", "pnl"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["action"] = result["action"].fillna("").astype(str)
    result["direction"] = result["direction"].fillna("").astype(str)
    result = result.dropna(subset=["source_date", "pnl"]).sort_values("source_date").reset_index(drop=True)
    return result


def _max_drawdown(cum_pnl: pd.Series) -> float:
    if cum_pnl.empty:
        return 0.0
    drawdown = cum_pnl - cum_pnl.cummax()
    return float(drawdown.min())


def _win_rate(pnl: pd.Series) -> float:
    if pnl.empty:
        return 0.0
    return float((pnl > 0).mean() * 100)


def _signal_match_rate(ordinary: pd.DataFrame, walk: pd.DataFrame) -> float:
    if ordinary.empty:
        return 0.0
    matches = (
        (ordinary["action"].reset_index(drop=True) == walk["action"].reset_index(drop=True))
        & (ordinary["direction"].reset_index(drop=True) == walk["direction"].reset_index(drop=True))
    )
    return float(matches.mean() * 100)


def prepare_comparison(
    *,
    pair: ComparisonPair,
    ordinary: pd.DataFrame,
    walk: pd.DataFrame,
) -> PairComparison:
    ordinary_norm = normalize_trades(ordinary)
    walk_norm = normalize_trades(walk)
    overlap = sorted(set(ordinary_norm["source_date"]) & set(walk_norm["source_date"]))
    if not overlap:
        return PairComparison(pair, pd.DataFrame(), pd.DataFrame(), {}, "Нет пересекающихся дат")

    ordinary_overlap = (
        ordinary_norm[ordinary_norm["source_date"].isin(overlap)]
        .sort_values("source_date")
        .reset_index(drop=True)
    )
    walk_overlap = (
        walk_norm[walk_norm["source_date"].isin(overlap)]
        .sort_values("source_date")
        .reset_index(drop=True)
    )
    ordinary_overlap["pnl"] = ordinary_overlap["pnl"].astype(float)
    walk_overlap["pnl"] = walk_overlap["pnl"].astype(float)
    ordinary_overlap["cum_pnl"] = ordinary_overlap["pnl"].cumsum()
    walk_overlap["cum_pnl"] = walk_overlap["pnl"].cumsum()

    ordinary_total_pnl = float(ordinary_overlap["pnl"].sum())
    walk_total_pnl = float(walk_overlap["pnl"].sum())
    metrics = {
        "ticker": pair.walk_ticker,
        "ticker_lc": pair.ticker_lc,
        "model_dir": pair.model_dir,
        "start_date": overlap[0],
        "end_date": overlap[-1],
        "overlap_rows": len(overlap),
        "ordinary_total_pnl": ordinary_total_pnl,
        "walk_total_pnl": walk_total_pnl,
        "delta_pnl": float(walk_total_pnl - ordinary_total_pnl),
        "ordinary_max_drawdown": _max_drawdown(ordinary_overlap["cum_pnl"]),
        "walk_max_drawdown": _max_drawdown(walk_overlap["cum_pnl"]),
        "ordinary_win_rate": _win_rate(ordinary_overlap["pnl"]),
        "walk_win_rate": _win_rate(walk_overlap["pnl"]),
        "signal_match_rate": _signal_match_rate(ordinary_overlap, walk_overlap),
    }
    return PairComparison(pair, ordinary_overlap, walk_overlap, metrics)
