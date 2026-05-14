from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import pickle
from typing import Any, Optional

import pandas as pd
import typer
import yaml

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
    backtest_start_date: date
    backtest_end_date: date | None
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


def parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return pd.to_datetime(str(value)).date()


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"YAML не найден: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_ticker_settings(ticker_lc: str) -> dict[str, Any]:
    return load_yaml(ROOT / ticker_lc / "settings.yaml")


def discover_models(raw_ticker_settings: dict[str, Any]) -> list[str]:
    return sorted((raw_ticker_settings.get("models") or {}).keys())


def build_model_settings(raw_ticker_settings: dict[str, Any], model_dir: str) -> dict[str, Any]:
    settings = deep_merge(
        raw_ticker_settings.get("common") or {},
        raw_ticker_settings.get("model_defaults") or {},
    )
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
    configured_end_date = settings.get("backtest_end_date")
    effective_end_date = end_date if end_date is not None else configured_end_date
    return RunOptions(
        tickers=parse_csv(tickers, settings_tickers),
        models=parse_csv(models, settings_models),
        backtest_start_date=parse_date(start_date or settings["backtest_start_date"]),
        backtest_end_date=parse_date(effective_end_date) if effective_end_date else None,
        train_months=int(train_months if train_months is not None else settings.get("train_months", 6)),
        output_dir=(output_dir or Path(str(settings.get("output_dir", "walk_forward/results")))).resolve(),
        save_daily_artifacts=bool(
            settings.get("save_daily_artifacts", False)
            if save_daily_artifacts is None
            else save_daily_artifacts
        ),
        min_train_rows=int(min_train_rows if min_train_rows is not None else settings.get("min_train_rows", 20)),
        keep_going=bool(settings.get("keep_going", True) if keep_going is None else keep_going),
    )


def load_sentiment(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Файл sentiment PKL не найден: {path}")
    with path.open("rb") as f:
        data = pickle.load(f)

    df = pd.DataFrame(data)
    required = {"source_date", "sentiment", "next_body"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"PKL не содержит обязательные колонки: {missing}. "
            "Запусти sentiment_analysis.py, чтобы дополнить pkl колонкой next_body."
        )

    df["source_date"] = pd.to_datetime(df["source_date"], errors="coerce").dt.date
    df["sentiment"] = pd.to_numeric(df["sentiment"], errors="coerce")
    df["next_body"] = pd.to_numeric(df["next_body"], errors="coerce")
    return df.dropna(subset=["source_date", "sentiment", "next_body"])


def index_by_date(df: pd.DataFrame) -> pd.DataFrame:
    if df["source_date"].duplicated().any():
        dups = df.loc[df["source_date"].duplicated(keep=False), "source_date"].unique()
        raise ValueError(
            f"В pkl несколько строк за одну дату: {sorted(dups)[:5]}... "
            "Перегенерируй pkl: sentiment_analysis.py теперь хранит одну строку на дату."
        )
    return df.set_index("source_date")[["sentiment", "next_body"]].sort_index()


def load_sentiment_pkl(path: Path) -> pd.DataFrame:
    return index_by_date(load_sentiment(path))


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
    save_daily_artifacts: Optional[bool] = typer.Option(
        None,
        "--save-daily-artifacts/--no-save-daily-artifacts",
    ),
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
                    start_date=options.backtest_start_date,
                    end_date=options.backtest_end_date,
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
