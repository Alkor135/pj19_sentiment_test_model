from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
from typing import Any, Optional

import pandas as pd
import typer
import yaml

ROOT = Path(__file__).resolve().parent.parent
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from oos.core import load_sentiment_pkl, run_oos_month


DEFAULT_TICKERS = ("rts", "mix", "ng", "si", "spyf")
app = typer.Typer(help="Leave-one-month-out OOS backtest без записи в рабочие модельные папки.")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _apply_placeholders(settings: dict[str, Any], model_dir: str) -> dict[str, Any]:
    ticker = str(settings.get("ticker", ""))
    ticker_lc = str(settings.get("ticker_lc", ticker.lower()))
    out = deepcopy(settings)
    placeholders = {
        "{ticker}": ticker,
        "{ticker_lc}": ticker_lc,
        "{model_dir}": model_dir,
    }
    for key, value in list(out.items()):
        if isinstance(value, str):
            for old, new in placeholders.items():
                value = value.replace(old, new)
            out[key] = value
    return out


def _parse_csv(value: Optional[str], default: tuple[str, ...] = ()) -> list[str]:
    if value is None or value.strip() == "":
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def load_ticker_settings(ticker_lc: str) -> dict[str, Any]:
    settings_path = ROOT / ticker_lc / "settings.yaml"
    if not settings_path.exists():
        raise FileNotFoundError(f"settings.yaml не найден: {settings_path}")
    return yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}


def load_model_settings(ticker_lc: str, model_dir: str) -> dict[str, Any]:
    raw = load_ticker_settings(ticker_lc)
    common = raw.get("common") or {}
    settings = _deep_merge(common, raw.get("model_defaults") or {})
    settings = _deep_merge(settings, (raw.get("models") or {}).get(model_dir) or {})
    settings["model_dir"] = model_dir
    return _apply_placeholders(settings, model_dir)


def discover_models(ticker_lc: str) -> list[str]:
    raw = load_ticker_settings(ticker_lc)
    return sorted((raw.get("models") or {}).keys())


def iter_months(index: pd.Index, start_month: str, end_month: Optional[str]) -> list[str]:
    if index.empty:
        return []
    start = pd.Period(start_month, freq="M")
    end = pd.Period(end_month, freq="M") if end_month else pd.Period(max(index), freq="M")
    if end < start:
        raise ValueError(f"end-month {end} раньше start-month {start}")
    return [str(period) for period in pd.period_range(start=start, end=end, freq="M")]


def error_summary(ticker: str, model_dir: str, sentiment_model: str, month: str, error: Exception) -> dict[str, Any]:
    return {
        "status": "error",
        "ticker": ticker,
        "model_dir": model_dir,
        "sentiment_model": sentiment_model,
        "month": month,
        "error": str(error),
    }


@app.command()
def main(
    tickers: Optional[str] = typer.Option(
        None,
        "--tickers",
        help="Тикеры через запятую. По умолчанию: rts,mix,ng,si,spyf.",
    ),
    models: Optional[str] = typer.Option(
        None,
        "--models",
        help="Модели через запятую. По умолчанию берутся все модели из settings.yaml каждого тикера.",
    ),
    start_month: str = typer.Option(
        "2025-10",
        "--start-month",
        help="Первый OOS-месяц в формате YYYY-MM.",
    ),
    end_month: Optional[str] = typer.Option(
        None,
        "--end-month",
        help="Последний OOS-месяц в формате YYYY-MM. По умолчанию последний месяц в sentiment PKL.",
    ),
    output_dir: Path = typer.Option(
        ROOT / "oos" / "results",
        "--output-dir",
        help="Папка для OOS-артефактов.",
    ),
    keep_going: bool = typer.Option(
        True,
        "--keep-going/--stop-on-error",
        help="Продолжать прогон при ошибке отдельного месяца/модели.",
    ),
) -> None:
    wanted_tickers = _parse_csv(tickers, DEFAULT_TICKERS)
    explicit_models = _parse_csv(models) if models else None
    summaries: list[dict[str, Any]] = []

    output_dir = output_dir.resolve()
    typer.echo(f"OOS output: {output_dir}")

    for ticker_lc in wanted_tickers:
        model_dirs = explicit_models or discover_models(ticker_lc)
        for model_dir in model_dirs:
            settings = load_model_settings(ticker_lc, model_dir)
            ticker = str(settings.get("ticker", ticker_lc.upper()))
            sentiment_model = str(settings.get("sentiment_model", model_dir))
            sentiment_pkl = Path(str(settings.get("sentiment_output_pkl", "")))

            try:
                indexed = load_sentiment_pkl(sentiment_pkl)
                months = iter_months(indexed.index, start_month, end_month)
            except Exception as exc:
                summaries.append(error_summary(ticker, model_dir, sentiment_model, start_month, exc))
                typer.echo(f"[ERROR] {ticker}/{model_dir}: {exc}")
                if not keep_going:
                    raise typer.Exit(code=1) from exc
                continue

            for month in months:
                try:
                    summary = run_oos_month(
                        indexed=indexed,
                        quantity=int(settings.get("quantity_test", 1)),
                        ticker=ticker,
                        model_dir=model_dir,
                        sentiment_model=sentiment_model,
                        month=month,
                        output_dir=output_dir,
                    )
                    summaries.append(summary)
                    typer.echo(
                        f"[OK] {ticker}/{model_dir}/{month}: "
                        f"trades={summary['trades']} pnl={summary['total_pnl']:.2f}"
                    )
                except Exception as exc:
                    summaries.append(error_summary(ticker, model_dir, sentiment_model, month, exc))
                    typer.echo(f"[ERROR] {ticker}/{model_dir}/{month}: {exc}")
                    if not keep_going:
                        raise typer.Exit(code=1) from exc

    if not summaries:
        typer.echo("Нет результатов OOS.")
        raise typer.Exit(code=1)

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_df = pd.DataFrame(summaries)
    summary_csv = output_dir / "summary.csv"
    summary_xlsx = output_dir / "summary.xlsx"
    summary_df.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    summary_df.to_excel(summary_xlsx, index=False)

    ok_count = int((summary_df["status"] == "ok").sum())
    error_count = int((summary_df["status"] == "error").sum())
    typer.echo("\n========== OOS ИТОГ ==========")
    typer.echo(f"OK: {ok_count}")
    typer.echo(f"ERROR: {error_count}")
    typer.echo(f"CSV: {summary_csv}")
    typer.echo(f"XLSX: {summary_xlsx}")

    if error_count:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
