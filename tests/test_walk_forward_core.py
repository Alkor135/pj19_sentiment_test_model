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
            date(2024, 10, 1),
            date(2024, 10, 2),
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
