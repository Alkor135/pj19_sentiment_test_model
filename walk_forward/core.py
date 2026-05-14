from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd


SENTIMENT_RANGE = range(-10, 11)
VALID_ACTIONS = {"follow", "invert", "skip"}


@dataclass
class WalkForwardDayResult:
    summary: dict[str, Any]
    trade: dict[str, Any] | None
    grouped: pd.DataFrame | None
    rules: list[dict[str, Any]] | None


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


def build_follow_trades(aggregated: pd.DataFrame, quantity: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for source_date, row in aggregated.iterrows():
        sentiment = float(row["sentiment"])
        next_body = float(row["next_body"])
        direction = "LONG" if sentiment >= 0 else "SHORT"
        pnl = next_body * quantity if direction == "LONG" else -next_body * quantity
        rows.append(
            {
                "source_date": source_date,
                "sentiment": sentiment,
                "direction": direction,
                "next_body": next_body,
                "pnl": pnl,
            }
        )
    return pd.DataFrame(rows)


def group_by_sentiment(trades: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        trades.groupby("sentiment")
        .agg(
            count_pos=("pnl", lambda s: int((s > 0).sum())),
            count_neg=("pnl", lambda s: int((s < 0).sum())),
            total_pnl=("pnl", "sum"),
            trades=("pnl", "size"),
        )
        .reset_index()
    )
    full = pd.DataFrame({"sentiment": [float(s) for s in SENTIMENT_RANGE]})
    grouped = full.merge(grouped, on="sentiment", how="left").fillna(
        {"count_pos": 0, "count_neg": 0, "total_pnl": 0.0, "trades": 0}
    )
    for col in ("count_pos", "count_neg", "trades"):
        grouped[col] = grouped[col].astype(int)
    return grouped.sort_values("sentiment").reset_index(drop=True)


def _action_from_total_pnl(total_pnl: float) -> str:
    return "follow" if total_pnl > 0 else "invert"


def recommend_action(total_pnl_by_sentiment: pd.Series, sentiment: int) -> str:
    total_pnl = float(total_pnl_by_sentiment.loc[sentiment])
    if total_pnl > 0:
        return "follow"
    if total_pnl < 0:
        return "invert"

    for distance in range(1, len(SENTIMENT_RANGE)):
        left_sentiment = sentiment - distance
        right_sentiment = sentiment + distance
        left_value = None
        right_value = None

        if left_sentiment in total_pnl_by_sentiment.index:
            candidate = float(total_pnl_by_sentiment.loc[left_sentiment])
            if candidate != 0:
                left_value = candidate
        if right_sentiment in total_pnl_by_sentiment.index:
            candidate = float(total_pnl_by_sentiment.loc[right_sentiment])
            if candidate != 0:
                right_value = candidate

        if left_value is None and right_value is None:
            continue
        if left_value is None:
            return _action_from_total_pnl(right_value)
        if right_value is None:
            return _action_from_total_pnl(left_value)
        if abs(left_value) > abs(right_value):
            return _action_from_total_pnl(left_value)
        if abs(right_value) > abs(left_value):
            return _action_from_total_pnl(right_value)
        continue

    raise ValueError("Невозможно определить рекомендацию: все значения total_pnl равны 0.")


def build_rules_recommendation(grouped: pd.DataFrame) -> list[dict[str, int | str]]:
    total_pnl_by_sentiment = grouped.copy()
    total_pnl_by_sentiment["sentiment"] = total_pnl_by_sentiment["sentiment"].astype(int)
    total_pnl = total_pnl_by_sentiment.set_index("sentiment")["total_pnl"]
    return [
        {
            "min": sentiment,
            "max": sentiment,
            "action": recommend_action(total_pnl, sentiment),
        }
        for sentiment in SENTIMENT_RANGE
    ]


def match_action(sentiment: float, rules: list[dict[str, Any]]) -> str:
    for rule in rules:
        if float(rule["min"]) <= sentiment <= float(rule["max"]):
            action = str(rule["action"])
            if action not in VALID_ACTIONS:
                raise ValueError(f"Некорректное action в rules: {action}")
            return action
    return "skip"


def direction_for_action(sentiment: float, action: str) -> str:
    if action == "follow":
        return "LONG" if sentiment >= 0 else "SHORT"
    return "SHORT" if sentiment >= 0 else "LONG"


def build_backtest(
    aggregated: pd.DataFrame,
    quantity: int,
    rules: list[dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for source_date, row in aggregated.iterrows():
        sentiment = float(row["sentiment"])
        next_body = float(row["next_body"])

        action = match_action(sentiment, rules)
        if action == "skip":
            continue
        direction = direction_for_action(sentiment, action)

        pnl = next_body * quantity if direction == "LONG" else -next_body * quantity

        rows.append(
            {
                "source_date": source_date,
                "sentiment": sentiment,
                "action": action,
                "direction": direction,
                "next_body": next_body,
                "quantity": quantity,
                "pnl": pnl,
            }
        )

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows).sort_values("source_date").reset_index(drop=True)
    result["cum_pnl"] = result["pnl"].cumsum()
    return result


def _base_summary(
    *,
    ticker: str,
    model_dir: str,
    sentiment_model: str,
    test_date: date,
    train_start: date,
    train_end: date,
    train_rows: int,
    test_rows: int,
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "model_dir": model_dir,
        "sentiment_model": sentiment_model,
        "source_date": test_date,
        "train_start": train_start,
        "train_end": train_end,
        "train_rows": int(train_rows),
        "test_rows": int(test_rows),
        "status": "",
        "skip_reason": "",
        "error": "",
        "trades": 0,
        "pnl": 0.0,
    }


def run_walk_forward_day(
    *,
    indexed: pd.DataFrame,
    ticker: str,
    model_dir: str,
    sentiment_model: str,
    quantity: int,
    test_date: date,
    train_months: int,
    min_train_rows: int,
) -> WalkForwardDayResult:
    train_start, train_end = training_window_for(test_date, train_months)
    train, test = split_walk_forward_day(
        indexed,
        test_date=test_date,
        train_months=train_months,
    )
    summary = _base_summary(
        ticker=ticker,
        model_dir=model_dir,
        sentiment_model=sentiment_model,
        test_date=test_date,
        train_start=train_start,
        train_end=train_end,
        train_rows=len(train),
        test_rows=len(test),
    )

    if test.empty:
        summary["status"] = "skipped"
        summary["skip_reason"] = "no_test_row"
        return WalkForwardDayResult(summary, None, None, None)

    if len(train) < min_train_rows:
        summary["status"] = "skipped"
        summary["skip_reason"] = "insufficient_train_rows"
        return WalkForwardDayResult(summary, None, None, None)

    try:
        grouped = group_by_sentiment(build_follow_trades(train, quantity))
        rules = build_rules_recommendation(grouped)
        result = build_backtest(test, quantity, rules)
    except Exception as exc:
        summary["status"] = "skipped"
        summary["skip_reason"] = "rules_unavailable"
        summary["error"] = str(exc)
        return WalkForwardDayResult(summary, None, None, None)

    if result.empty:
        summary["status"] = "skipped"
        summary["skip_reason"] = "no_trade"
        return WalkForwardDayResult(summary, None, grouped, rules)

    trade = result.iloc[0].to_dict()
    summary["status"] = "ok"
    summary["trades"] = 1
    summary["pnl"] = float(trade["pnl"])
    return WalkForwardDayResult(summary, trade, grouped, rules)
