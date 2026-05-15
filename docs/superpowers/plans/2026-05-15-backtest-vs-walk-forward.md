# План реализации сравнения Backtest и Walk-Forward

> **Для агентных исполнителей:** ОБЯЗАТЕЛЬНЫЙ ПОДНАВЫК: использовать `superpowers:subagent-driven-development` (рекомендуется) или `superpowers:executing-plans`, выполнять план по задачам. Шаги используют чекбоксы `- [ ]` для отслеживания.

**Цель:** создать отдельный HTML-отчет, который сравнивает обычные модельные backtest-графики с walk-forward-графиками на общих датах для каждой пары тикер/модель.

**Архитектура:** новый пакет `compare_backtests` будет читать XLSX-артефакты из двух существующих источников, нормализовать данные, пересчитывать `cum_pnl` на пересечении дат и строить автономный HTML-отчет через Plotly. Логика чтения, сравнения, метрик и HTML останется в одном небольшом модуле, потому что первая версия отчета узкая и не требует отдельного слоя конфигурации.

**Технологии:** Python, pandas, plotly, typer, pathlib, стандартный `unittest`; запуск через `.venv\Scripts\python.exe`.

---

## Структура файлов

- Создать `compare_backtests/__init__.py`.
  Отвечает только за объявление пакета.
- Создать `compare_backtests/build_report.py`.
  Отвечает за обнаружение пар, чтение XLSX, нормализацию, пересечение дат, расчет метрик, построение Plotly HTML и CLI.
- Создать `tests/test_compare_backtests_report.py`.
  Проверяет чистые helper-функции и сборку HTML на временных XLSX-файлах.
- Использовать существующую спеку `docs/superpowers/specs/2026-05-15-backtest-vs-walk-forward-design.md` как источник требований.

## Задача 1: Тесты обнаружения пар и нормализации

**Файлы:**
- Создать: `tests/test_compare_backtests_report.py`
- Создать в шаге 3: `compare_backtests/__init__.py`
- Создать в шаге 3: `compare_backtests/build_report.py`

- [ ] **Шаг 1: написать падающие тесты для тикер-маппинга и обнаружения пар**

Добавить в `tests/test_compare_backtests_report.py`:

```python
from pathlib import Path

import pandas as pd

from compare_backtests import build_report


def test_ticker_folder_mapping_uses_walk_forward_names() -> None:
    assert build_report.walk_ticker_for("rts") == "RTS"
    assert build_report.walk_ticker_for("mix") == "MIX"
    assert build_report.walk_ticker_for("ng") == "NG"
    assert build_report.walk_ticker_for("si") == "Si"
    assert build_report.walk_ticker_for("spyf") == "SPYF"


def test_discover_pairs_reads_walk_forward_model_folders(tmp_path: Path) -> None:
    walk_results = tmp_path / "walk_forward" / "results"
    (walk_results / "RTS" / "gemma3_12b").mkdir(parents=True)
    (walk_results / "RTS" / "qwen2.5_7b").mkdir(parents=True)
    (walk_results / "MIX" / "gemma3_12b").mkdir(parents=True)
    (walk_results / "RTS" / "gemma3_12b" / "trades.xlsx").write_bytes(b"placeholder")
    (walk_results / "RTS" / "qwen2.5_7b" / "trades.xlsx").write_bytes(b"placeholder")
    (walk_results / "MIX" / "gemma3_12b" / "trades.xlsx").write_bytes(b"placeholder")

    pairs = build_report.discover_pairs(root=tmp_path, walk_results_dir=walk_results)

    assert [(item.ticker_lc, item.walk_ticker, item.model_dir) for item in pairs] == [
        ("mix", "MIX", "gemma3_12b"),
        ("rts", "RTS", "gemma3_12b"),
        ("rts", "RTS", "qwen2.5_7b"),
    ]
    assert pairs[0].ordinary_path == tmp_path / "mix" / "gemma3_12b" / "backtest" / "sentiment_backtest_results.xlsx"
    assert pairs[0].walk_path == walk_results / "MIX" / "gemma3_12b" / "trades.xlsx"
```

- [ ] **Шаг 2: запустить тесты и увидеть ожидаемое падение**

Команда:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_compare_backtests_report -v
```

Ожидание: падение с `ModuleNotFoundError: No module named 'compare_backtests'`.

- [ ] **Шаг 3: создать минимальный пакет и helper обнаружения пар**

Создать `compare_backtests/__init__.py`:

```python
"""Сравнение обычного backtest и walk-forward отчетов."""
```

Создать `compare_backtests/build_report.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


TICKER_MAP: dict[str, str] = {
    "rts": "RTS",
    "mix": "MIX",
    "ng": "NG",
    "si": "Si",
    "spyf": "SPYF",
}

DEFAULT_WALK_RESULTS_DIR = Path("walk_forward/results")
DEFAULT_OUTPUT_HTML = Path("compare_backtests/results/backtest_vs_walk_forward.html")


@dataclass(frozen=True)
class ComparisonPair:
    ticker_lc: str
    walk_ticker: str
    model_dir: str
    ordinary_path: Path
    walk_path: Path


def walk_ticker_for(ticker_lc: str) -> str:
    key = ticker_lc.lower()
    if key not in TICKER_MAP:
        raise KeyError(f"Неизвестный тикер: {ticker_lc}")
    return TICKER_MAP[key]


def discover_pairs(
    *,
    root: Path,
    walk_results_dir: Path,
    tickers: list[str] | None = None,
    models: list[str] | None = None,
) -> list[ComparisonPair]:
    selected_tickers = [item.lower() for item in tickers] if tickers else sorted(TICKER_MAP)
    selected_models = set(models or [])
    pairs: list[ComparisonPair] = []

    for ticker_lc in selected_tickers:
        walk_ticker = walk_ticker_for(ticker_lc)
        ticker_dir = walk_results_dir / walk_ticker
        if not ticker_dir.exists():
            continue
        for model_path in sorted(item for item in ticker_dir.iterdir() if item.is_dir()):
            if selected_models and model_path.name not in selected_models:
                continue
            walk_path = model_path / "trades.xlsx"
            ordinary_path = root / ticker_lc / model_path.name / "backtest" / "sentiment_backtest_results.xlsx"
            pairs.append(
                ComparisonPair(
                    ticker_lc=ticker_lc,
                    walk_ticker=walk_ticker,
                    model_dir=model_path.name,
                    ordinary_path=ordinary_path,
                    walk_path=walk_path,
                )
            )

    return sorted(pairs, key=lambda item: (item.ticker_lc, item.model_dir))
```

- [ ] **Шаг 4: запустить тесты и убедиться, что задача 1 зеленая**

Команда:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_compare_backtests_report -v
```

Ожидание: 2 теста проходят.

- [ ] **Шаг 5: коммит задачи 1**

```powershell
git add compare_backtests tests/test_compare_backtests_report.py
git commit -m "Add comparison pair discovery"
```

## Задача 2: Нормализация, пересечение дат и метрики

**Файлы:**
- Изменить: `compare_backtests/build_report.py`
- Изменить: `tests/test_compare_backtests_report.py`

- [ ] **Шаг 1: написать падающие тесты для пересечения дат и метрик**

Добавить в `tests/test_compare_backtests_report.py`:

```python
def _ordinary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"source_date": "2026-01-01", "sentiment": 1, "action": "follow", "direction": "LONG", "next_body": 10, "quantity": 1, "pnl": 10, "cum_pnl": 10},
            {"source_date": "2026-01-02", "sentiment": -1, "action": "invert", "direction": "LONG", "next_body": -3, "quantity": 1, "pnl": -3, "cum_pnl": 7},
            {"source_date": "2026-01-03", "sentiment": 2, "action": "follow", "direction": "LONG", "next_body": 5, "quantity": 1, "pnl": 5, "cum_pnl": 12},
        ]
    )


def _walk_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"source_date": "2026-01-02", "sentiment": -1, "action": "invert", "direction": "LONG", "next_body": -3, "quantity": 1, "pnl": -3, "cum_pnl": -3, "ticker": "RTS", "model_dir": "model_a"},
            {"source_date": "2026-01-03", "sentiment": 2, "action": "invert", "direction": "SHORT", "next_body": 5, "quantity": 1, "pnl": -5, "cum_pnl": -8, "ticker": "RTS", "model_dir": "model_a"},
            {"source_date": "2026-01-04", "sentiment": 3, "action": "follow", "direction": "LONG", "next_body": 7, "quantity": 1, "pnl": 7, "cum_pnl": -1, "ticker": "RTS", "model_dir": "model_a"},
        ]
    )


def test_prepare_comparison_uses_only_overlap_and_recalculates_cum_pnl() -> None:
    comparison = build_report.prepare_comparison(
        pair=build_report.ComparisonPair(
            ticker_lc="rts",
            walk_ticker="RTS",
            model_dir="model_a",
            ordinary_path=Path("ordinary.xlsx"),
            walk_path=Path("walk.xlsx"),
        ),
        ordinary=_ordinary_frame(),
        walk=_walk_frame(),
    )

    assert comparison.error is None
    assert comparison.ordinary["source_date"].astype(str).tolist() == ["2026-01-02", "2026-01-03"]
    assert comparison.walk["source_date"].astype(str).tolist() == ["2026-01-02", "2026-01-03"]
    assert comparison.ordinary["cum_pnl"].tolist() == [-3.0, 2.0]
    assert comparison.walk["cum_pnl"].tolist() == [-3.0, -8.0]
    assert comparison.metrics["ordinary_total_pnl"] == 2.0
    assert comparison.metrics["walk_total_pnl"] == -8.0
    assert comparison.metrics["delta_pnl"] == -10.0
    assert comparison.metrics["signal_match_rate"] == 50.0
```

- [ ] **Шаг 2: запустить тест и увидеть ожидаемое падение**

Команда:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_compare_backtests_report -v
```

Ожидание: падение с `AttributeError: module 'compare_backtests.build_report' has no attribute 'prepare_comparison'`.

- [ ] **Шаг 3: реализовать нормализацию и расчет метрик**

Добавить в `compare_backtests/build_report.py`:

```python
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = {
    "source_date",
    "sentiment",
    "action",
    "direction",
    "next_body",
    "quantity",
    "pnl",
    "cum_pnl",
}


@dataclass
class PairComparison:
    pair: ComparisonPair
    ordinary: pd.DataFrame
    walk: pd.DataFrame
    metrics: dict[str, Any]
    error: str | None = None


def normalize_trades(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    missing = REQUIRED_COLUMNS - set(result.columns)
    if missing:
        raise ValueError(f"Нет обязательных колонок: {sorted(missing)}")

    result["source_date"] = pd.to_datetime(result["source_date"], errors="coerce").dt.date
    for column in ("sentiment", "next_body", "quantity", "pnl"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["action"] = result["action"].fillna("").astype(str)
    result["direction"] = result["direction"].fillna("").astype(str)
    result = result.dropna(subset=["source_date", "pnl"]).sort_values("source_date").reset_index(drop=True)
    return result


def _max_drawdown(cum_pnl: pd.Series) -> float:
    if cum_pnl.empty:
        return 0.0
    drawdown = cum_pnl - cum_pnl.cummax()
    return float(drawdown.min())


def _win_rate(pnl: pd.Series) -> float:
    if pnl.empty:
        return 0.0
    return float((pnl > 0).mean() * 100)


def _signal_match_rate(ordinary: pd.DataFrame, walk: pd.DataFrame) -> float:
    if ordinary.empty:
        return 0.0
    matches = (
        (ordinary["action"].reset_index(drop=True) == walk["action"].reset_index(drop=True))
        & (ordinary["direction"].reset_index(drop=True) == walk["direction"].reset_index(drop=True))
    )
    return float(matches.mean() * 100)


def prepare_comparison(
    *,
    pair: ComparisonPair,
    ordinary: pd.DataFrame,
    walk: pd.DataFrame,
) -> PairComparison:
    ordinary_norm = normalize_trades(ordinary)
    walk_norm = normalize_trades(walk)
    overlap = sorted(set(ordinary_norm["source_date"]) & set(walk_norm["source_date"]))
    if not overlap:
        return PairComparison(pair, pd.DataFrame(), pd.DataFrame(), {}, "Нет пересекающихся дат")

    ordinary_overlap = ordinary_norm[ordinary_norm["source_date"].isin(overlap)].sort_values("source_date").reset_index(drop=True)
    walk_overlap = walk_norm[walk_norm["source_date"].isin(overlap)].sort_values("source_date").reset_index(drop=True)
    ordinary_overlap["pnl"] = ordinary_overlap["pnl"].astype(float)
    walk_overlap["pnl"] = walk_overlap["pnl"].astype(float)
    ordinary_overlap["cum_pnl"] = ordinary_overlap["pnl"].cumsum()
    walk_overlap["cum_pnl"] = walk_overlap["pnl"].cumsum()

    metrics = {
        "ticker": pair.walk_ticker,
        "ticker_lc": pair.ticker_lc,
        "model_dir": pair.model_dir,
        "start_date": overlap[0],
        "end_date": overlap[-1],
        "overlap_rows": len(overlap),
        "ordinary_total_pnl": float(ordinary_overlap["pnl"].sum()),
        "walk_total_pnl": float(walk_overlap["pnl"].sum()),
        "delta_pnl": float(walk_overlap["pnl"].sum() - ordinary_overlap["pnl"].sum()),
        "ordinary_max_drawdown": _max_drawdown(ordinary_overlap["cum_pnl"]),
        "walk_max_drawdown": _max_drawdown(walk_overlap["cum_pnl"]),
        "ordinary_win_rate": _win_rate(ordinary_overlap["pnl"]),
        "walk_win_rate": _win_rate(walk_overlap["pnl"]),
        "signal_match_rate": _signal_match_rate(ordinary_overlap, walk_overlap),
    }
    return PairComparison(pair, ordinary_overlap, walk_overlap, metrics)
```

- [ ] **Шаг 4: запустить тесты и убедиться, что задача 2 зеленая**

Команда:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_compare_backtests_report -v
```

Ожидание: тесты проходят.

- [ ] **Шаг 5: коммит задачи 2**

```powershell
git add compare_backtests/build_report.py tests/test_compare_backtests_report.py
git commit -m "Add comparison metrics"
```

## Задача 3: HTML-отчет и обработка ошибок

**Файлы:**
- Изменить: `compare_backtests/build_report.py`
- Изменить: `tests/test_compare_backtests_report.py`

- [ ] **Шаг 1: написать падающий тест сборки HTML на временных XLSX**

Добавить в `tests/test_compare_backtests_report.py`:

```python
def test_build_report_writes_html_with_metrics_and_errors(tmp_path: Path) -> None:
    walk_results = tmp_path / "walk_forward" / "results"
    walk_model = walk_results / "RTS" / "model_a"
    walk_model.mkdir(parents=True)
    ordinary_model = tmp_path / "rts" / "model_a" / "backtest"
    ordinary_model.mkdir(parents=True)

    _ordinary_frame().to_excel(ordinary_model / "sentiment_backtest_results.xlsx", index=False)
    _walk_frame().to_excel(walk_model / "trades.xlsx", index=False)

    missing_model = walk_results / "RTS" / "missing_model"
    missing_model.mkdir(parents=True)
    _walk_frame().to_excel(missing_model / "trades.xlsx", index=False)

    missing_walk_model = walk_results / "RTS" / "missing_walk"
    missing_walk_model.mkdir(parents=True)
    missing_walk_backtest = tmp_path / "rts" / "missing_walk" / "backtest"
    missing_walk_backtest.mkdir(parents=True)
    _ordinary_frame().to_excel(missing_walk_backtest / "sentiment_backtest_results.xlsx", index=False)

    output_html = tmp_path / "compare.html"

    build_report.build_report(
        root=tmp_path,
        walk_results_dir=walk_results,
        output_html=output_html,
        tickers=["rts"],
        models=None,
    )

    html = output_html.read_text(encoding="utf-8")
    assert "Сравнение Backtest и Walk-Forward" in html
    assert "RTS / model_a" in html
    assert "Delta P/L" in html
    assert "missing_model" in html
    assert "Не найден ordinary backtest" in html
    assert "missing_walk" in html
    assert "Не найден walk-forward trades" in html
```

- [ ] **Шаг 2: запустить тест и увидеть ожидаемое падение**

Команда:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_compare_backtests_report -v
```

Ожидание: падение с `AttributeError: module 'compare_backtests.build_report' has no attribute 'build_report'`.

- [ ] **Шаг 3: реализовать чтение файлов, HTML и таблицу ошибок**

Добавить в `compare_backtests/build_report.py`:

```python
from html import escape

import plotly.graph_objects as go
import plotly.io as pio


def _format_number(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.2f}".replace(",", " ")
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")
    return str(value)


def _plot_div(fig: go.Figure, *, include_plotlyjs: bool) -> str:
    return pio.to_html(
        fig,
        include_plotlyjs=include_plotlyjs,
        full_html=False,
        config={"displayModeBar": False, "responsive": True},
    )


def _equity_figure(comparison: PairComparison) -> go.Figure:
    fig = go.Figure()
    ordinary = comparison.ordinary
    walk = comparison.walk
    label = f"{comparison.pair.walk_ticker} / {comparison.pair.model_dir}"
    fig.add_trace(
        go.Scatter(
            x=[str(item) for item in ordinary["source_date"]],
            y=ordinary["cum_pnl"],
            mode="lines",
            name="Обычный backtest",
            line={"color": "#2563eb", "width": 2},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[str(item) for item in walk["source_date"]],
            y=walk["cum_pnl"],
            mode="lines",
            name="Walk-forward",
            line={"color": "#dc2626", "width": 2},
        )
    )
    fig.update_layout(
        title=f"{label}: equity на общих датах",
        template="plotly_white",
        height=360,
        margin={"l": 45, "r": 20, "t": 55, "b": 40},
        hovermode="x unified",
    )
    return fig


def _drawdown_figure(comparison: PairComparison) -> go.Figure:
    fig = go.Figure()
    ordinary_cum = comparison.ordinary["cum_pnl"]
    walk_cum = comparison.walk["cum_pnl"]
    ordinary_dd = ordinary_cum - ordinary_cum.cummax()
    walk_dd = walk_cum - walk_cum.cummax()
    fig.add_trace(go.Scatter(x=[str(item) for item in comparison.ordinary["source_date"]], y=ordinary_dd, mode="lines", name="Обычный backtest"))
    fig.add_trace(go.Scatter(x=[str(item) for item in comparison.walk["source_date"]], y=walk_dd, mode="lines", name="Walk-forward"))
    fig.update_layout(
        title="Drawdown на общих датах",
        template="plotly_white",
        height=280,
        margin={"l": 45, "r": 20, "t": 55, "b": 40},
        hovermode="x unified",
    )
    return fig


def _metrics_table(metrics: dict[str, Any]) -> str:
    rows = [
        ("Период", f"{metrics['start_date']} .. {metrics['end_date']}"),
        ("Общих строк", metrics["overlap_rows"]),
        ("Backtest P/L", metrics["ordinary_total_pnl"]),
        ("Walk-forward P/L", metrics["walk_total_pnl"]),
        ("Delta P/L", metrics["delta_pnl"]),
        ("Backtest MaxDD", metrics["ordinary_max_drawdown"]),
        ("Walk-forward MaxDD", metrics["walk_max_drawdown"]),
        ("Backtest win rate", f"{metrics['ordinary_win_rate']:.1f}%"),
        ("Walk-forward win rate", f"{metrics['walk_win_rate']:.1f}%"),
        ("Совпадение сигналов", f"{metrics['signal_match_rate']:.1f}%"),
    ]
    body = "".join(f"<tr><th>{escape(str(name))}</th><td>{escape(_format_number(value))}</td></tr>" for name, value in rows)
    return f"<table class='metrics'><tbody>{body}</tbody></table>"


def _summary_table(metrics_rows: list[dict[str, Any]]) -> str:
    if not metrics_rows:
        return "<p class='muted'>Нет сопоставимых пар.</p>"
    columns = [
        ("ticker", "Тикер"),
        ("model_dir", "Модель"),
        ("overlap_rows", "Строк"),
        ("ordinary_total_pnl", "Backtest P/L"),
        ("walk_total_pnl", "WF P/L"),
        ("delta_pnl", "Delta P/L"),
        ("signal_match_rate", "Сигналы %"),
    ]
    header = "".join(f"<th>{escape(title)}</th>" for _, title in columns)
    rows = []
    for row in sorted(metrics_rows, key=lambda item: (item["ticker"], -item["delta_pnl"])):
        cells = "".join(f"<td>{escape(_format_number(row[key]))}</td>" for key, _ in columns)
        rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _errors_table(errors: list[dict[str, str]]) -> str:
    if not errors:
        return "<p class='muted'>Ошибок и пропусков нет.</p>"
    header = "<th>Тикер</th><th>Модель</th><th>Ошибка</th>"
    rows = "".join(
        f"<tr><td>{escape(row['ticker'])}</td><td>{escape(row['model_dir'])}</td><td>{escape(row['error'])}</td></tr>"
        for row in errors
    )
    return f"<table><thead><tr>{header}</tr></thead><tbody>{rows}</tbody></table>"


def build_html(*, comparisons: list[PairComparison], errors: list[dict[str, str]]) -> str:
    metrics_rows = [item.metrics for item in comparisons if item.error is None]
    sections: list[str] = []
    include_plotlyjs = True
    tickers = sorted({item.pair.walk_ticker for item in comparisons if item.error is None})
    for ticker in tickers:
        pair_blocks: list[str] = []
        ticker_comparisons = [
            item
            for item in comparisons
            if item.error is None and item.pair.walk_ticker == ticker
        ]
        for comparison in sorted(ticker_comparisons, key=lambda item: item.pair.model_dir):
            label = f"{comparison.pair.walk_ticker} / {comparison.pair.model_dir}"
            pair_blocks.append(
                f"""
                <div class="pair">
                  <h3>{escape(label)}</h3>
                  <div class="grid">
                    <div>{_plot_div(_equity_figure(comparison), include_plotlyjs=include_plotlyjs)}</div>
                    <div>{_plot_div(_drawdown_figure(comparison), include_plotlyjs=False)}</div>
                  </div>
                  {_metrics_table(comparison.metrics)}
                </div>
                """
            )
            include_plotlyjs = False
        sections.append(
            f"""
            <section>
              <h2>{escape(ticker)}</h2>
              {"".join(pair_blocks)}
            </section>
            """
        )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Сравнение Backtest и Walk-Forward</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; background: #f8fafc; }}
    h1, h2, h3 {{ color: #111827; }}
    section {{ margin: 28px 0; padding: 20px; background: #ffffff; border: 1px solid #e5e7eb; border-radius: 6px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 14px; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 7px 9px; text-align: right; }}
    th:first-child, td:first-child, td:nth-child(2) {{ text-align: left; }}
    thead th {{ background: #1f4e78; color: #ffffff; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; }}
    .metrics th {{ width: 260px; background: #f3f4f6; color: #111827; }}
    .muted {{ color: #6b7280; }}
  </style>
</head>
<body>
  <h1>Сравнение Backtest и Walk-Forward</h1>
  <p class="muted">Сравнение строится только на датах, которые есть в обоих источниках для каждой пары тикер/модель.</p>
  <section>
    <h2>Сводка</h2>
    {_summary_table(metrics_rows)}
  </section>
  {"".join(sections)}
  <section>
    <h2>Ошибки и пропуски</h2>
    {_errors_table(errors)}
  </section>
</body>
</html>"""


def _read_xlsx(path: Path) -> pd.DataFrame:
    return pd.read_excel(path)


def build_report(
    *,
    root: Path,
    walk_results_dir: Path,
    output_html: Path,
    tickers: list[str] | None = None,
    models: list[str] | None = None,
) -> None:
    comparisons: list[PairComparison] = []
    errors: list[dict[str, str]] = []
    for pair in discover_pairs(root=root, walk_results_dir=walk_results_dir, tickers=tickers, models=models):
        if not pair.ordinary_path.exists():
            errors.append({"ticker": pair.walk_ticker, "model_dir": pair.model_dir, "error": f"Не найден ordinary backtest: {pair.ordinary_path}"})
            continue
        if not pair.walk_path.exists():
            errors.append({"ticker": pair.walk_ticker, "model_dir": pair.model_dir, "error": f"Не найден walk-forward trades: {pair.walk_path}"})
            continue
        try:
            comparison = prepare_comparison(pair=pair, ordinary=_read_xlsx(pair.ordinary_path), walk=_read_xlsx(pair.walk_path))
        except Exception as exc:
            errors.append({"ticker": pair.walk_ticker, "model_dir": pair.model_dir, "error": str(exc)})
            continue
        if comparison.error is not None:
            errors.append({"ticker": pair.walk_ticker, "model_dir": pair.model_dir, "error": comparison.error})
            continue
        comparisons.append(comparison)

    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(build_html(comparisons=comparisons, errors=errors), encoding="utf-8")
```

- [ ] **Шаг 4: запустить тесты и убедиться, что задача 3 зеленая**

Команда:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_compare_backtests_report -v
```

Ожидание: тесты проходят, HTML создается во временной папке.

- [ ] **Шаг 5: коммит задачи 3**

```powershell
git add compare_backtests/build_report.py tests/test_compare_backtests_report.py
git commit -m "Build backtest comparison HTML"
```

## Задача 4: CLI и реальный smoke test

**Файлы:**
- Изменить: `compare_backtests/build_report.py`
- Изменить: `tests/test_compare_backtests_report.py`

- [ ] **Шаг 1: написать падающий тест parse_csv для CLI-фильтров**

Добавить в `tests/test_compare_backtests_report.py`:

```python
def test_parse_csv_returns_none_for_empty_and_values_for_list() -> None:
    assert build_report.parse_csv(None) is None
    assert build_report.parse_csv("") is None
    assert build_report.parse_csv("rts, mix") == ["rts", "mix"]
```

- [ ] **Шаг 2: запустить тест и увидеть ожидаемое падение**

Команда:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_compare_backtests_report -v
```

Ожидание: падение с `AttributeError: module 'compare_backtests.build_report' has no attribute 'parse_csv'`.

- [ ] **Шаг 3: добавить typer CLI**

Добавить в `compare_backtests/build_report.py`:

```python
from typing import Optional

import typer


app = typer.Typer(help="Собрать HTML-сравнение ordinary backtest и walk-forward.")


def parse_csv(value: Optional[str]) -> list[str] | None:
    if value is None or value.strip() == "":
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


@app.command()
def main(
    walk_results_dir: Path = typer.Option(DEFAULT_WALK_RESULTS_DIR, "--walk-results-dir", help="Папка walk-forward результатов."),
    output_html: Path = typer.Option(DEFAULT_OUTPUT_HTML, "--output-html", help="Итоговый HTML-отчет."),
    tickers: Optional[str] = typer.Option(None, "--tickers", help="Фильтр папок тикеров через запятую."),
    models: Optional[str] = typer.Option(None, "--models", help="Фильтр моделей через запятую."),
) -> None:
    root = Path.cwd()
    build_report(
        root=root,
        walk_results_dir=(root / walk_results_dir).resolve() if not walk_results_dir.is_absolute() else walk_results_dir,
        output_html=(root / output_html).resolve() if not output_html.is_absolute() else output_html,
        tickers=parse_csv(tickers),
        models=parse_csv(models),
    )
    typer.echo(f"HTML-отчет: {output_html}")


if __name__ == "__main__":
    app()
```

- [ ] **Шаг 4: запустить unit-тесты**

Команда:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_compare_backtests_report -v
```

Ожидание: все тесты нового файла проходят.

- [ ] **Шаг 5: запустить реальный smoke test на локальных артефактах**

Команда:

```powershell
.venv\Scripts\python.exe -m compare_backtests.build_report
```

Ожидание:

- команда завершается с exit code 0;
- создан файл `compare_backtests/results/backtest_vs_walk_forward.html`;
- в выводе есть путь к HTML-отчету;
- модельные папки `<ticker>/<model>/` не изменяются.

- [ ] **Шаг 6: проверить HTML-файл текстово**

Команда:

```powershell
Select-String -Path compare_backtests\results\backtest_vs_walk_forward.html -Pattern "Сравнение Backtest и Walk-Forward","RTS","MIX","Delta P/L"
```

Ожидание: находятся заголовок отчета, тикеры и колонка `Delta P/L`.

- [ ] **Шаг 7: запустить релевантные существующие тесты**

Команда:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_compare_backtests_report tests.test_walk_forward_report tests.test_walk_forward_core -v
```

Ожидание: все перечисленные тесты проходят.

- [ ] **Шаг 8: коммит задачи 4**

```powershell
git add compare_backtests tests/test_compare_backtests_report.py
git commit -m "Add backtest comparison CLI"
```

## Финальная проверка

- [ ] **Шаг 1: проверить git status**

```powershell
git status --short
```

Ожидание: в рабочем дереве нет неожиданных изменений. Допустим ожидаемый новый артефакт `compare_backtests/results/backtest_vs_walk_forward.html`, если он не игнорируется.

- [ ] **Шаг 2: если HTML-артефакт не должен попасть в git, проверить `.gitignore`**

```powershell
git check-ignore -v compare_backtests\results\backtest_vs_walk_forward.html
```

Ожидание: файл игнорируется общим правилом для `*.html` или добавляется новое узкое правило для `compare_backtests/results/`.

- [ ] **Шаг 3: итоговый запуск smoke test**

```powershell
.venv\Scripts\python.exe -m compare_backtests.build_report
```

Ожидание: HTML-отчет пересобран без ошибок.

- [ ] **Шаг 4: итоговый запуск тестов**

```powershell
.venv\Scripts\python.exe -m unittest tests.test_compare_backtests_report tests.test_walk_forward_report tests.test_walk_forward_core -v
```

Ожидание: все тесты проходят.
