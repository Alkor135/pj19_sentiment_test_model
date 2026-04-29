"""
Корневой торговый оркестратор тикеров.

Сначала скрипт синхронизирует RSS-БД и логи через `beget/sync_files.py`.
После успешной синхронизации запускает тикерные торговые оркестраторы вида
`<ticker>/run_<ticker>_trade.py`. Аргументы для каждого тикера задаются
явной структурой `TICKER_TRADE_RUNS` ниже.

Запуск:
.venv/Scripts/python.exe run_trade.py
.venv/Scripts/python.exe run_trade.py --tickers mix,rts
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, TypedDict

import typer


class TickerRunConfig(TypedDict):
    only: list[str]
    keep_going: bool


TICKER_TRADE_RUNS: dict[str, TickerRunConfig] = {
    "mix": {
        "only": [
            "gemma3_12b",
            "gemma4_e2b",
            "gemma4_e4b",
            "qwen2.5_14b",
            "qwen2.5_7b",
            "qwen3_14b",
            "combine",
        ],
        "keep_going": True,
    },
    "ng": {
        "only": [
            "gemma3_12b",
            "gemma4_e2b",
            "gemma4_e4b",
            "qwen2.5_14b",
            "qwen2.5_7b",
            "qwen3_14b",
            "combine",
        ],
        "keep_going": True,
    },
    "rts": {
        "only": [
            "gemma3_12b",
            "gemma4_e2b",
            "gemma4_e4b",
            "qwen2.5_14b",
            "qwen2.5_7b",
            "qwen3_14b",
            "combine",
        ],
        "keep_going": True,
    },
    "si": {
        "only": [
            "gemma3_12b",
            "gemma4_e2b",
            "gemma4_e4b",
            "qwen2.5_14b",
            "qwen2.5_7b",
            "qwen3_14b",
            "combine",
        ],
        "keep_going": True,
    },
    "spyf": {
        "only": [
            "gemma3_12b",
            "gemma4_e2b",
            "gemma4_e4b",
            "qwen2.5_14b",
            "qwen2.5_7b",
            "qwen3_14b",
            "combine",
        ],
        "keep_going": True,
    },
}


ROOT_DIR = Path(__file__).resolve().parent
BEGET_SYNC = ROOT_DIR / "beget" / "sync_files.py"

app = typer.Typer(help="Последовательный запуск торговых пайплайнов тикеров.")


def select_ticker_runs(
    runs: dict[str, TickerRunConfig],
    tickers: Optional[str],
) -> dict[str, TickerRunConfig]:
    """Возвращает конфиги выбранных тикеров в порядке `runs`."""
    if not tickers:
        return runs

    wanted = {s.strip() for s in tickers.split(",") if s.strip()}
    unknown = wanted - set(runs)
    if unknown:
        raise typer.BadParameter(
            f"Неизвестные тикеры: {sorted(unknown)}. Доступны: {sorted(runs)}"
        )
    return {ticker: config for ticker, config in runs.items() if ticker in wanted}


def build_ticker_command(runner: Path, config: TickerRunConfig) -> list[str]:
    """Собирает команду запуска тикерного trade-оркестратора."""
    cmd = [sys.executable, str(runner)]
    if config["only"]:
        cmd += ["--only", ",".join(config["only"])]
    if config["keep_going"]:
        cmd.append("--keep-going")
    return cmd


def run_ticker(ticker: str, config: TickerRunConfig) -> tuple[bool, float]:
    """Запускает один тикерный trade-оркестратор и возвращает (успех, время)."""
    runner = ROOT_DIR / ticker / f"run_{ticker}_trade.py"
    if not runner.exists():
        raise typer.BadParameter(f"Не найден оркестратор тикера: {runner}")

    typer.echo(f"\n@@@@@@@@@@ {ticker.upper()} @@@@@@@@@@")
    typer.echo(f"only: {','.join(config['only'])}")
    typer.echo(f"keep-going: {config['keep_going']}")

    started = time.monotonic()
    completed = subprocess.run(
        build_ticker_command(runner, config),
        cwd=str(runner.parent),
    )
    elapsed = time.monotonic() - started

    if completed.returncode == 0:
        typer.echo(f"[OK]   {ticker} ({elapsed:.1f} с)")
        return True, elapsed

    typer.echo(f"[FAIL] {ticker} код={completed.returncode} ({elapsed:.1f} с)")
    if not config["keep_going"]:
        raise typer.Exit(code=completed.returncode)
    return False, elapsed


def run_beget_sync() -> tuple[bool, float]:
    """Запускает обязательную синхронизацию RSS-БД перед торговым пайплайном."""
    if not BEGET_SYNC.exists():
        raise typer.BadParameter(f"Не найден скрипт синхронизации: {BEGET_SYNC}")

    typer.echo("\n========== BEGET SYNC ==========")
    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, str(BEGET_SYNC)],
        cwd=str(BEGET_SYNC.parent),
    )
    elapsed = time.monotonic() - started

    if completed.returncode == 0:
        typer.echo(f"[OK]   beget/sync_files.py ({elapsed:.1f} с)")
        return True, elapsed

    typer.echo(f"[FAIL] beget/sync_files.py код={completed.returncode} ({elapsed:.1f} с)")
    raise typer.Exit(code=completed.returncode)


@app.command()
def main(
    tickers: Optional[str] = typer.Option(
        None,
        "--tickers",
        help="Запустить только указанные тикеры через запятую (mix,ng,rts,si,spyf).",
    ),
) -> None:
    """Прогоняет торговые пайплайны тикеров по `TICKER_TRADE_RUNS`."""
    runs = select_ticker_runs(TICKER_TRADE_RUNS, tickers)
    if not runs:
        typer.echo("Не выбрано ни одного тикера.")
        raise typer.Exit(code=1)

    typer.echo(f"Корневая папка: {ROOT_DIR}")
    typer.echo(f"Тикеров к запуску: {len(runs)}")
    for ticker in runs:
        typer.echo(f"  - {ticker}")

    total_started = time.monotonic()
    summary: list[tuple[str, bool, float]] = []
    ok, elapsed = run_beget_sync()
    summary.append(("beget", ok, elapsed))

    for ticker, config in runs.items():
        ok, elapsed = run_ticker(ticker, config)
        summary.append((ticker, ok, elapsed))
    total_elapsed = time.monotonic() - total_started

    typer.echo("\n========== ИТОГ ПО ТИКЕРАМ ==========")
    for ticker, ok, elapsed in summary:
        marker = "OK  " if ok else "FAIL"
        typer.echo(f"  [{marker}] {ticker:8s} {elapsed:8.1f} с")
    typer.echo(f"Общее время: {total_elapsed:.1f} с")

    if any(not ok for _, ok, _ in summary):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
