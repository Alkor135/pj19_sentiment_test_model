# План Реализации Отчёта Walk-Forward

> **Для агентных исполнителей:** ОБЯЗАТЕЛЬНЫЙ ПОД-НАВЫК: используйте `superpowers:subagent-driven-development` или `superpowers:executing-plans` для выполнения этого плана по задачам. Шаги используют checkbox-синтаксис (`- [ ]`) для отслеживания.

**Цель:** добавить генератор Excel и HTML отчётов по результатам дневного walk-forward бэктеста.

**Архитектура:** новый модуль `walk_forward/report.py` читает `walk_forward/results/summary.csv` и все `trades.csv`, нормализует данные, считает leaderboard/матрицы/метрики и записывает `walk_forward_report.xlsx` и `walk_forward_report.html`. Реализация не трогает рабочие папки тикеров и моделей.

**Технологии:** Python 3.13, pandas, openpyxl, Plotly, Typer, pytest.

---

## Структура Файлов

- Создать: `walk_forward/report.py`
  - Загрузка данных, расчёт метрик, Excel writer, HTML builder, Typer CLI.
- Создать: `tests/test_walk_forward_report.py`
  - Тесты leaderboard, ticker summary, monthly/daily matrix, Excel/HTML output, missing trades handling.
- Изменить: `walk_forward/README.md`
  - Добавить команду генерации отчёта.

---

### Task 1: Данные И Leaderboard

**Файлы:**
- Создать: `tests/test_walk_forward_report.py`
- Создать: `walk_forward/report.py`

- [ ] **Шаг 1: Написать падающие тесты для загрузки сделок и leaderboard**

Создать `tests/test_walk_forward_report.py`:

```python
from datetime import date
from pathlib import Path

import pandas as pd

from walk_forward import report


def _sample_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"status": "ok", "ticker": "RTS", "model_dir": "model_a", "sentiment_model": "model:a", "source_date": "2026-04-01", "trades": 1, "pnl": 10, "skip_reason": "", "error": ""},
            {"status": "ok", "ticker": "RTS", "model_dir": "model_a", "sentiment_model": "model:a", "source_date": "2026-04-02", "trades": 1, "pnl": -4, "skip_reason": "", "error": ""},
            {"status": "ok", "ticker": "RTS", "model_dir": "model_b", "sentiment_model": "model:b", "source_date": "2026-04-01", "trades": 1, "pnl": 20, "skip_reason": "", "error": ""},
            {"status": "skipped", "ticker": "MIX", "model_dir": "model_c", "sentiment_model": "model:c", "source_date": "2026-04-01", "trades": 0, "pnl": 0, "skip_reason": "insufficient_train_rows", "error": ""},
        ]
    )


def _sample_trades() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ticker": "RTS", "model_dir": "model_a", "sentiment_model": "model:a", "source_date": date(2026, 4, 1), "pnl": 10.0, "direction": "LONG", "action": "follow", "sentiment": 1.0},
            {"ticker": "RTS", "model_dir": "model_a", "sentiment_model": "model:a", "source_date": date(2026, 4, 2), "pnl": -4.0, "direction": "SHORT", "action": "invert", "sentiment": -1.0},
            {"ticker": "RTS", "model_dir": "model_b", "sentiment_model": "model:b", "source_date": date(2026, 4, 1), "pnl": 20.0, "direction": "LONG", "action": "follow", "sentiment": 2.0},
            {"ticker": "RTS", "model_dir": "model_b", "sentiment_model": "model:b", "source_date": date(2026, 4, 2), "pnl": 5.0, "direction": "LONG", "action": "follow", "sentiment": 2.0},
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
```

- [ ] **Шаг 2: Запустить тесты и увидеть RED**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_report.py -v
```

Ожидаемо: падение на отсутствии `walk_forward.report`.

- [ ] **Шаг 3: Реализовать минимальные функции данных и leaderboard**

Создать `walk_forward/report.py` с функциями:

- `normalize_summary(summary: pd.DataFrame) -> pd.DataFrame`
- `normalize_trades(trades: pd.DataFrame) -> pd.DataFrame`
- `build_leaderboard(summary: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame`
- `build_ticker_summary(leaderboard: pd.DataFrame) -> pd.DataFrame`

Формулы:

```python
gross_profit = positive_pnl.sum()
gross_loss = abs(negative_pnl.sum())
profit_factor = gross_profit / gross_loss if gross_loss else float("inf")
cum = pnl.cumsum()
max_drawdown = (cum - cum.cummax()).min()
recovery_factor = total_pnl / abs(max_drawdown) if max_drawdown else float("inf")
score = total_pnl + max_drawdown * 0.5
```

- [ ] **Шаг 4: Проверить GREEN**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_report.py -v
```

Ожидаемо: тесты Task 1 проходят.

- [ ] **Шаг 5: Коммит**

```powershell
git add walk_forward\report.py tests\test_walk_forward_report.py
git commit -m "Add walk-forward report metrics"
```

---

### Task 2: Матрицы И Загрузка Файлов

**Файлы:**
- Изменить: `walk_forward/report.py`
- Изменить: `tests/test_walk_forward_report.py`

- [ ] **Шаг 1: Добавить падающие тесты для матриц и missing trades**

Добавить тесты:

```python
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
    pd.DataFrame([{"ticker": "RTS", "model_dir": "model_a", "source_date": "2026-04-01", "pnl": 1}]).to_csv(
        model_dir / "trades.csv",
        index=False,
    )
    missing_summary = pd.DataFrame(
        [{"ticker": "RTS", "model_dir": "missing", "sentiment_model": "missing", "status": "ok"}]
    )

    trades, errors = report.load_all_trades(tmp_path, missing_summary)

    assert len(trades) == 1
    assert errors.iloc[0]["model_dir"] == "missing"
    assert "trades.csv" in errors.iloc[0]["error"]
```

- [ ] **Шаг 2: Запустить и увидеть RED**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_report.py -v
```

- [ ] **Шаг 3: Реализовать `load_all_trades`, `build_monthly_matrix`, `build_daily_matrix`**

Функции читают только `results_dir/<TICKER>/<model>/trades.csv` и возвращают объединённый DataFrame плюс DataFrame ошибок.

- [ ] **Шаг 4: Проверить GREEN**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_report.py -v
```

- [ ] **Шаг 5: Коммит**

```powershell
git add walk_forward\report.py tests\test_walk_forward_report.py
git commit -m "Add walk-forward report matrices"
```

---

### Task 3: Excel Workbook

**Файлы:**
- Изменить: `walk_forward/report.py`
- Изменить: `tests/test_walk_forward_report.py`

- [ ] **Шаг 1: Добавить падающий тест Excel**

```python
from openpyxl import load_workbook


def test_write_excel_report_creates_expected_sheets(tmp_path: Path) -> None:
    output_xlsx = tmp_path / "walk_forward_report.xlsx"
    summary = _sample_summary()
    trades = _sample_trades()
    leaderboard = report.build_leaderboard(summary, trades)
    ticker_summary = report.build_ticker_summary(leaderboard)
    monthly = report.build_monthly_matrix(trades)
    daily = report.build_daily_matrix(trades)

    report.write_excel_report(
        summary=summary,
        trades=trades,
        leaderboard=leaderboard,
        ticker_summary=ticker_summary,
        monthly_matrix=monthly,
        daily_matrix=daily,
        errors=pd.DataFrame(),
        output_xlsx=output_xlsx,
    )

    workbook = load_workbook(output_xlsx, read_only=True)
    assert workbook.sheetnames == [
        "Dashboard",
        "Leaderboard",
        "Ticker_Summary",
        "Monthly_Matrix",
        "Daily_Matrix",
        "RTS",
        "Raw_Summary",
        "Raw_Trades",
        "Errors",
    ]
```

- [ ] **Шаг 2: Запустить и увидеть RED**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_report.py -v
```

- [ ] **Шаг 3: Реализовать Excel writer**

Добавить:

- `build_dashboard(...) -> pd.DataFrame`
- `write_excel_report(...) -> None`
- `_style_workbook(path: Path) -> None`

Минимальное форматирование: фильтры, frozen row, ширины колонок, числовые форматы, цвет положительного/отрицательного P/L.

- [ ] **Шаг 4: Проверить GREEN**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_report.py -v
```

- [ ] **Шаг 5: Коммит**

```powershell
git add walk_forward\report.py tests\test_walk_forward_report.py
git commit -m "Add walk-forward Excel report"
```

---

### Task 4: HTML Dashboard И CLI

**Файлы:**
- Изменить: `walk_forward/report.py`
- Изменить: `walk_forward/README.md`
- Изменить: `tests/test_walk_forward_report.py`

- [ ] **Шаг 1: Добавить падающий тест HTML и full build**

```python
def test_build_report_writes_html_and_excel(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    model_dir = results_dir / "RTS" / "model_a"
    model_dir.mkdir(parents=True)
    summary_csv = results_dir / "summary.csv"
    output_html = results_dir / "walk_forward_report.html"
    output_xlsx = results_dir / "walk_forward_report.xlsx"

    _sample_summary().to_csv(summary_csv, index=False, encoding="utf-8-sig")
    _sample_trades().to_csv(model_dir / "trades.csv", index=False, encoding="utf-8-sig")

    report.build_report(
        summary_csv=summary_csv,
        results_dir=results_dir,
        output_html=output_html,
        output_xlsx=output_xlsx,
    )

    html = output_html.read_text(encoding="utf-8")
    assert "Walk-Forward Dashboard" in html
    assert "Лучшие модели по тикерам" in html
    assert "RTS" in html
    assert output_xlsx.exists()
```

- [ ] **Шаг 2: Запустить и увидеть RED**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_report.py -v
```

- [ ] **Шаг 3: Реализовать HTML и CLI**

Добавить:

- `build_html(...) -> str`
- Plotly-графики equity, drawdown, monthly heatmap, daily bars;
- `build_report(...) -> None`
- Typer `main(...)`

CLI defaults:

```text
summary_csv = walk_forward/results/summary.csv
results_dir = walk_forward/results
output_html = walk_forward/results/walk_forward_report.html
output_xlsx = walk_forward/results/walk_forward_report.xlsx
```

- [ ] **Шаг 4: Обновить README**

Добавить команду:

```powershell
.venv\Scripts\python.exe -m walk_forward.report
```

- [ ] **Шаг 5: Проверить GREEN**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_report.py -v
```

- [ ] **Шаг 6: Коммит**

```powershell
git add walk_forward\report.py walk_forward\README.md tests\test_walk_forward_report.py
git commit -m "Add walk-forward HTML report"
```

---

### Task 5: Финальная Проверка

**Файлы:**
- Без плановых изменений.

- [ ] **Шаг 1: Запустить focused tests**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_walk_forward_report.py tests\test_walk_forward_core.py tests\test_walk_forward_runner.py -v
```

- [ ] **Шаг 2: Запустить smoke report**

```powershell
.venv\Scripts\python.exe -m walk_forward.report
```

Ожидаемо создаются:

```text
walk_forward/results/walk_forward_report.xlsx
walk_forward/results/walk_forward_report.html
```

- [ ] **Шаг 3: Проверить git status**

```powershell
git status --short
```

Ожидаемо: generated files в `walk_forward/results/` игнорируются.

---

## Самопроверка

- Spec покрыт: Excel, HTML, CLI, метрики, матрицы, тикерные листы, missing trades, output только в `walk_forward/results/`.
- Плейсхолдеров нет.
- Имена функций согласованы между тестами и реализацией.
