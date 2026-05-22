"""Вспомогательная логика оперативного walk-forward для модельных торговых скриптов.

Функции модуля намеренно переиспользуют ``walk_forward.core`` для окон
обучения, групповой статистики, рекомендаций правил и исторического
walk-forward-бэктеста. Тонкие скрипты в ``<ticker>/<model>/`` должны вызывать
эти вспомогательные функции, а не хранить собственные копии расчётной логики.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from html import escape
import importlib.util
from pathlib import Path
import pickle
import subprocess
import sys
import time
from typing import Any, Optional

import pandas as pd
import typer
import yaml

from walk_forward.core import (
    WalkForwardModelResult,
    build_follow_trades,
    build_rules_recommendation,
    direction_for_action,
    group_by_sentiment,
    match_action,
    render_rules_yaml,
    run_walk_forward_model,
    training_window_for,
)


RULES_WF_FILENAME = "rules_wf.yaml"
GROUP_STATS_WF_FILENAME = "sentiment_group_stats_wf.xlsx"
BACKTEST_WF_FILENAME = "sentiment_backtest_results_wf.xlsx"
BACKTEST_WF_HTML_FILENAME = "sentiment_backtest_wf.html"
DEFAULT_CHROME_PATH = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


@dataclass(frozen=True)
class ModelContext:
    """Разрешённые пути и настройки одной модельной папки."""

    model_path: Path
    ticker_path: Path
    model_dir: str
    settings: dict[str, Any]
    ticker: str
    sentiment_model: str
    quantity: int
    sentiment_pkl: Path
    predict_path: Path


@dataclass(frozen=True)
class LiveRulesResult:
    """Артефакты, созданные для одного оперативного walk-forward окна правил."""

    rules_path: Path
    group_stats_path: Path
    train_start: date
    train_end: date
    train_rows: int
    rules: list[dict[str, Any]]
    grouped: pd.DataFrame


@dataclass(frozen=True)
class BacktestWfReportResult:
    """Артефакты модельного walk-forward отчёта."""

    xlsx_path: Path
    html_path: Path
    trades: pd.DataFrame


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Рекурсивно объединяет два словаря настроек без изменения исходников."""

    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _apply_placeholders(settings: dict[str, Any], model_dir: str) -> dict[str, Any]:
    """Подставляет стандартные плейсхолдеры тикера и модели в строках настроек."""

    ticker = str(settings.get("ticker", ""))
    ticker_lc = str(settings.get("ticker_lc", ticker.lower()))
    replacements = {
        "{ticker}": ticker,
        "{ticker_lc}": ticker_lc,
        "{model_dir}": model_dir,
    }
    out = deepcopy(settings)
    for key, value in list(out.items()):
        if isinstance(value, str):
            for old, new in replacements.items():
                value = value.replace(old, new)
            out[key] = value
    return out


def _parse_date(value: Any) -> date | None:
    """Преобразует дату из settings/CLI в ``date`` или ``None``."""

    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return pd.to_datetime(str(value)).date()


def _load_yaml(path: Path) -> dict[str, Any]:
    """Читает YAML-файл как словарь."""

    if not path.exists():
        raise FileNotFoundError(f"YAML не найден: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_model_context(script_file: str | Path) -> ModelContext:
    """Загружает объединённые настройки модели для скрипта в ``<ticker>/<model>/``."""

    model_path = Path(script_file).resolve().parent
    ticker_path = model_path.parent
    raw = _load_yaml(ticker_path / "settings.yaml")
    model_dir = model_path.name

    settings = _deep_merge(raw.get("common") or {}, raw.get("model_defaults") or {})
    settings = _deep_merge(settings, (raw.get("models") or {}).get(model_dir) or {})
    settings["model_dir"] = model_dir
    settings = _apply_placeholders(settings, model_dir)

    sentiment_path = Path(str(settings.get("sentiment_output_pkl", "sentiment_scores.pkl")))
    if not sentiment_path.is_absolute():
        sentiment_path = model_path / sentiment_path

    predict_path = Path(str(settings.get("predict_path", model_path / "predict")))
    if not predict_path.is_absolute():
        predict_path = model_path / predict_path

    return ModelContext(
        model_path=model_path,
        ticker_path=ticker_path,
        model_dir=model_dir,
        settings=settings,
        ticker=str(settings.get("ticker", ticker_path.name.upper())),
        sentiment_model=str(settings.get("sentiment_model", model_dir)),
        quantity=int(settings.get("quantity_test", 1)),
        sentiment_pkl=sentiment_path,
        predict_path=predict_path,
    )


def load_sentiment(path: Path) -> pd.DataFrame:
    """Загружает sentiment PKL и нормализует обязательные колонки."""

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
    """Индексирует sentiment-строки по дате и проверяет уникальность дат."""

    if df["source_date"].duplicated().any():
        dups = df.loc[df["source_date"].duplicated(keep=False), "source_date"].unique()
        raise ValueError(
            f"В pkl несколько строк за одну дату: {sorted(dups)[:5]}... "
            "Перегенерируй pkl: sentiment_analysis.py хранит одну строку на дату."
        )
    return df.set_index("source_date")[["sentiment", "next_body"]].sort_index()


def load_indexed_sentiment(path: Path) -> pd.DataFrame:
    """Загружает sentiment PKL как индексированный DataFrame."""

    return index_by_date(load_sentiment(path))


def _effective_train_months(settings: dict[str, Any], train_months: int | None) -> int:
    value = train_months if train_months is not None else settings.get("rules_train_months", 6)
    return int(value)


def _effective_min_train_rows(settings: dict[str, Any], min_train_rows: int | None) -> int:
    value = min_train_rows if min_train_rows is not None else settings.get("rules_min_train_rows", 20)
    return int(value)


def build_live_rules(
    indexed: pd.DataFrame,
    *,
    target_date: date,
    train_months: int,
    min_train_rows: int,
    quantity: int,
) -> tuple[pd.DataFrame, list[dict[str, Any]], date, date]:
    """Строит групповую статистику и правила для оперативного WF-окна перед целевой датой."""

    train_start, train_end = training_window_for(target_date, train_months)
    train = indexed.loc[(indexed.index >= train_start) & (indexed.index <= train_end)].copy()

    if len(train) < min_train_rows:
        raise ValueError(
            f"Недостаточно строк обучения для WF-правил: {len(train)} < {min_train_rows} "
            f"({train_start}..{train_end})"
        )

    grouped = group_by_sentiment(build_follow_trades(train, quantity))
    rules = build_rules_recommendation(grouped)
    return grouped, rules, train_start, train_end


def write_rules_wf_outputs(
    script_file: str | Path,
    *,
    target_date: date | None = None,
    train_months: int | None = None,
    min_train_rows: int | None = None,
) -> LiveRulesResult:
    """Строит оперативные WF-правила и пишет ``rules_wf.yaml`` плюс XLSX групповой статистики."""

    context = load_model_context(script_file)
    target = target_date or date.today()
    effective_train_months = _effective_train_months(context.settings, train_months)
    effective_min_train_rows = _effective_min_train_rows(context.settings, min_train_rows)

    indexed = load_indexed_sentiment(context.sentiment_pkl)
    grouped, rules, train_start, train_end = build_live_rules(
        indexed,
        target_date=target,
        train_months=effective_train_months,
        min_train_rows=effective_min_train_rows,
        quantity=context.quantity,
    )

    group_stats_path = context.model_path / "group_stats" / GROUP_STATS_WF_FILENAME
    group_stats_path.parent.mkdir(parents=True, exist_ok=True)
    grouped.to_excel(group_stats_path, index=False)

    rules_path = context.model_path / RULES_WF_FILENAME
    rules_path.write_text(
        render_rules_yaml(
            rules,
            ticker=context.ticker,
            sentiment_model=context.sentiment_model,
            test_date=target,
            train_start=train_start,
            train_end=train_end,
        ),
        encoding="utf-8",
    )

    return LiveRulesResult(
        rules_path=rules_path,
        group_stats_path=group_stats_path,
        train_start=train_start,
        train_end=train_end,
        train_rows=int(len(indexed.loc[(indexed.index >= train_start) & (indexed.index <= train_end)])),
        rules=rules,
        grouped=grouped,
    )


def load_rules(path: Path) -> list[dict[str, Any]]:
    """Загружает и валидирует YAML-файл правил."""

    data = _load_yaml(path)
    rules = data.get("rules") or []
    if not isinstance(rules, list) or not rules:
        raise ValueError(f"В {path} нет списка 'rules' или он пустой")
    for i, rule in enumerate(rules):
        for key in ("min", "max", "action"):
            if key not in rule:
                raise ValueError(f"Правило #{i} без поля '{key}': {rule}")
        if str(rule["action"]) not in {"follow", "invert", "skip"}:
            raise ValueError(
                f"Правило #{i}: action должен быть follow/invert/skip, "
                f"получено {rule['action']!r}"
            )
        if float(rule["min"]) > float(rule["max"]):
            raise ValueError(f"Правило #{i}: min > max ({rule})")
    return rules


def get_sentiment_for_date(indexed: pd.DataFrame, target_date: date) -> float | None:
    """Возвращает sentiment за целевую дату или ``None``, если строки нет."""

    if target_date not in indexed.index:
        return None
    row = indexed.loc[target_date]
    if isinstance(row, pd.DataFrame):
        raise ValueError(
            f"В pkl несколько строк за {target_date}: ожидалась одна. "
            "Перегенерируй pkl: sentiment_analysis.py хранит одну строку на дату."
        )
    return float(row["sentiment"])


def predict_file_date(path: Path) -> date | None:
    """Возвращает дату из имени файла прогноза ``YYYY-MM-DD.txt``."""

    try:
        return datetime.strptime(path.stem, "%Y-%m-%d").date()
    except ValueError:
        return None


def should_delete_existing_predict_file(out_file: Path, target_date: date, time_start: str) -> bool:
    """Повторяет старую логику: заменять только сегодняшний файл до ``time_start``."""

    if predict_file_date(out_file) != target_date or not out_file.exists():
        return False
    cutoff = datetime.combine(target_date, datetime.strptime(time_start, "%H:%M:%S").time())
    file_mtime = datetime.fromtimestamp(out_file.stat().st_mtime)
    return file_mtime.date() == target_date and file_mtime < cutoff


def write_predict_file(
    out_file: Path,
    target_date: date,
    direction: str,
    status: str,
    *,
    sentiment: float | None = None,
    action: str | None = None,
    note: str = "",
) -> None:
    """Атомарно пишет файл прогноза, совместимый с торговыми скриптами."""

    sentiment_label = f"{sentiment:.2f}" if sentiment is not None else "n/a"
    action_label = action if action is not None else "n/a"
    lines = [
        f"Дата: {target_date:%Y-%m-%d}",
        f"Sentiment: {sentiment_label}",
        f"Action: {action_label}",
        f"Status: {status}",
    ]
    if note:
        lines.append(f"Note: {note}")
    lines.append(f"Предсказанное направление: {direction}")
    content = "\n".join(lines) + "\n"

    out_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = out_file.with_suffix(out_file.suffix + ".tmp")
    tmp_file.write_text(content, encoding="utf-8")
    tmp_file.replace(out_file)


def _direction_label(sentiment: float, action: str) -> str:
    """Преобразует действие WF в метку прогноза up/down/skip."""

    if action == "skip":
        return "skip"
    direction = direction_for_action(sentiment, action)
    return "up" if direction == "LONG" else "down"


def write_predict_wf(
    script_file: str | Path,
    *,
    target_date: date | None = None,
) -> Path:
    """Применяет ``rules_wf.yaml`` к sentiment за целевую дату и пишет прогноз."""

    context = load_model_context(script_file)
    target = target_date or date.today()
    out_file = context.predict_path / f"{target:%Y-%m-%d}.txt"

    if out_file.exists():
        time_start = str(context.settings.get("time_start", "21:00:00"))
        if should_delete_existing_predict_file(out_file, target, time_start):
            out_file.unlink()
        else:
            return out_file

    try:
        rules = load_rules(context.model_path / RULES_WF_FILENAME)
        indexed = load_indexed_sentiment(context.sentiment_pkl)
        sentiment = get_sentiment_for_date(indexed, target)
        if sentiment is None:
            write_predict_file(
                out_file,
                target,
                "skip",
                "no_pkl_row",
                note=f"в sentiment_scores.pkl нет строки за {target:%Y-%m-%d}",
            )
            return out_file

        action = match_action(sentiment, rules)
        direction = _direction_label(sentiment, action)
        status = "ok" if direction != "skip" else "no_trade"
        write_predict_file(
            out_file,
            target,
            direction,
            status,
            sentiment=sentiment,
            action=action,
        )
        return out_file
    except FileNotFoundError as exc:
        write_predict_file(out_file, target, "skip", "missing_file", note=str(exc))
        return out_file
    except ValueError as exc:
        write_predict_file(out_file, target, "skip", "error", note=str(exc))
        return out_file


def write_backtest_wf_outputs(
    script_file: str | Path,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    train_months: int | None = None,
    min_train_rows: int | None = None,
) -> Path:
    """Запускает WF-бэктест модели и пишет XLSX сделок в ``backtest/``."""

    context, result = run_backtest_wf(
        script_file,
        start_date=start_date,
        end_date=end_date,
        train_months=train_months,
        min_train_rows=min_train_rows,
    )
    return write_backtest_wf_xlsx(context, result.trades)


def run_backtest_wf(
    script_file: str | Path,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    train_months: int | None = None,
    min_train_rows: int | None = None,
) -> tuple[ModelContext, WalkForwardModelResult]:
    """Считает WF-бэктест модели и возвращает контекст плюс расчётный результат."""

    context = load_model_context(script_file)
    indexed = load_indexed_sentiment(context.sentiment_pkl)

    configured_start = (
        start_date
        or _parse_date(context.settings.get("wf_backtest_date_from"))
        or _parse_date(context.settings.get("backtest_date_from"))
        or min(indexed.index)
    )
    configured_end = (
        end_date
        or _parse_date(context.settings.get("wf_backtest_date_to"))
        or _parse_date(context.settings.get("backtest_date_to"))
    )

    result = run_walk_forward_model(
        indexed=indexed,
        ticker=context.ticker,
        model_dir=context.model_dir,
        sentiment_model=context.sentiment_model,
        quantity=context.quantity,
        start_date=configured_start,
        end_date=configured_end,
        train_months=_effective_train_months(context.settings, train_months),
        min_train_rows=_effective_min_train_rows(context.settings, min_train_rows),
    )

    return context, result


def write_backtest_wf_xlsx(context: ModelContext, trades: pd.DataFrame) -> Path:
    """Пишет XLSX WF-бэктеста модели в ``backtest/``."""

    output_xlsx = context.model_path / "backtest" / BACKTEST_WF_FILENAME
    output_xlsx.parent.mkdir(parents=True, exist_ok=True)
    trades.to_excel(output_xlsx, index=False)
    return output_xlsx


def _load_model_backtest_module(context: ModelContext):
    """Импортирует модельный ``sentiment_backtest.py`` для переиспользования HTML-отчёта."""

    module_path = context.model_path / "sentiment_backtest.py"
    if not module_path.exists():
        raise FileNotFoundError(f"Скрипт построения HTML не найден: {module_path}")

    module_name = f"_wf_sentiment_backtest_{context.ticker_path.name}_{context.model_dir}_{id(context)}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Не удалось загрузить модуль: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_empty_backtest_wf_html(
    output_html: Path,
    *,
    context: ModelContext,
    reason: str,
) -> None:
    """Пишет минимальный HTML, если WF-бэктест не дал ни одной сделки."""

    output_html.parent.mkdir(parents=True, exist_ok=True)
    title = f"{context.ticker} {context.sentiment_model} WF-бэктест"
    output_html.write_text(
        "\n".join(
            [
                "<!doctype html>",
                "<html lang=\"ru\">",
                "<head>",
                "  <meta charset=\"utf-8\">",
                f"  <title>{escape(title)}</title>",
                "</head>",
                "<body>",
                f"  <h1>{escape(title)}</h1>",
                f"  <p>{escape(reason)}</p>",
                "</body>",
                "</html>",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_backtest_wf_html(context: ModelContext, trades: pd.DataFrame) -> Path:
    """Пишет Plotly HTML WF-бэктеста без генерации QuantStats-отчёта."""

    output_html = context.model_path / "plots" / BACKTEST_WF_HTML_FILENAME
    output_html.parent.mkdir(parents=True, exist_ok=True)

    if trades.empty:
        _write_empty_backtest_wf_html(
            output_html,
            context=context,
            reason="WF-бэктест не сформировал сделок для выбранного периода.",
        )
        return output_html

    module = _load_model_backtest_module(context)
    build_report = getattr(module, "build_report", None)
    if not callable(build_report):
        raise AttributeError(f"В {context.model_path / 'sentiment_backtest.py'} нет build_report()")

    build_report(
        trades.copy(),
        context.ticker,
        context.sentiment_model,
        output_html,
        context.model_path / RULES_WF_FILENAME,
    )
    return output_html


def write_backtest_wf_report(
    script_file: str | Path,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    train_months: int | None = None,
    min_train_rows: int | None = None,
) -> BacktestWfReportResult:
    """Запускает WF-бэктест модели и пишет XLSX плюс HTML-отчёт."""

    context, result = run_backtest_wf(
        script_file,
        start_date=start_date,
        end_date=end_date,
        train_months=train_months,
        min_train_rows=min_train_rows,
    )
    xlsx_path = write_backtest_wf_xlsx(context, result.trades)
    html_path = write_backtest_wf_html(context, result.trades)
    return BacktestWfReportResult(xlsx_path=xlsx_path, html_path=html_path, trades=result.trades)


def open_html_reports_in_chrome(chrome_path: Path, reports: list[Path]) -> None:
    """Открывает HTML-отчёты в одном новом окне Google Chrome."""

    if not reports:
        return
    if not chrome_path.exists():
        raise FileNotFoundError(f"Google Chrome не найден: {chrome_path}")
    subprocess.Popen([str(chrome_path), "--new-window", *[str(p) for p in reports]])


def discover_model_fw_runners(ticker_dir: Path) -> list[Path]:
    """Находит модельные ``run_report_fw.py`` в папке тикера."""

    runners: list[Path] = []
    for child in sorted(ticker_dir.iterdir()):
        if not child.is_dir() or child.name in {"combine", "shared"}:
            continue
        candidate = child / "run_report_fw.py"
        if candidate.exists():
            runners.append(candidate)
    return runners


def _build_model_fw_args(
    *,
    start_date: str | None,
    end_date: str | None,
    train_months: int | None,
    min_train_rows: int | None,
) -> list[str]:
    """Формирует CLI-аргументы для модельного ``run_report_fw.py``."""

    args = ["--no-open-browser"]
    if start_date:
        args.extend(["--start-date", start_date])
    if end_date:
        args.extend(["--end-date", end_date])
    if train_months is not None:
        args.extend(["--train-months", str(train_months)])
    if min_train_rows is not None:
        args.extend(["--min-train-rows", str(min_train_rows)])
    return args


def run_model_fw_report(
    runner: Path,
    *,
    model_args: list[str],
    stop_on_error: bool,
) -> tuple[str, float, Path | None]:
    """Запускает WF-отчёт одной модели через её wrapper-скрипт."""

    name = runner.parent.name
    typer.echo(f"\n########## {name} ##########")

    context = load_model_context(runner)
    if not context.sentiment_pkl.exists():
        typer.echo(f"[SKIP] {name}: sentiment PKL не найден: {context.sentiment_pkl}")
        return "skip", 0.0, None

    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, str(runner), *model_args],
        cwd=str(runner.parent),
    )
    elapsed = time.monotonic() - started

    if completed.returncode == 0:
        html_path = runner.parent / "plots" / BACKTEST_WF_HTML_FILENAME
        if not html_path.exists():
            typer.echo(f"[WARN] {name}: HTML не найден после успешного запуска: {html_path}")
            html_path = None
        typer.echo(f"[OK]   {name} ({elapsed:.1f} с)")
        return "ok", elapsed, html_path

    typer.echo(f"[FAIL] {name} код={completed.returncode} ({elapsed:.1f} с)")
    if stop_on_error:
        raise typer.Exit(code=completed.returncode)
    return "fail", elapsed, None


def rules_recommendation_wf_app(script_file: str | Path) -> typer.Typer:
    """Создаёт Typer-приложение для генерации WF-правил модели."""

    app = typer.Typer(help="Строит оперативный WF rules_wf.yaml по последнему обучающему окну.")

    @app.command()
    def main(
        target_date: Optional[str] = typer.Option(None, "--target-date", help="Дата прогноза YYYY-MM-DD."),
        train_months: Optional[int] = typer.Option(None, "--train-months", help="Количество месяцев истории."),
        min_train_rows: Optional[int] = typer.Option(None, "--min-train-rows", help="Минимум строк обучения."),
    ) -> None:
        result = write_rules_wf_outputs(
            script_file,
            target_date=_parse_date(target_date) if target_date else None,
            train_months=train_months,
            min_train_rows=min_train_rows,
        )
        typer.echo(
            f"WF обучение: {result.train_start} .. {result.train_end} "
            f"строк={result.train_rows}"
        )
        typer.echo(f"XLSX групповой статистики сохранён: {result.group_stats_path}")
        typer.echo(f"YAML правил сохранён: {result.rules_path}")

    return app


def sentiment_to_predict_wf_app(script_file: str | Path) -> typer.Typer:
    """Создаёт Typer-приложение для WF-прогноза модели."""

    app = typer.Typer(help="Пишет прогноз по rules_wf.yaml для целевой даты.")

    @app.command()
    def main(
        target_date: Optional[str] = typer.Option(None, "--target-date", help="Дата прогноза YYYY-MM-DD."),
    ) -> None:
        out_file = write_predict_wf(
            script_file,
            target_date=_parse_date(target_date) if target_date else None,
        )
        typer.echo(f"WF-прогноз сохранён: {out_file}")

    return app


def sentiment_backtest_wf_app(script_file: str | Path) -> typer.Typer:
    """Создаёт Typer-приложение для экспорта WF-бэктеста модели в XLSX и HTML."""

    app = typer.Typer(help="Пишет XLSX и HTML WF-бэктеста модели.")

    @app.command()
    def main(
        start_date: Optional[str] = typer.Option(None, "--start-date", help="Дата начала YYYY-MM-DD."),
        end_date: Optional[str] = typer.Option(None, "--end-date", help="Дата окончания YYYY-MM-DD."),
        train_months: Optional[int] = typer.Option(None, "--train-months", help="Количество месяцев истории."),
        min_train_rows: Optional[int] = typer.Option(None, "--min-train-rows", help="Минимум строк обучения."),
    ) -> None:
        report = write_backtest_wf_report(
            script_file,
            start_date=_parse_date(start_date) if start_date else None,
            end_date=_parse_date(end_date) if end_date else None,
            train_months=train_months,
            min_train_rows=min_train_rows,
        )
        typer.echo(f"XLSX WF-бэктеста сохранён: {report.xlsx_path}")
        typer.echo(f"HTML WF-бэктеста сохранён: {report.html_path}")

    return app


def run_report_fw_app(script_file: str | Path) -> typer.Typer:
    """Создаёт Typer-приложение для модельного WF-отчёта с открытием HTML."""

    app = typer.Typer(help="Строит WF-отчёт модели без QuantStats и открывает HTML.")

    @app.command()
    def main(
        start_date: Optional[str] = typer.Option(None, "--start-date", help="Дата начала YYYY-MM-DD."),
        end_date: Optional[str] = typer.Option(None, "--end-date", help="Дата окончания YYYY-MM-DD."),
        train_months: Optional[int] = typer.Option(None, "--train-months", help="Количество месяцев истории."),
        min_train_rows: Optional[int] = typer.Option(None, "--min-train-rows", help="Минимум строк обучения."),
        open_browser: bool = typer.Option(
            True,
            "--open-browser/--no-open-browser",
            help="Открывать созданный HTML в новом окне Chrome.",
        ),
        chrome_path: Path = typer.Option(
            DEFAULT_CHROME_PATH,
            "--chrome-path",
            help="Путь к chrome.exe.",
        ),
    ) -> None:
        report = write_backtest_wf_report(
            script_file,
            start_date=_parse_date(start_date) if start_date else None,
            end_date=_parse_date(end_date) if end_date else None,
            train_months=train_months,
            min_train_rows=min_train_rows,
        )
        typer.echo(f"XLSX WF-бэктеста сохранён: {report.xlsx_path}")
        typer.echo(f"HTML WF-бэктеста сохранён: {report.html_path}")

        if open_browser:
            try:
                open_html_reports_in_chrome(chrome_path, [report.html_path])
            except FileNotFoundError as exc:
                raise typer.BadParameter(str(exc)) from exc
            typer.echo(f"Открываю HTML в Chrome: {report.html_path}")

    return app


def run_ticker_report_fw_app(script_file: str | Path) -> typer.Typer:
    """Создаёт Typer-приложение для WF-отчётов всех моделей одного тикера."""

    ticker_dir = Path(script_file).resolve().parent
    ticker_name = ticker_dir.name.upper()
    app = typer.Typer(
        help=f"Последовательный запуск WF-отчётов всех моделей {ticker_name}."
    )

    @app.command()
    def main(
        only: Optional[str] = typer.Option(
            None,
            "--only",
            help="Запустить только указанные модели через запятую.",
        ),
        keep_going: bool = typer.Option(
            False,
            "--keep-going/--stop-on-error",
            help="Продолжать прогон при падении модели.",
        ),
        start_date: Optional[str] = typer.Option(None, "--start-date", help="Дата начала YYYY-MM-DD."),
        end_date: Optional[str] = typer.Option(None, "--end-date", help="Дата окончания YYYY-MM-DD."),
        train_months: Optional[int] = typer.Option(None, "--train-months", help="Количество месяцев истории."),
        min_train_rows: Optional[int] = typer.Option(None, "--min-train-rows", help="Минимум строк обучения."),
        open_browser: bool = typer.Option(
            True,
            "--open-browser/--no-open-browser",
            help="Открывать созданные HTML в одном новом окне Chrome.",
        ),
        chrome_path: Path = typer.Option(
            DEFAULT_CHROME_PATH,
            "--chrome-path",
            help="Путь к chrome.exe.",
        ),
    ) -> None:
        all_runners = discover_model_fw_runners(ticker_dir)
        if not all_runners:
            typer.echo(f"Не найдено модельных run_report_fw.py в {ticker_dir}.")
            raise typer.Exit(code=1)

        if only:
            wanted = {s.strip() for s in only.split(",") if s.strip()}
            available = {runner.parent.name for runner in all_runners}
            unknown = wanted - available
            if unknown:
                raise typer.BadParameter(
                    f"Неизвестные модели: {sorted(unknown)}. Доступны: {sorted(available)}"
                )
            runners = [runner for runner in all_runners if runner.parent.name in wanted]
        else:
            runners = all_runners

        model_args = _build_model_fw_args(
            start_date=start_date,
            end_date=end_date,
            train_months=train_months,
            min_train_rows=min_train_rows,
        )

        typer.echo(f"Корневая папка: {ticker_dir}")
        typer.echo(f"Моделей к запуску: {len(runners)}")
        for runner in runners:
            typer.echo(f"  - {runner.parent.name}")

        total_started = time.monotonic()
        summary: list[tuple[str, str, float]] = []
        html_reports: list[Path] = []
        for runner in runners:
            status, elapsed, html_path = run_model_fw_report(
                runner,
                model_args=model_args,
                stop_on_error=not keep_going,
            )
            summary.append((runner.parent.name, status, elapsed))
            if html_path is not None:
                html_reports.append(html_path)

        total_elapsed = time.monotonic() - total_started

        typer.echo("\n========== ИТОГ ==========")
        name_width = max(14, max((len(name) for name, _, _ in summary), default=14))
        for name, status, elapsed in summary:
            marker = {"ok": "OK  ", "skip": "SKIP", "fail": "FAIL"}[status]
            typer.echo(f"  [{marker}] {name:{name_width}s} {elapsed:8.1f} с")
        typer.echo(f"Общее время: {total_elapsed:.1f} с")

        if open_browser and html_reports:
            try:
                open_html_reports_in_chrome(chrome_path, html_reports)
            except FileNotFoundError as exc:
                raise typer.BadParameter(str(exc)) from exc
            typer.echo(f"Открываю {len(html_reports)} HTML-отчётов в Chrome:")
            for path in html_reports:
                typer.echo(f"  [ОТКРЫВАЮ] {path.relative_to(ticker_dir)}")

        if any(status == "fail" for _, status, _ in summary):
            raise typer.Exit(code=1)

    return app
