from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
