from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import typer


TICKER_MAP: dict[str, str] = {
    "rts": "RTS",
    "mix": "MIX",
    "ng": "NG",
    "si": "Si",
    "spyf": "SPYF",
}

DEFAULT_WALK_RESULTS_DIR = Path("walk_forward/results")
DEFAULT_OUTPUT_HTML = Path("compare_backtests/results/backtest_vs_walk_forward.html")

app = typer.Typer(help="Собрать HTML-сравнение ordinary backtest и walk-forward.")


@dataclass(frozen=True)
class ComparisonPair:
    ticker_lc: str
    walk_ticker: str
    model_dir: str
    ordinary_path: Path
    walk_path: Path


@dataclass
class PairComparison:
    pair: ComparisonPair
    ordinary: pd.DataFrame
    walk: pd.DataFrame
    metrics: dict[str, Any]
    error: str | None = None


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

    ordinary_overlap = (
        ordinary_norm[ordinary_norm["source_date"].isin(overlap)]
        .sort_values("source_date")
        .reset_index(drop=True)
    )
    walk_overlap = (
        walk_norm[walk_norm["source_date"].isin(overlap)]
        .sort_values("source_date")
        .reset_index(drop=True)
    )
    ordinary_overlap["pnl"] = ordinary_overlap["pnl"].astype(float)
    walk_overlap["pnl"] = walk_overlap["pnl"].astype(float)
    ordinary_overlap["cum_pnl"] = ordinary_overlap["pnl"].cumsum()
    walk_overlap["cum_pnl"] = walk_overlap["pnl"].cumsum()

    ordinary_total_pnl = float(ordinary_overlap["pnl"].sum())
    walk_total_pnl = float(walk_overlap["pnl"].sum())
    metrics = {
        "ticker": pair.walk_ticker,
        "ticker_lc": pair.ticker_lc,
        "model_dir": pair.model_dir,
        "start_date": overlap[0],
        "end_date": overlap[-1],
        "overlap_rows": len(overlap),
        "ordinary_total_pnl": ordinary_total_pnl,
        "walk_total_pnl": walk_total_pnl,
        "delta_pnl": float(walk_total_pnl - ordinary_total_pnl),
        "ordinary_max_drawdown": _max_drawdown(ordinary_overlap["cum_pnl"]),
        "walk_max_drawdown": _max_drawdown(walk_overlap["cum_pnl"]),
        "ordinary_win_rate": _win_rate(ordinary_overlap["pnl"]),
        "walk_win_rate": _win_rate(walk_overlap["pnl"]),
        "signal_match_rate": _signal_match_rate(ordinary_overlap, walk_overlap),
    }
    return PairComparison(pair, ordinary_overlap, walk_overlap, metrics)


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
    fig.add_trace(
        go.Scatter(
            x=[str(item) for item in comparison.ordinary["source_date"]],
            y=ordinary_dd,
            mode="lines",
            name="Обычный backtest",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[str(item) for item in comparison.walk["source_date"]],
            y=walk_dd,
            mode="lines",
            name="Walk-forward",
        )
    )
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
    body = "".join(
        f"<tr><th>{escape(str(name))}</th><td>{escape(_format_number(value))}</td></tr>"
        for name, value in rows
    )
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
            errors.append(
                {
                    "ticker": pair.walk_ticker,
                    "model_dir": pair.model_dir,
                    "error": f"Не найден ordinary backtest: {pair.ordinary_path}",
                }
            )
            continue
        if not pair.walk_path.exists():
            errors.append(
                {
                    "ticker": pair.walk_ticker,
                    "model_dir": pair.model_dir,
                    "error": f"Не найден walk-forward trades: {pair.walk_path}",
                }
            )
            continue
        try:
            comparison = prepare_comparison(
                pair=pair,
                ordinary=_read_xlsx(pair.ordinary_path),
                walk=_read_xlsx(pair.walk_path),
            )
        except Exception as exc:
            errors.append({"ticker": pair.walk_ticker, "model_dir": pair.model_dir, "error": str(exc)})
            continue
        if comparison.error is not None:
            errors.append({"ticker": pair.walk_ticker, "model_dir": pair.model_dir, "error": comparison.error})
            continue
        comparisons.append(comparison)

    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(build_html(comparisons=comparisons, errors=errors), encoding="utf-8")


def parse_csv(value: Optional[str]) -> list[str] | None:
    if value is None or value.strip() == "":
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


@app.command()
def main(
    walk_results_dir: Path = typer.Option(
        DEFAULT_WALK_RESULTS_DIR,
        "--walk-results-dir",
        help="Папка walk-forward результатов.",
    ),
    output_html: Path = typer.Option(
        DEFAULT_OUTPUT_HTML,
        "--output-html",
        help="Итоговый HTML-отчет.",
    ),
    tickers: Optional[str] = typer.Option(
        None,
        "--tickers",
        help="Фильтр папок тикеров через запятую.",
    ),
    models: Optional[str] = typer.Option(
        None,
        "--models",
        help="Фильтр моделей через запятую.",
    ),
) -> None:
    root = Path.cwd()
    resolved_walk_results_dir = (
        (root / walk_results_dir).resolve()
        if not walk_results_dir.is_absolute()
        else walk_results_dir
    )
    resolved_output_html = (
        (root / output_html).resolve()
        if not output_html.is_absolute()
        else output_html
    )
    build_report(
        root=root,
        walk_results_dir=resolved_walk_results_dir,
        output_html=resolved_output_html,
        tickers=parse_csv(tickers),
        models=parse_csv(models),
    )
    typer.echo(f"HTML-отчет: {resolved_output_html}")


if __name__ == "__main__":
    app()
