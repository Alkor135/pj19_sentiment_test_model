from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def training_window_for(test_date: date, train_months: int) -> tuple[date, date]:
    if train_months < 1:
        raise ValueError("train_months должен быть >= 1")
    start = (pd.Timestamp(test_date) - pd.DateOffset(months=train_months)).date()
    end = test_date - timedelta(days=1)
    return start, end


def split_walk_forward_day(
    indexed: pd.DataFrame,
    *,
    test_date: date,
    train_months: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_start, train_end = training_window_for(test_date, train_months)
    train_mask = (indexed.index >= train_start) & (indexed.index <= train_end)
    test_mask = indexed.index == test_date
    return indexed.loc[train_mask].copy(), indexed.loc[test_mask].copy()


def iter_test_dates(
    indexed: pd.DataFrame,
    *,
    start_date: date,
    end_date: date | None,
) -> list[date]:
    if indexed.empty:
        return []
    last_date = max(indexed.index)
    effective_end = end_date or last_date
    return [
        source_date
        for source_date in indexed.index
        if start_date <= source_date <= effective_end
    ]
