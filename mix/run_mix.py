"""
Оркестратор всех модельных пайплайнов для тикера MIX.

Скрипт находит в подпапках `mix/<model>/` файлы `run_report.py`
(модельные оркестраторы) и запускает их по очереди.

Каждый модельный оркестратор сам прогоняет 5 шагов своего пайплайна
(sentiment_analysis → sentiment_group_stats → rules_recommendation →
sentiment_backtest → sentiment_to_predict). После всех моделей оркестратор
запускает combine-пайплайн в `mix/combine/` (если эта папка есть):
1. `combine/sentiment_combine.py`    — комбинированный бэктест по двум моделям;
2. `combine/sentiment_to_predict.py` — комбинированный прогноз на сегодня.
При запуске с `--only` combine пропускается (так как сужен набор моделей).

Запуск:
python mix/run_mix.py
python mix/run_mix.py --only gemma3_12b,gemma4_e2b,gemma4_e4b,qwen2.5_14b,qwen2.5_7b,qwen3_14b --keep-going
python mix/run_mix.py --keep-going  «продолжать дальше»
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import typer

TICKER_DIR = Path(__file__).resolve().parent

app = typer.Typer(help="Последовательный запуск пайплайнов всех моделей MIX.")


def discover_model_runners() -> list[Path]:
    """Возвращает отсортированный список оркестраторов вида mix/<model>/run_report.py."""
    runners: list[Path] = []
    for child in sorted(TICKER_DIR.iterdir()):
        if not child.is_dir():
            continue
        candidate = child / "run_report.py"
        if candidate.exists():
            runners.append(candidate)
    return runners


def run_model(
    runner: Path,
    stop_on_error: bool,
    label: str | None = None,
) -> tuple[bool, float]:
    """Запускает один скрипт (модельный оркестратор или combine) и возвращает (успех, время)."""
    name = label or runner.parent.name
    typer.echo(f"\n########## {name} ##########")
    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, str(runner)],
        cwd=str(runner.parent),
    )
    elapsed = time.monotonic() - started

    if completed.returncode == 0:
        typer.echo(f"[OK]   {name} ({elapsed:.1f} с)")
        return True, elapsed

    typer.echo(f"[FAIL] {name} код={completed.returncode} ({elapsed:.1f} с)")
    if stop_on_error:
        raise typer.Exit(code=completed.returncode)
    return False, elapsed


@app.command()
def main(
    only: Optional[str] = typer.Option(
        None,
        "--only",
        help="Запустить только указанные модели через запятую (combine при этом пропускается).",
    ),
    keep_going: bool = typer.Option(
        False,
        "--keep-going/--stop-on-error",
        help="Продолжать прогон при падении модели (по умолчанию — останавливаться).",
    ),
) -> None:
    """Прогоняет пайплайны всех моделей MIX или подмножества по --only."""
    all_runners = discover_model_runners()
    if not all_runners:
        typer.echo(f"Не найдено модельных оркестраторов в {TICKER_DIR}.")
        raise typer.Exit(code=1)

    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        runners = [r for r in all_runners if r.parent.name in wanted]
        unknown = wanted - {r.parent.name for r in all_runners}
        if unknown:
            available = [r.parent.name for r in all_runners]
            raise typer.BadParameter(
                f"Неизвестные модели: {sorted(unknown)}. Доступны: {available}"
            )
    else:
        runners = all_runners

    typer.echo(f"Корневая папка: {TICKER_DIR}")
    typer.echo(f"Моделей к запуску: {len(runners)}")
    for r in runners:
        typer.echo(f"  - {r.parent.name}")

    total_started = time.monotonic()
    summary: list[tuple[str, bool, float]] = []
    for runner in runners:
        ok, elapsed = run_model(runner, stop_on_error=not keep_going)
        summary.append((runner.parent.name, ok, elapsed))

    # Combine pipeline (после всех моделей; пропускается при --only).
    if not only:
        combine_dir = TICKER_DIR / "combine"
        if combine_dir.is_dir():
            for script_name in ("sentiment_combine.py", "sentiment_to_predict.py"):
                script = combine_dir / script_name
                if not script.exists():
                    continue
                label = f"combine/{script.stem}"
                ok, elapsed = run_model(
                    script,
                    stop_on_error=not keep_going,
                    label=label,
                )
                summary.append((label, ok, elapsed))

    total_elapsed = time.monotonic() - total_started

    typer.echo("\n========== ИТОГ ==========")
    name_width = max(14, max((len(n) for n, _, _ in summary), default=14))
    for name, ok, elapsed in summary:
        marker = "OK  " if ok else "FAIL"
        typer.echo(f"  [{marker}] {name:{name_width}s} {elapsed:8.1f} с")
    typer.echo(f"Общее время: {total_elapsed:.1f} с")

    if any(not ok for _, ok, _ in summary):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
