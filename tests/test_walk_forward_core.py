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
