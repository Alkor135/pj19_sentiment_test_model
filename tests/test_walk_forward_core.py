from datetime import date

import pandas as pd

from walk_forward import core


def _indexed_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sentiment": [9, 1, -1, 2, 3],
            "next_body": [90, 10, 20, 30, 40],
        },
        index=[
            date(2024, 9, 30),
            date(2024, 10, 1),
            date(2025, 3, 31),
            date(2025, 4, 1),
            date(2025, 4, 2),
        ],
    )


def test_training_window_for_six_months_excludes_test_day() -> None:
    start, end = core.training_window_for(date(2025, 4, 1), train_months=6)

    assert start == date(2024, 10, 1)
    assert end == date(2025, 3, 31)


def test_split_walk_forward_day_uses_only_lookback_rows() -> None:
    train, test = core.split_walk_forward_day(
        _indexed_frame(),
        test_date=date(2025, 4, 1),
        train_months=6,
    )

    assert train.index.tolist() == [date(2024, 10, 1), date(2025, 3, 31)]
    assert test.index.tolist() == [date(2025, 4, 1)]


def test_iter_test_dates_uses_available_rows_inside_bounds() -> None:
    dates = core.iter_test_dates(
        _indexed_frame(),
        start_date=date(2025, 4, 1),
        end_date=date(2025, 4, 30),
    )

    assert dates == [date(2025, 4, 1), date(2025, 4, 2)]


def test_run_walk_forward_day_builds_rules_from_training_only() -> None:
    indexed = pd.DataFrame(
        {
            "sentiment": [1, -1, -1, 1],
            "next_body": [10, 12, 7, -1000],
        },
        index=[
            date(2024, 10, 2),
            date(2024, 10, 3),
            date(2025, 4, 1),
            date(2025, 4, 2),
        ],
    )

    day = core.run_walk_forward_day(
        indexed=indexed,
        ticker="RTS",
        model_dir="gemma3_12b",
        sentiment_model="gemma3:12b",
        quantity=1,
        test_date=date(2025, 4, 1),
        train_months=6,
        min_train_rows=2,
    )

    assert day.summary["status"] == "ok"
    assert day.summary["train_rows"] == 2
    assert day.trade is not None
    assert day.trade["source_date"] == date(2025, 4, 1)
    assert day.trade["action"] == "invert"
    assert day.trade["direction"] == "LONG"
    assert day.trade["pnl"] == 7.0
    assert day.rules is not None
    assert all(rule["action"] in {"follow", "invert"} for rule in day.rules)
    sentiment_zero_rule = next(rule for rule in day.rules if rule["min"] == 0)
    assert sentiment_zero_rule["action"] != "skip"


def test_run_walk_forward_day_skips_when_training_rows_are_insufficient() -> None:
    indexed = pd.DataFrame(
        {"sentiment": [1, -1], "next_body": [10, 7]},
        index=[date(2024, 10, 1), date(2025, 4, 1)],
    )

    day = core.run_walk_forward_day(
        indexed=indexed,
        ticker="RTS",
        model_dir="gemma3_12b",
        sentiment_model="gemma3:12b",
        quantity=1,
        test_date=date(2025, 4, 1),
        train_months=6,
        min_train_rows=2,
    )

    assert day.summary["status"] == "skipped"
    assert day.summary["skip_reason"] == "insufficient_train_rows"
    assert day.trade is None
    assert day.grouped is None
    assert day.rules is None


def test_run_walk_forward_model_returns_daily_summaries_and_trades() -> None:
    indexed = pd.DataFrame(
        {
            "sentiment": [1, -1, -1, 1],
            "next_body": [10, 12, 7, 5],
        },
        index=[
            date(2024, 10, 2),
            date(2024, 10, 3),
            date(2025, 4, 1),
            date(2025, 4, 2),
        ],
    )

    result = core.run_walk_forward_model(
        indexed=indexed,
        ticker="RTS",
        model_dir="gemma3_12b",
        sentiment_model="gemma3:12b",
        quantity=1,
        start_date=date(2025, 4, 1),
        end_date=date(2025, 4, 2),
        train_months=6,
        min_train_rows=2,
    )

    assert len(result.daily_summaries) == 2
    assert result.trades["source_date"].tolist() == [date(2025, 4, 1), date(2025, 4, 2)]
    assert result.model_summary["status"] == "ok"
    assert result.model_summary["days"] == 2
    assert result.model_summary["trades"] == 2
    assert result.model_summary["total_pnl"] == 12.0


def test_save_outputs_writes_only_inside_output_dir_without_daily_artifacts(tmp_path) -> None:
    summaries = [
        {
            "ticker": "RTS",
            "model_dir": "gemma3_12b",
            "sentiment_model": "gemma3:12b",
            "source_date": date(2025, 4, 1),
            "status": "ok",
            "skip_reason": "",
            "error": "",
            "trades": 1,
            "pnl": 7.0,
        }
    ]
    trades = pd.DataFrame(
        [
            {
                "source_date": date(2025, 4, 1),
                "sentiment": -1.0,
                "action": "invert",
                "direction": "LONG",
                "next_body": 7.0,
                "quantity": 1,
                "pnl": 7.0,
                "cum_pnl": 7.0,
            }
        ]
    )
    model_summary = {
        "ticker": "RTS",
        "model_dir": "gemma3_12b",
        "sentiment_model": "gemma3:12b",
        "status": "ok",
        "days": 1,
        "trades": 1,
        "total_pnl": 7.0,
        "winrate": 100.0,
        "max_drawdown": 0.0,
        "skipped_days": 0,
        "error_days": 0,
    }

    core.save_model_outputs(
        output_dir=tmp_path,
        ticker="RTS",
        model_dir="gemma3_12b",
        daily_summaries=summaries,
        trades=trades,
        model_summary=model_summary,
        save_daily_artifacts=False,
        daily_artifacts={},
    )
    core.save_global_summary(tmp_path, summaries)

    model_dir = tmp_path / "RTS" / "gemma3_12b"
    assert (tmp_path / "summary.csv").exists()
    assert (tmp_path / "summary.xlsx").exists()
    assert (model_dir / "trades.csv").exists()
    assert (model_dir / "trades.xlsx").exists()
    assert (model_dir / "summary.json").exists()
    assert not (model_dir / "daily").exists()
