from datetime import date
from pathlib import Path

import pandas as pd

from walk_forward import report


def _sample_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "status": "ok",
                "ticker": "RTS",
                "model_dir": "model_a",
                "sentiment_model": "model:a",
                "source_date": "2026-04-01",
                "trades": 1,
                "pnl": 10,
                "skip_reason": "",
                "error": "",
            },
            {
                "status": "ok",
                "ticker": "RTS",
                "model_dir": "model_a",
                "sentiment_model": "model:a",
                "source_date": "2026-04-02",
                "trades": 1,
                "pnl": -4,
                "skip_reason": "",
                "error": "",
            },
            {
                "status": "ok",
                "ticker": "RTS",
                "model_dir": "model_b",
                "sentiment_model": "model:b",
                "source_date": "2026-04-01",
                "trades": 1,
                "pnl": 20,
                "skip_reason": "",
                "error": "",
            },
            {
                "status": "skipped",
                "ticker": "MIX",
                "model_dir": "model_c",
                "sentiment_model": "model:c",
                "source_date": "2026-04-01",
                "trades": 0,
                "pnl": 0,
                "skip_reason": "insufficient_train_rows",
                "error": "",
            },
        ]
    )


def _sample_trades() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "RTS",
                "model_dir": "model_a",
                "sentiment_model": "model:a",
                "source_date": date(2026, 4, 1),
                "pnl": 10.0,
                "direction": "LONG",
                "action": "follow",
                "sentiment": 1.0,
            },
            {
                "ticker": "RTS",
                "model_dir": "model_a",
                "sentiment_model": "model:a",
                "source_date": date(2026, 4, 2),
                "pnl": -4.0,
                "direction": "SHORT",
                "action": "invert",
                "sentiment": -1.0,
            },
            {
                "ticker": "RTS",
                "model_dir": "model_b",
                "sentiment_model": "model:b",
                "source_date": date(2026, 4, 1),
                "pnl": 20.0,
                "direction": "LONG",
                "action": "follow",
                "sentiment": 2.0,
            },
            {
                "ticker": "RTS",
                "model_dir": "model_b",
                "sentiment_model": "model:b",
                "source_date": date(2026, 4, 2),
                "pnl": 5.0,
                "direction": "LONG",
                "action": "follow",
                "sentiment": 2.0,
            },
        ]
    )


def test_build_leaderboard_scores_models_by_ticker() -> None:
    leaderboard = report.build_leaderboard(_sample_summary(), _sample_trades())
    rts = leaderboard[leaderboard["ticker"] == "RTS"].reset_index(drop=True)

    assert rts["model_dir"].tolist() == ["model_b", "model_a"]
    assert rts.loc[0, "rank"] == 1
    assert rts.loc[0, "trades"] == 2
    assert rts.loc[0, "total_pnl"] == 25.0
    assert rts.loc[0, "winrate"] == 100.0
    assert rts.loc[1, "profit_factor"] == 2.5


def test_build_ticker_summary_selects_best_model() -> None:
    leaderboard = report.build_leaderboard(_sample_summary(), _sample_trades())
    ticker_summary = report.build_ticker_summary(leaderboard)

    row = ticker_summary[ticker_summary["ticker"] == "RTS"].iloc[0]
    assert row["models"] == 2
    assert row["best_model"] == "model_b"
    assert row["total_pnl"] == 31.0


def test_build_monthly_and_daily_matrices() -> None:
    trades = _sample_trades()

    monthly = report.build_monthly_matrix(trades)
    daily = report.build_daily_matrix(trades)

    assert monthly.loc["RTS / model_a", "2026-04"] == 6.0
    assert monthly.loc["RTS / model_b", "2026-04"] == 25.0
    assert daily.loc["RTS / model_a", "2026-04-01"] == 10.0
    assert daily.loc["RTS / model_a", "2026-04-02"] == -4.0


def test_load_all_trades_records_missing_trade_file(tmp_path: Path) -> None:
    model_dir = tmp_path / "RTS" / "model_a"
    model_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "ticker": "RTS",
                "model_dir": "model_a",
                "sentiment_model": "model:a",
                "source_date": "2026-04-01",
                "pnl": 1,
            }
        ]
    ).to_csv(model_dir / "trades.csv", index=False)
    summary = pd.DataFrame(
        [
            {"ticker": "RTS", "model_dir": "model_a", "sentiment_model": "model:a", "status": "ok"},
            {"ticker": "RTS", "model_dir": "missing", "sentiment_model": "missing", "status": "ok"},
        ]
    )

    trades, errors = report.load_all_trades(tmp_path, summary)

    assert len(trades) == 1
    assert errors.iloc[0]["model_dir"] == "missing"
    assert "trades.csv" in errors.iloc[0]["error"]
