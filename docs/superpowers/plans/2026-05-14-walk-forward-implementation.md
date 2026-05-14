# Walk-Forward Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Построить изолированный дневной walk-forward бэктест, который читает готовые `sentiment_scores.pkl` и пишет результаты только в `walk_forward/results/`.

**Architecture:** Новый пакет `walk_forward/` содержит чистую логику расчёта, настройки и CLI runner. Расчёт переиспользует безопасные функции из `oos.core`, но не запускает скрипты из модельных папок, потому что они пишут рабочие артефакты.

**Tech Stack:** Python 3.13, pandas, PyYAML, Typer, openpyxl, pytest, существующие тикерные `settings.yaml`.

---

## File Structure

- Create: `walk_forward/__init__.py`
  - Маркер пакета и короткое описание.
- Create: `walk_forward/settings.yaml`
  - Конфиг по умолчанию: тикеры, модели, дата старта, `train_months`, output-директория и режимы ошибок.
- Create: `walk_forward/core.py`
  - Date-window функции, дневной walk-forward расчёт, summary/trade aggregation, запись output-файлов.
- Create: `walk_forward/run_walk_forward.py`
  - Typer CLI, загрузка настроек, discovery моделей, запуск по тикерам/моделям.
- Create: `walk_forward/README.md`
  - Команды запуска и описание артефактов.
- Modify: `.gitignore`
  - Добавить `walk_forward/results/`.
- Create: `tests/test_walk_forward_core.py`
  - Unit-тесты окон дат, дневного расчёта и записи артефактов.
- Create: `tests/test_walk_forward_runner.py`
  - Unit-тесты merge настроек, discovery моделей и CLI override helper-функций.

---

### Task 1: Core Date Windows

**Files:**
- Create: `walk_forward/__init__.py`
- Create: `walk_forward/core.py`
- Test: `tests/test_walk_forward_core.py`

- [ ] **Step 1: Write failing tests for rolling date windows**

Create `tests/test_walk_forward_core.py` with:

```python
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
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_core.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'walk_forward'` or missing functions from `walk_forward.core`.

- [ ] **Step 3: Create minimal package and date-window implementation**

Create `walk_forward/__init__.py`:

```python
"""Daily walk-forward backtest package."""
```

Create `walk_forward/core.py` with:

```python
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
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_core.py -v
```

Expected: PASS for 3 tests.

- [ ] **Step 5: Commit**

Run:

```powershell
git add walk_forward\__init__.py walk_forward\core.py tests\test_walk_forward_core.py
git commit -m "Add walk-forward date windows"
```

---

### Task 2: Daily Walk-Forward Calculation

**Files:**
- Modify: `walk_forward/core.py`
- Modify: `tests/test_walk_forward_core.py`

- [ ] **Step 1: Add failing tests for daily calculation and skipped days**

Append to `tests/test_walk_forward_core.py`:

```python
def test_run_walk_forward_day_builds_rules_from_training_only() -> None:
    indexed = pd.DataFrame(
        {
            "sentiment": [1, -1, -1, 1],
            "next_body": [10, 10, 7, -1000],
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
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_core.py -v
```

Expected: FAIL with missing `run_walk_forward_day`.

- [ ] **Step 3: Implement daily calculation**

Extend `walk_forward/core.py`:

```python
from dataclasses import dataclass
from typing import Any

from oos.core import (
    build_backtest,
    build_follow_trades,
    build_rules_recommendation,
    group_by_sentiment,
)


@dataclass
class WalkForwardDayResult:
    summary: dict[str, Any]
    trade: dict[str, Any] | None
    grouped: pd.DataFrame | None
    rules: list[dict[str, Any]] | None


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
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_core.py -v
```

Expected: PASS for 5 tests.

- [ ] **Step 5: Commit**

Run:

```powershell
git add walk_forward\core.py tests\test_walk_forward_core.py
git commit -m "Add walk-forward daily calculation"
```

---

### Task 3: Model Aggregation And Artifact Writing

**Files:**
- Modify: `walk_forward/core.py`
- Modify: `tests/test_walk_forward_core.py`

- [ ] **Step 1: Add failing tests for model run aggregation and output isolation**

Append to `tests/test_walk_forward_core.py`:

```python
def test_run_walk_forward_model_returns_daily_summaries_and_trades() -> None:
    indexed = pd.DataFrame(
        {
            "sentiment": [1, -1, -1, 1],
            "next_body": [10, 10, 7, 5],
        },
        index=[
            date(2024, 10, 1),
            date(2024, 10, 2),
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
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_core.py -v
```

Expected: FAIL with missing `run_walk_forward_model` and `save_model_outputs`.

- [ ] **Step 3: Implement aggregation and output writers**

Extend `walk_forward/core.py`:

```python
import json
from pathlib import Path


@dataclass
class WalkForwardModelResult:
    daily_summaries: list[dict[str, Any]]
    trades: pd.DataFrame
    model_summary: dict[str, Any]
    daily_artifacts: dict[date, WalkForwardDayResult]


def summarize_model(
    *,
    ticker: str,
    model_dir: str,
    sentiment_model: str,
    daily_summaries: list[dict[str, Any]],
    trades: pd.DataFrame,
) -> dict[str, Any]:
    ok_days = sum(1 for row in daily_summaries if row["status"] == "ok")
    skipped_days = sum(1 for row in daily_summaries if row["status"] == "skipped")
    error_days = sum(1 for row in daily_summaries if row["status"] == "error")
    total_pnl = float(trades["pnl"].sum()) if not trades.empty else 0.0
    winrate = float((trades["pnl"] > 0).mean() * 100) if not trades.empty else 0.0
    max_drawdown = 0.0
    if not trades.empty:
        cum = trades["pnl"].cumsum()
        max_drawdown = float((cum - cum.cummax()).min())
    status = "ok" if error_days == 0 else "error"
    return {
        "ticker": ticker,
        "model_dir": model_dir,
        "sentiment_model": sentiment_model,
        "status": status,
        "days": len(daily_summaries),
        "ok_days": ok_days,
        "skipped_days": skipped_days,
        "error_days": error_days,
        "trades": int(len(trades)),
        "total_pnl": total_pnl,
        "winrate": winrate,
        "max_drawdown": max_drawdown,
    }


def run_walk_forward_model(
    *,
    indexed: pd.DataFrame,
    ticker: str,
    model_dir: str,
    sentiment_model: str,
    quantity: int,
    start_date: date,
    end_date: date | None,
    train_months: int,
    min_train_rows: int,
) -> WalkForwardModelResult:
    daily_summaries: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    daily_artifacts: dict[date, WalkForwardDayResult] = {}

    for test_date in iter_test_dates(indexed, start_date=start_date, end_date=end_date):
        day = run_walk_forward_day(
            indexed=indexed,
            ticker=ticker,
            model_dir=model_dir,
            sentiment_model=sentiment_model,
            quantity=quantity,
            test_date=test_date,
            train_months=train_months,
            min_train_rows=min_train_rows,
        )
        daily_summaries.append(day.summary)
        daily_artifacts[test_date] = day
        if day.trade is not None:
            row = dict(day.trade)
            row["ticker"] = ticker
            row["model_dir"] = model_dir
            row["sentiment_model"] = sentiment_model
            row["train_start"] = day.summary["train_start"]
            row["train_end"] = day.summary["train_end"]
            row["train_rows"] = day.summary["train_rows"]
            trade_rows.append(row)

    trades = pd.DataFrame(trade_rows)
    if not trades.empty:
        trades = trades.sort_values("source_date").reset_index(drop=True)
        trades["cum_pnl"] = trades["pnl"].cumsum()

    model_summary = summarize_model(
        ticker=ticker,
        model_dir=model_dir,
        sentiment_model=sentiment_model,
        daily_summaries=daily_summaries,
        trades=trades,
    )
    return WalkForwardModelResult(daily_summaries, trades, model_summary, daily_artifacts)


def _json_default(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def save_model_outputs(
    *,
    output_dir: Path,
    ticker: str,
    model_dir: str,
    daily_summaries: list[dict[str, Any]],
    trades: pd.DataFrame,
    model_summary: dict[str, Any],
    save_daily_artifacts: bool,
    daily_artifacts: dict[date, WalkForwardDayResult],
) -> None:
    target = output_dir / ticker / model_dir
    target.mkdir(parents=True, exist_ok=True)
    trades.to_csv(target / "trades.csv", index=False, encoding="utf-8-sig")
    trades.to_excel(target / "trades.xlsx", index=False)
    (target / "summary.json").write_text(
        json.dumps(model_summary, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    if save_daily_artifacts:
        for test_date, day in daily_artifacts.items():
            if day.grouped is None or day.rules is None:
                continue
            daily_dir = target / "daily" / test_date.isoformat()
            daily_dir.mkdir(parents=True, exist_ok=True)
            day.grouped.to_excel(daily_dir / "group_stats.xlsx", index=False)
            (daily_dir / "rules.yaml").write_text(
                render_rules_yaml(
                    day.rules,
                    ticker=ticker,
                    sentiment_model=str(model_summary["sentiment_model"]),
                    test_date=test_date,
                    train_start=day.summary["train_start"],
                    train_end=day.summary["train_end"],
                ),
                encoding="utf-8",
            )


def save_global_summary(output_dir: Path, summaries: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_df = pd.DataFrame(summaries)
    summary_df.to_csv(output_dir / "summary.csv", index=False, encoding="utf-8-sig")
    summary_df.to_excel(output_dir / "summary.xlsx", index=False)
```

Also add:

```python
def render_rules_yaml(
    rules: list[dict[str, Any]],
    *,
    ticker: str,
    sentiment_model: str,
    test_date: date,
    train_start: date,
    train_end: date,
) -> str:
    lines = [
        (
            f"rules:  # WF {ticker} {sentiment_model} "
            f"test_date={test_date} train={train_start}..{train_end}"
        )
    ]
    for rule in rules:
        lines.append(
            f"  - {{min: {rule['min']}, max: {rule['max']}, action: {rule['action']}}}"
        )
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_core.py -v
```

Expected: PASS for 7 tests.

- [ ] **Step 5: Commit**

Run:

```powershell
git add walk_forward\core.py tests\test_walk_forward_core.py
git commit -m "Add walk-forward output writers"
```

---

### Task 4: Settings And CLI Runner

**Files:**
- Create: `walk_forward/settings.yaml`
- Create: `walk_forward/run_walk_forward.py`
- Create: `tests/test_walk_forward_runner.py`

- [ ] **Step 1: Write failing tests for settings merge and model discovery**

Create `tests/test_walk_forward_runner.py` with:

```python
from pathlib import Path

from walk_forward import run_walk_forward


def test_parse_csv_returns_default_for_empty_value() -> None:
    assert run_walk_forward.parse_csv(None, ("rts", "mix")) == ["rts", "mix"]
    assert run_walk_forward.parse_csv("", ("rts", "mix")) == ["rts", "mix"]
    assert run_walk_forward.parse_csv("rts, mix", ()) == ["rts", "mix"]


def test_merge_run_options_applies_cli_overrides(tmp_path: Path) -> None:
    settings = {
        "tickers": ["rts", "mix"],
        "models": [],
        "backtest_start_date": "2025-04-01",
        "backtest_end_date": None,
        "train_months": 6,
        "output_dir": "walk_forward/results",
        "save_daily_artifacts": False,
        "min_train_rows": 20,
        "keep_going": True,
    }

    options = run_walk_forward.merge_run_options(
        settings,
        tickers="si",
        models="gemma3_12b,qwen3_14b",
        start_date="2025-05-01",
        end_date="2025-05-31",
        train_months=3,
        output_dir=tmp_path,
        save_daily_artifacts=True,
        min_train_rows=5,
        keep_going=False,
    )

    assert options.tickers == ["si"]
    assert options.models == ["gemma3_12b", "qwen3_14b"]
    assert options.backtest_start_date.isoformat() == "2025-05-01"
    assert options.backtest_end_date.isoformat() == "2025-05-31"
    assert options.train_months == 3
    assert options.output_dir == tmp_path
    assert options.save_daily_artifacts is True
    assert options.min_train_rows == 5
    assert options.keep_going is False


def test_load_model_settings_merges_common_defaults_and_model_overrides() -> None:
    raw = {
        "common": {"ticker": "RTS", "ticker_lc": "rts", "quantity_test": 2},
        "model_defaults": {
            "sentiment_output_pkl": "{ticker_lc}/{model_dir}/sentiment_scores.pkl",
            "sentiment_model": "{model_dir}",
        },
        "models": {
            "gemma3_12b": {
                "sentiment_model": "gemma3:12b",
                "quantity_test": 3,
            }
        },
    }

    settings = run_walk_forward.build_model_settings(raw, "gemma3_12b")

    assert settings["ticker"] == "RTS"
    assert settings["quantity_test"] == 3
    assert settings["sentiment_model"] == "gemma3:12b"
    assert settings["sentiment_output_pkl"] == "rts/gemma3_12b/sentiment_scores.pkl"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_runner.py -v
```

Expected: FAIL with missing `walk_forward.run_walk_forward`.

- [ ] **Step 3: Add default settings**

Create `walk_forward/settings.yaml`:

```yaml
tickers: [rts, mix, ng, si, spyf]
models: []
backtest_start_date: "2025-04-01"
backtest_end_date: null
train_months: 6
output_dir: "walk_forward/results"
save_daily_artifacts: false
min_train_rows: 20
keep_going: true
```

- [ ] **Step 4: Implement runner helpers and CLI**

Create `walk_forward/run_walk_forward.py` with:

```python
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import typer
import yaml

from oos.core import load_sentiment_pkl
from walk_forward.core import (
    run_walk_forward_model,
    save_global_summary,
    save_model_outputs,
)


ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"
DEFAULT_TICKERS = ("rts", "mix", "ng", "si", "spyf")

app = typer.Typer(help="Daily walk-forward backtest без записи в рабочие модельные папки.")


@dataclass
class RunOptions:
    tickers: list[str]
    models: list[str]
    backtest_start_date: pd.Timestamp
    backtest_end_date: pd.Timestamp | None
    train_months: int
    output_dir: Path
    save_daily_artifacts: bool
    min_train_rows: int
    keep_going: bool


def parse_csv(value: Optional[str], default: tuple[str, ...] = ()) -> list[str]:
    if value is None or value.strip() == "":
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def apply_template_values(settings: dict[str, Any], model_dir: str) -> dict[str, Any]:
    ticker = str(settings.get("ticker", ""))
    ticker_lc = str(settings.get("ticker_lc", ticker.lower()))
    out = deepcopy(settings)
    replacements = {
        "{ticker}": ticker,
        "{ticker_lc}": ticker_lc,
        "{model_dir}": model_dir,
    }
    for key, value in list(out.items()):
        if isinstance(value, str):
            for old, new in replacements.items():
                value = value.replace(old, new)
            out[key] = value
    return out


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"YAML не найден: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_ticker_settings(ticker_lc: str) -> dict[str, Any]:
    return load_yaml(ROOT / ticker_lc / "settings.yaml")


def discover_models(raw_ticker_settings: dict[str, Any]) -> list[str]:
    return sorted((raw_ticker_settings.get("models") or {}).keys())


def build_model_settings(raw_ticker_settings: dict[str, Any], model_dir: str) -> dict[str, Any]:
    settings = deep_merge(raw_ticker_settings.get("common") or {}, raw_ticker_settings.get("model_defaults") or {})
    settings = deep_merge(settings, (raw_ticker_settings.get("models") or {}).get(model_dir) or {})
    settings["model_dir"] = model_dir
    return apply_template_values(settings, model_dir)


def merge_run_options(
    settings: dict[str, Any],
    *,
    tickers: Optional[str],
    models: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    train_months: Optional[int],
    output_dir: Optional[Path],
    save_daily_artifacts: Optional[bool],
    min_train_rows: Optional[int],
    keep_going: Optional[bool],
) -> RunOptions:
    settings_tickers = tuple(settings.get("tickers") or DEFAULT_TICKERS)
    settings_models = tuple(settings.get("models") or ())
    return RunOptions(
        tickers=parse_csv(tickers, settings_tickers),
        models=parse_csv(models, settings_models),
        backtest_start_date=pd.to_datetime(start_date or settings["backtest_start_date"]),
        backtest_end_date=pd.to_datetime(end_date or settings.get("backtest_end_date")) if (end_date or settings.get("backtest_end_date")) else None,
        train_months=int(train_months if train_months is not None else settings.get("train_months", 6)),
        output_dir=(output_dir or Path(str(settings.get("output_dir", "walk_forward/results")))).resolve(),
        save_daily_artifacts=bool(settings.get("save_daily_artifacts", False) if save_daily_artifacts is None else save_daily_artifacts),
        min_train_rows=int(min_train_rows if min_train_rows is not None else settings.get("min_train_rows", 20)),
        keep_going=bool(settings.get("keep_going", True) if keep_going is None else keep_going),
    )


def error_summary(ticker: str, model_dir: str, sentiment_model: str, error: Exception) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "model_dir": model_dir,
        "sentiment_model": sentiment_model,
        "source_date": "",
        "status": "error",
        "skip_reason": "",
        "error": str(error),
        "trades": 0,
        "pnl": 0.0,
    }


@app.command()
def main(
    tickers: Optional[str] = typer.Option(None, "--tickers", help="Тикеры через запятую."),
    models: Optional[str] = typer.Option(None, "--models", help="Модели через запятую."),
    start_date: Optional[str] = typer.Option(None, "--start-date", help="Дата начала YYYY-MM-DD."),
    end_date: Optional[str] = typer.Option(None, "--end-date", help="Дата окончания YYYY-MM-DD."),
    train_months: Optional[int] = typer.Option(None, "--train-months", help="Количество месяцев lookback."),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Папка результатов."),
    save_daily_artifacts: Optional[bool] = typer.Option(None, "--save-daily-artifacts/--no-save-daily-artifacts"),
    min_train_rows: Optional[int] = typer.Option(None, "--min-train-rows", help="Минимум строк обучения."),
    keep_going: Optional[bool] = typer.Option(None, "--keep-going/--stop-on-error"),
) -> None:
    options = merge_run_options(
        load_yaml(SETTINGS_PATH),
        tickers=tickers,
        models=models,
        start_date=start_date,
        end_date=end_date,
        train_months=train_months,
        output_dir=output_dir,
        save_daily_artifacts=save_daily_artifacts,
        min_train_rows=min_train_rows,
        keep_going=keep_going,
    )

    all_summaries: list[dict[str, Any]] = []
    typer.echo(f"Walk-forward output: {options.output_dir}")

    for ticker_lc in options.tickers:
        raw_ticker_settings = load_ticker_settings(ticker_lc)
        model_dirs = options.models or discover_models(raw_ticker_settings)
        for model_dir in model_dirs:
            model_settings = build_model_settings(raw_ticker_settings, model_dir)
            ticker = str(model_settings.get("ticker", ticker_lc.upper()))
            sentiment_model = str(model_settings.get("sentiment_model", model_dir))
            sentiment_pkl = Path(str(model_settings.get("sentiment_output_pkl", "")))
            try:
                indexed = load_sentiment_pkl(sentiment_pkl)
                result = run_walk_forward_model(
                    indexed=indexed,
                    ticker=ticker,
                    model_dir=model_dir,
                    sentiment_model=sentiment_model,
                    quantity=int(model_settings.get("quantity_test", 1)),
                    start_date=options.backtest_start_date.date(),
                    end_date=options.backtest_end_date.date() if options.backtest_end_date is not None else None,
                    train_months=options.train_months,
                    min_train_rows=options.min_train_rows,
                )
                save_model_outputs(
                    output_dir=options.output_dir,
                    ticker=ticker,
                    model_dir=model_dir,
                    daily_summaries=result.daily_summaries,
                    trades=result.trades,
                    model_summary=result.model_summary,
                    save_daily_artifacts=options.save_daily_artifacts,
                    daily_artifacts=result.daily_artifacts,
                )
                all_summaries.extend(result.daily_summaries)
                typer.echo(
                    f"[OK] {ticker}/{model_dir}: "
                    f"days={result.model_summary['days']} "
                    f"trades={result.model_summary['trades']} "
                    f"pnl={result.model_summary['total_pnl']:.2f}"
                )
            except Exception as exc:
                row = error_summary(ticker, model_dir, sentiment_model, exc)
                all_summaries.append(row)
                typer.echo(f"[ERROR] {ticker}/{model_dir}: {exc}")
                if not options.keep_going:
                    raise typer.Exit(code=1) from exc

    save_global_summary(options.output_dir, all_summaries)
    errors = sum(1 for row in all_summaries if row["status"] == "error")
    typer.echo(f"Summary: {options.output_dir / 'summary.csv'}")
    if errors:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
```

- [ ] **Step 5: Run runner tests and core tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_core.py tests\test_walk_forward_runner.py -v
```

Expected: PASS for all walk-forward tests.

- [ ] **Step 6: Commit**

Run:

```powershell
git add walk_forward\settings.yaml walk_forward\run_walk_forward.py tests\test_walk_forward_runner.py
git commit -m "Add walk-forward runner"
```

---

### Task 5: README And Gitignore

**Files:**
- Create: `walk_forward/README.md`
- Modify: `.gitignore`
- Test: `tests/test_walk_forward_runner.py`

- [ ] **Step 1: Add failing test for default settings values**

Append to `tests/test_walk_forward_runner.py`:

```python
def test_default_settings_match_approved_design() -> None:
    settings = run_walk_forward.load_yaml(run_walk_forward.SETTINGS_PATH)

    assert settings["backtest_start_date"] == "2025-04-01"
    assert settings["train_months"] == 6
    assert settings["save_daily_artifacts"] is False
    assert settings["output_dir"] == "walk_forward/results"
```

- [ ] **Step 2: Run test and verify it passes after Task 4 settings**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_runner.py::test_default_settings_match_approved_design -v
```

Expected: PASS.

- [ ] **Step 3: Add README**

Create `walk_forward/README.md`:

```markdown
# Walk-Forward Backtest

Дневной walk-forward бэктест читает готовые `sentiment_scores.pkl` из модельных настроек тикеров и пишет результаты только в `walk_forward/results/`.

## Запуск

```powershell
.venv\Scripts\python.exe -m walk_forward.run_walk_forward
```

Одна модель:

```powershell
.venv\Scripts\python.exe -m walk_forward.run_walk_forward --tickers rts --models gemma3_12b --start-date 2025-04-01 --train-months 6
```

## Логика

Для каждой тестовой даты `D` правила строятся на окне `D - train_months` .. `D - 1 день`.
Тестовый день и более поздние даты в обучение не попадают.

## Артефакты

- `walk_forward/results/summary.csv`
- `walk_forward/results/summary.xlsx`
- `walk_forward/results/<TICKER>/<model>/trades.csv`
- `walk_forward/results/<TICKER>/<model>/trades.xlsx`
- `walk_forward/results/<TICKER>/<model>/summary.json`

При `save_daily_artifacts: true` дополнительно пишутся дневные `group_stats.xlsx` и `rules.yaml`.
```

- [ ] **Step 4: Update `.gitignore`**

Add this line near generated pipeline artifacts:

```gitignore
walk_forward/results/
```

- [ ] **Step 5: Run all walk-forward tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_core.py tests\test_walk_forward_runner.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add .gitignore walk_forward\README.md tests\test_walk_forward_runner.py
git commit -m "Document walk-forward backtest"
```

---

### Task 6: Verification Run

**Files:**
- No planned source changes.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_core.py tests\test_walk_forward_runner.py -v
```

Expected: PASS.

- [ ] **Step 2: Run existing OOS tests to catch shared-logic regressions**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_oos_backtest.py tests\test_oos_report.py -v
```

Expected: PASS.

- [ ] **Step 3: Run a small real-data smoke test without daily artifacts**

Run:

```powershell
.venv\Scripts\python.exe -m walk_forward.run_walk_forward --tickers rts --models gemma3_12b --start-date 2025-04-01 --end-date 2025-04-10 --train-months 6 --no-save-daily-artifacts --keep-going
```

Expected:

```text
Walk-forward output: C:\Users\Alkor\VSCode\pj19_sentiment_test_model\walk_forward\results
[OK] RTS/gemma3_12b: ...
Summary: C:\Users\Alkor\VSCode\pj19_sentiment_test_model\walk_forward\results\summary.csv
```

If the local PKL is missing, expected result is a clear `[ERROR] RTS/gemma3_12b: sentiment PKL не найден: ...` message and no writes outside `walk_forward/results/`.

- [ ] **Step 4: Confirm artifact isolation**

Run:

```powershell
git status --short
```

Expected tracked changes after implementation commits: clean or only intended code/docs changes. Generated files under `walk_forward/results/` should be ignored.

- [ ] **Step 5: Final commit only if verification required a small fix**

If verification requires a small source or test fix, commit that fix:

```powershell
git add <changed-source-or-test-files>
git commit -m "Fix walk-forward verification issue"
```

---

## Self-Review

- Spec coverage: tasks cover the isolated package, default config, daily rolling train window, CLI, output layout, optional daily artifacts, tests, and no writes to model folders.
- Red-flag scan: this plan has no incomplete sections or vague implementation steps.
- Type consistency: planned public functions use consistent names across tests and implementation snippets: `training_window_for`, `split_walk_forward_day`, `iter_test_dates`, `run_walk_forward_day`, `run_walk_forward_model`, `save_model_outputs`, `save_global_summary`, `merge_run_options`, and `build_model_settings`.
