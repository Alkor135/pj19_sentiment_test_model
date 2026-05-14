from datetime import date

import pandas as pd

from oos import core


def test_leave_one_month_out_keeps_future_rows_in_training() -> None:
    indexed = pd.DataFrame(
        {
            "sentiment": [1, 2, 3, 4],
            "next_body": [10, 20, 30, 40],
        },
        index=[
            date(2025, 9, 30),
            date(2025, 10, 1),
            date(2025, 10, 31),
            date(2025, 11, 1),
        ],
    )

    train, test = core.split_leave_one_month_out(indexed, "2025-10")

    assert train.index.tolist() == [date(2025, 9, 30), date(2025, 11, 1)]
    assert test.index.tolist() == [date(2025, 10, 1), date(2025, 10, 31)]


def test_rules_are_built_from_non_test_month_and_applied_to_test_month() -> None:
    indexed = pd.DataFrame(
        {
            "sentiment": [1, 1, -1, -1, 1, -1],
            "next_body": [10, 20, 10, 15, 5, -7],
        },
        index=[
            date(2025, 9, 15),
            date(2025, 11, 15),
            date(2025, 9, 16),
            date(2025, 11, 16),
            date(2025, 10, 2),
            date(2025, 10, 3),
        ],
    )
    train, test = core.split_leave_one_month_out(indexed, "2025-10")

    grouped = core.group_by_sentiment(core.build_follow_trades(train, quantity=1))
    rules = core.build_rules_recommendation(grouped)
    result = core.build_backtest(test, quantity=1, rules=rules)

    by_sentiment = {rule["min"]: rule["action"] for rule in rules}
    assert by_sentiment[1] == "follow"
    assert by_sentiment[-1] == "invert"
    assert result["pnl"].tolist() == [5.0, -7.0]
    assert result["action"].tolist() == ["follow", "invert"]


def test_month_result_writes_only_inside_requested_output_dir(tmp_path) -> None:
    indexed = pd.DataFrame(
        {
            "sentiment": [1, -1, 1],
            "next_body": [20, 10, 5],
        },
        index=[
            date(2025, 9, 15),
            date(2025, 11, 15),
            date(2025, 10, 2),
        ],
    )

    summary = core.run_oos_month(
        indexed=indexed,
        quantity=1,
        ticker="RTS",
        model_dir="gemma3_12b",
        sentiment_model="gemma3:12b",
        month="2025-10",
        output_dir=tmp_path,
    )

    month_dir = tmp_path / "RTS" / "gemma3_12b" / "2025-10"
    assert summary["status"] == "ok"
    assert summary["ticker"] == "RTS"
    assert summary["model_dir"] == "gemma3_12b"
    assert summary["month"] == "2025-10"
    assert (month_dir / "group_stats.xlsx").exists()
    assert (month_dir / "rules.yaml").exists()
    assert (month_dir / "backtest.xlsx").exists()
    assert (month_dir / "summary.json").exists()
