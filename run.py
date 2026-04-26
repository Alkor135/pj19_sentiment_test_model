"""
Корневой оркестратор всех тикеров.

Скрипт находит в подпапках корня файлы вида `<ticker>/run_<ticker>.py`
(тикерные оркестраторы) и запускает их по очереди. Каждый тикерный
оркестратор сам перебирает свои модели и для каждой прогоняет
5-шаговый pipeline (sentiment_analysis → sentiment_group_stats →
rules_recommendation → sentiment_backtest → sentiment_to_predict).

Параметры --only и --keep-going прозрачно прокидываются в каждый
тикерный оркестратор — это те же самые флаги, которые понимает
`<ticker>/run_<ticker>.py`.

Запуск:
python run.py
python run.py --only gemma3_12b,gemma4_e2b,gemma4_e4b,qwen2.5_14b,qwen2.5_7b,qwen3_14b --keep-going
python run.py --tickers mix,rts,si,spyf --only gemma3_12b --keep-going
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import typer

ROOT_DIR = Path(__file__).resolve().parent

app = typer.Typer(help="Последовательный запуск пайплайнов всех тикеров.")


def discover_ticker_runners() -> list[Path]:
    """Возвращает отсортированный список оркестраторов вида <ticker>/run_<ticker>.py."""
    runners: list[Path] = []
    for child in sorted(ROOT_DIR.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        candidate = child / f"run_{child.name}.py"
        if candidate.exists():
            runners.append(candidate)
    return runners


def run_ticker(
    runner: Path,
    only: Optional[str],
    keep_going: bool,
    stop_on_error: bool,
) -> tuple[bool, float]:
    """Запускает один тикерный оркестратор и возвращает (успех, время)."""
    ticker_name = runner.parent.name
    typer.echo(f"\n@@@@@@@@@@ {ticker_name.upper()} @@@@@@@@@@")

    cmd = [sys.executable, str(runner)]
    if only:
        cmd += ["--only", only]
    if keep_going:
        cmd.append("--keep-going")

    started = time.monotonic()
    completed = subprocess.run(cmd, cwd=str(runner.parent))
    elapsed = time.monotonic() - started

    if completed.returncode == 0:
        typer.echo(f"[OK]   {ticker_name} ({elapsed:.1f} с)")
        return True, elapsed

    typer.echo(f"[FAIL] {ticker_name} код={completed.returncode} ({elapsed:.1f} с)")
    if stop_on_error:
        raise typer.Exit(code=completed.returncode)
    return False, elapsed


@app.command()
def main(
    only: Optional[str] = typer.Option(
        None,
        "--only",
        help="Список моделей через запятую (прокидывается в --only каждого тикера).",
    ),
    keep_going: bool = typer.Option(
        False,
        "--keep-going/--stop-on-error",
        help="Продолжать прогон при падении тикера/модели (по умолчанию — останавливаться).",
    ),
    tickers: Optional[str] = typer.Option(
        None,
        "--tickers",
        help="Запустить только указанные тикеры через запятую (mix,rts,si,spyf).",
    ),
) -> None:
    """Прогоняет пайплайны всех тикеров или подмножества по --tickers."""
    all_runners = discover_ticker_runners()
    if not all_runners:
        typer.echo(f"Не найдено тикерных оркестраторов в {ROOT_DIR}.")
        raise typer.Exit(code=1)

    if tickers:
        wanted = {s.strip() for s in tickers.split(",") if s.strip()}
        runners = [r for r in all_runners if r.parent.name in wanted]
        unknown = wanted - {r.parent.name for r in all_runners}
        if unknown:
            available = [r.parent.name for r in all_runners]
            raise typer.BadParameter(
                f"Неизвестные тикеры: {sorted(unknown)}. Доступны: {available}"
            )
    else:
        runners = all_runners

    typer.echo(f"Корневая папка: {ROOT_DIR}")
    typer.echo(f"Тикеров к запуску: {len(runners)}")
    for r in runners:
        typer.echo(f"  - {r.parent.name}")
    if only:
        typer.echo(f"Фильтр моделей (--only): {only}")
    typer.echo(f"keep-going: {keep_going}")

    total_started = time.monotonic()
    summary: list[tuple[str, bool, float]] = []
    for runner in runners:
        ok, elapsed = run_ticker(
            runner,
            only=only,
            keep_going=keep_going,
            stop_on_error=not keep_going,
        )
        summary.append((runner.parent.name, ok, elapsed))
    total_elapsed = time.monotonic() - total_started

    typer.echo("\n========== ИТОГ ПО ТИКЕРАМ ==========")
    for name, ok, elapsed in summary:
        marker = "OK  " if ok else "FAIL"
        typer.echo(f"  [{marker}] {name:8s} {elapsed:8.1f} с")
    typer.echo(f"Общее время: {total_elapsed:.1f} с")

    if any(not ok for _, ok, _ in summary):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
