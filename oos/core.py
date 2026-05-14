from __future__ import annotations

import json
import pickle
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml


SENTIMENT_RANGE = range(-10, 11)
VALID_ACTIONS = {"follow", "invert", "skip"}


def parse_month(month: str) -> tuple[date, date]:
    period = pd.Period(month, freq="M")
    return period.start_time.date(), period.end_time.date()


def normalize_sentiment_frame(df: pd.DataFrame) -> pd.DataFrame:
    required = {"source_date", "sentiment", "next_body"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Нет обязательных колонок sentiment PKL: {sorted(missing)}")

    out = df.copy()
    out["source_date"] = pd.to_datetime(out["source_date"], errors="coerce").dt.date
    out["sentiment"] = pd.to_numeric(out["sentiment"], errors="coerce")
    out["next_body"] = pd.to_numeric(out["next_body"], errors="coerce")
    out = out.dropna(subset=["source_date", "sentiment", "next_body"])

    if out["source_date"].duplicated().any():
        duplicates = sorted(out.loc[out["source_date"].duplicated(keep=False), "source_date"].unique())
        raise ValueError(f"В sentiment данных несколько строк за одну дату: {duplicates[:5]}")

    return (
        out.set_index("source_date")[["sentiment", "next_body"]]
        .sort_index()
    )


def load_sentiment_pkl(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"sentiment PKL не найден: {path}")
    with path.open("rb") as f:
        data = pickle.load(f)
    return normalize_sentiment_frame(pd.DataFrame(data))


def split_leave_one_month_out(indexed: pd.DataFrame, month: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    start, end = parse_month(month)
    test_mask = (indexed.index >= start) & (indexed.index <= end)
    return indexed.loc[~test_mask].copy(), indexed.loc[test_mask].copy()


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
    if trades.empty:
        grouped = pd.DataFrame(columns=["sentiment", "count_pos", "count_neg", "total_pnl", "trades"])
    else:
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

    raise ValueError("Невозможно построить правила: все значения total_pnl равны 0.")


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


def render_rules_yaml(rules: Iterable[dict[str, int | str]], ticker: str, sentiment_model: str, month: str) -> str:
    lines = [f"rules:  # OOS {ticker} {sentiment_model} test_month={month}"]
    for rule in rules:
        lines.append(
            f"  - {{min: {rule['min']}, max: {rule['max']}, action: {rule['action']}}}"
        )
    return "\n".join(lines) + "\n"


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


def build_backtest(aggregated: pd.DataFrame, quantity: int, rules: list[dict[str, Any]]) -> pd.DataFrame:
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
        return pd.DataFrame(columns=["source_date", "sentiment", "action", "direction", "next_body", "quantity", "pnl", "cum_pnl"])

    result = pd.DataFrame(rows).sort_values("source_date").reset_index(drop=True)
    result["cum_pnl"] = result["pnl"].cumsum()
    return result


def summarize_backtest(
    *,
    ticker: str,
    model_dir: str,
    sentiment_model: str,
    month: str,
    train_rows: int,
    test_rows: int,
    result: pd.DataFrame,
) -> dict[str, Any]:
    total_pnl = float(result["pnl"].sum()) if not result.empty else 0.0
    trades = int(len(result))
    winrate = float((result["pnl"] > 0).mean() * 100) if trades else 0.0
    max_drawdown = 0.0
    if not result.empty:
        peak = result["cum_pnl"].cummax()
        max_drawdown = float((result["cum_pnl"] - peak).min())

    return {
        "status": "ok",
        "ticker": ticker,
        "model_dir": model_dir,
        "sentiment_model": sentiment_model,
        "month": month,
        "train_rows": int(train_rows),
        "test_rows": int(test_rows),
        "trades": trades,
        "total_pnl": total_pnl,
        "winrate": winrate,
        "max_drawdown": max_drawdown,
    }


def _json_default(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def run_oos_month(
    *,
    indexed: pd.DataFrame,
    quantity: int,
    ticker: str,
    model_dir: str,
    sentiment_model: str,
    month: str,
    output_dir: Path,
) -> dict[str, Any]:
    train, test = split_leave_one_month_out(indexed, month)
    if train.empty:
        raise ValueError(f"{ticker}/{model_dir}/{month}: нет данных для построения правил")
    if test.empty:
        raise ValueError(f"{ticker}/{model_dir}/{month}: нет данных для тестового месяца")

    grouped = group_by_sentiment(build_follow_trades(train, quantity))
    rules = build_rules_recommendation(grouped)
    result = build_backtest(test, quantity, rules)
    if result.empty:
        raise ValueError(f"{ticker}/{model_dir}/{month}: правила не дали сделок")

    month_dir = output_dir / ticker / model_dir / month
    month_dir.mkdir(parents=True, exist_ok=True)
    grouped.to_excel(month_dir / "group_stats.xlsx", index=False)
    (month_dir / "rules.yaml").write_text(
        render_rules_yaml(rules, ticker, sentiment_model, month),
        encoding="utf-8",
    )
    result.to_excel(month_dir / "backtest.xlsx", index=False)

    summary = summarize_backtest(
        ticker=ticker,
        model_dir=model_dir,
        sentiment_model=sentiment_model,
        month=month,
        train_rows=len(train),
        test_rows=len(test),
        result=result,
    )
    (month_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return summary
