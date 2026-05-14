"""
Оркестратор pj19 для ручного запуска полного sentiment-пайплайна.

Это намеренно простой файл-расписание: порядок запуска меняется переносом строк
в HARD_STEPS и SOFT_STEPS. HARD_STEPS останавливают весь пайплайн при ошибке;
SOFT_STEPS логируют ошибку и продолжают выполнение.

По умолчанию включены активные тикеры и модели из ручного расписания
`HARD_STEPS`/`SOFT_STEPS` и корневого `run_report.py`:
mix, ng, rts, si, spyf; gemma3_12b, gemma4_e2b, gemma4_e4b,
qwen2.5_14b, qwen2.5_7b, qwen3_14b.

Запуск:
.venv/Scripts/python.exe run_all.py

Регистрация в планировщике Windows:
schtasks /Create /SC DAILY /ST 21:00:05 /TN "pj19_run_all_test" ^
    /TR "C:\\Users\\Alkor\\VSCode\\pj19_sentiment_test_model\\.venv\\Scripts\\python.exe C:\\Users\\Alkor\\VSCode\\pj19_sentiment_test_model\\run_all.py"
"""

from __future__ import annotations

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from orchestrator_logging import build_handlers

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "log"
LOG_DIR.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file = LOG_DIR / f"run_all_{timestamp}.txt"


logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=build_handlers(log_file),
    force=True,
)
logger = logging.getLogger("run_all")

for old in sorted(LOG_DIR.glob("run_all_*.txt"))[:-3]:
    try:
        old.unlink()
    except OSError:
        pass


HARD_STEPS: list[Path] = [
    # Общий этап: синхронизация RSS-БД и логов с удалённого сервера.
    ROOT / "beget" / "sync_files.py",

    # ==================== MIX ====================
    ROOT / "mix" / "shared" / "download_minutes_to_db.py",
    ROOT / "mix" / "shared" / "convert_minutes_to_days.py",
    ROOT / "mix" / "shared" / "create_markdown_files.py",

    ROOT / "mix" / "gemma3_12b" / "sentiment_analysis.py",
    # ROOT / "mix" / "gemma3_12b" / "sentiment_group_stats.py",
    # ROOT / "mix" / "gemma3_12b" / "rules_recommendation.py",
    ROOT / "mix" / "gemma3_12b" / "sentiment_to_predict.py",

    ROOT / "mix" / "gemma4_e2b" / "sentiment_analysis.py",
    # ROOT / "mix" / "gemma4_e2b" / "sentiment_group_stats.py",
    # ROOT / "mix" / "gemma4_e2b" / "rules_recommendation.py",
    ROOT / "mix" / "gemma4_e2b" / "sentiment_to_predict.py",

    ROOT / "mix" / "combine" / "sentiment_combine.py",
    ROOT / "mix" / "combine" / "sentiment_to_predict.py",

    ROOT / "trade" / "trade_mix_ebs.py",

    # ==================== RTS ====================
    ROOT / "rts" / "shared" / "download_minutes_to_db.py",
    ROOT / "rts" / "shared" / "convert_minutes_to_days.py",
    # ROOT / "rts" / "shared" / "create_markdown_files.py",

    ROOT / "rts" / "gemma4_e2b" / "sentiment_analysis.py",
    # ROOT / "rts" / "gemma4_e2b" / "sentiment_group_stats.py",
    # ROOT / "rts" / "gemma4_e2b" / "rules_recommendation.py",
    ROOT / "rts" / "gemma4_e2b" / "sentiment_to_predict.py",

    ROOT / "rts" / "gemma4_e4b" / "sentiment_analysis.py",
    # ROOT / "rts" / "gemma4_e4b" / "sentiment_group_stats.py",
    # ROOT / "rts" / "gemma4_e4b" / "rules_recommendation.py",
    ROOT / "rts" / "gemma4_e4b" / "sentiment_to_predict.py",

    ROOT / "rts" / "combine" / "sentiment_combine.py",
    ROOT / "rts" / "combine" / "sentiment_to_predict.py",

    ROOT / "trade" / "trade_rts_ebs.py",

    # ==================== SI ====================
    ROOT / "si" / "shared" / "download_minutes_to_db.py",
    ROOT / "si" / "shared" / "convert_minutes_to_days.py",
    # ROOT / "si" / "shared" / "create_markdown_files.py",

    ROOT / "si" / "gpt-oss_20b" / "sentiment_analysis.py",
    # ROOT / "si" / "gpt-oss_20b" / "sentiment_group_stats.py",
    # ROOT / "si" / "gpt-oss_20b" / "rules_recommendation.py",
    ROOT / "si" / "gpt-oss_20b" / "sentiment_to_predict.py",

    ROOT / "si" / "gemma4_e4b" / "sentiment_analysis.py",
    # ROOT / "si" / "gemma4_e4b" / "sentiment_group_stats.py",
    # ROOT / "si" / "gemma4_e4b" / "rules_recommendation.py",
    ROOT / "si" / "gemma4_e4b" / "sentiment_to_predict.py",

    ROOT / "si" / "combine" / "sentiment_combine.py",
    ROOT / "si" / "combine" / "sentiment_to_predict.py",

    ROOT / "trade" / "trade_si_ebs.py",

    # ==================== NG ====================
    ROOT / "ng" / "shared" / "download_minutes_to_db.py",
    ROOT / "ng" / "shared" / "convert_minutes_to_days.py",
    # ROOT / "ng" / "shared" / "create_markdown_files.py",

    ROOT / "ng" / "gemma3_12b" / "sentiment_analysis.py",
    # ROOT / "ng" / "gemma3_12b" / "sentiment_group_stats.py",
    # ROOT / "ng" / "gemma3_12b" / "rules_recommendation.py",
    ROOT / "ng" / "gemma3_12b" / "sentiment_to_predict.py",

    ROOT / "ng" / "gemma4_e2b" / "sentiment_analysis.py",
    # ROOT / "ng" / "gemma4_e2b" / "sentiment_group_stats.py",
    # ROOT / "ng" / "gemma4_e2b" / "rules_recommendation.py",
    ROOT / "ng" / "gemma4_e2b" / "sentiment_to_predict.py",

    ROOT / "ng" / "gemma4_e4b" / "sentiment_analysis.py",
    # ROOT / "ng" / "gemma4_e4b" / "sentiment_group_stats.py",
    # ROOT / "ng" / "gemma4_e4b" / "rules_recommendation.py",
    ROOT / "ng" / "gemma4_e4b" / "sentiment_to_predict.py",

    ROOT / "ng" / "qwen2.5_14b" / "sentiment_analysis.py",
    # ROOT / "ng" / "qwen2.5_14b" / "sentiment_group_stats.py",
    # ROOT / "ng" / "qwen2.5_14b" / "rules_recommendation.py",
    ROOT / "ng" / "qwen2.5_14b" / "sentiment_to_predict.py",

    ROOT / "ng" / "qwen2.5_7b" / "sentiment_analysis.py",
    # ROOT / "ng" / "qwen2.5_7b" / "sentiment_group_stats.py",
    # ROOT / "ng" / "qwen2.5_7b" / "rules_recommendation.py",
    ROOT / "ng" / "qwen2.5_7b" / "sentiment_to_predict.py",

    ROOT / "ng" / "qwen3_14b" / "sentiment_analysis.py",
    # ROOT / "ng" / "qwen3_14b" / "sentiment_group_stats.py",
    # ROOT / "ng" / "qwen3_14b" / "rules_recommendation.py",
    ROOT / "ng" / "qwen3_14b" / "sentiment_to_predict.py",

    ROOT / "ng" / "gpt-oss_20b" / "sentiment_analysis.py",
    # ROOT / "ng" / "gpt-oss_20b" / "sentiment_group_stats.py",
    # ROOT / "ng" / "gpt-oss_20b" / "rules_recommendation.py",
    ROOT / "ng" / "gpt-oss_20b" / "sentiment_to_predict.py",

    ROOT / "ng" / "combine" / "sentiment_combine.py",
    ROOT / "ng" / "combine" / "sentiment_to_predict.py",

    # ==================== SPYF ====================
    ROOT / "spyf" / "shared" / "download_minutes_to_db.py",
    ROOT / "spyf" / "shared" / "convert_minutes_to_days.py",
    # ROOT / "spyf" / "shared" / "create_markdown_files.py",

    ROOT / "spyf" / "gemma3_12b" / "sentiment_analysis.py",
    # ROOT / "spyf" / "gemma3_12b" / "sentiment_group_stats.py",
    # ROOT / "spyf" / "gemma3_12b" / "rules_recommendation.py",
    ROOT / "spyf" / "gemma3_12b" / "sentiment_to_predict.py",

    ROOT / "spyf" / "gemma4_e2b" / "sentiment_analysis.py",
    # ROOT / "spyf" / "gemma4_e2b" / "sentiment_group_stats.py",
    # ROOT / "spyf" / "gemma4_e2b" / "rules_recommendation.py",
    ROOT / "spyf" / "gemma4_e2b" / "sentiment_to_predict.py",

    ROOT / "spyf" / "gemma4_e4b" / "sentiment_analysis.py",
    # ROOT / "spyf" / "gemma4_e4b" / "sentiment_group_stats.py",
    # ROOT / "spyf" / "gemma4_e4b" / "rules_recommendation.py",
    ROOT / "spyf" / "gemma4_e4b" / "sentiment_to_predict.py",

    ROOT / "spyf" / "qwen2.5_14b" / "sentiment_analysis.py",
    # ROOT / "spyf" / "qwen2.5_14b" / "sentiment_group_stats.py",
    # ROOT / "spyf" / "qwen2.5_14b" / "rules_recommendation.py",
    ROOT / "spyf" / "qwen2.5_14b" / "sentiment_to_predict.py",

    ROOT / "spyf" / "qwen2.5_7b" / "sentiment_analysis.py",
    # ROOT / "spyf" / "qwen2.5_7b" / "sentiment_group_stats.py",
    # ROOT / "spyf" / "qwen2.5_7b" / "rules_recommendation.py",
    ROOT / "spyf" / "qwen2.5_7b" / "sentiment_to_predict.py",

    ROOT / "spyf" / "qwen3_14b" / "sentiment_analysis.py",
    # ROOT / "spyf" / "qwen3_14b" / "sentiment_group_stats.py",
    # ROOT / "spyf" / "qwen3_14b" / "rules_recommendation.py",
    ROOT / "spyf" / "qwen3_14b" / "sentiment_to_predict.py",

    ROOT / "spyf" / "gpt-oss_20b" / "sentiment_analysis.py",
    # ROOT / "spyf" / "gpt-oss_20b" / "sentiment_group_stats.py",
    # ROOT / "spyf" / "gpt-oss_20b" / "rules_recommendation.py",
    ROOT / "spyf" / "gpt-oss_20b" / "sentiment_to_predict.py",

    ROOT / "spyf" / "combine" / "sentiment_combine.py",
    ROOT / "spyf" / "combine" / "sentiment_to_predict.py",

    # Торговые EBS-шаги MIX/RTS включены выше сразу после соответствующих combine-прогнозов.
]

SOFT_STEPS: list[Path] = [
    # ==================== MIX ====================
    ROOT / "mix" / "gemma4_e4b" / "sentiment_analysis.py",
    # ROOT / "mix" / "gemma4_e4b" / "sentiment_group_stats.py",
    # ROOT / "mix" / "gemma4_e4b" / "rules_recommendation.py",
    ROOT / "mix" / "gemma4_e4b" / "sentiment_to_predict.py",

    ROOT / "mix" / "qwen2.5_7b" / "sentiment_analysis.py",
    # ROOT / "mix" / "qwen2.5_7b" / "sentiment_group_stats.py",
    # ROOT / "mix" / "qwen2.5_7b" / "rules_recommendation.py",
    ROOT / "mix" / "qwen2.5_7b" / "sentiment_to_predict.py",

    ROOT / "mix" / "qwen3_14b" / "sentiment_analysis.py",
    # ROOT / "mix" / "qwen3_14b" / "sentiment_group_stats.py",
    # ROOT / "mix" / "qwen3_14b" / "rules_recommendation.py",
    ROOT / "mix" / "qwen3_14b" / "sentiment_to_predict.py",

    ROOT / "mix" / "qwen2.5_14b" / "sentiment_analysis.py",
    # ROOT / "mix" / "qwen2.5_14b" / "sentiment_group_stats.py",
    # ROOT / "mix" / "qwen2.5_14b" / "rules_recommendation.py",
    ROOT / "mix" / "qwen2.5_14b" / "sentiment_to_predict.py",

    ROOT / "mix" / "gpt-oss_20b" / "sentiment_analysis.py",
    # ROOT / "mix" / "gpt-oss_20b" / "sentiment_group_stats.py",
    # ROOT / "mix" / "gpt-oss_20b" / "rules_recommendation.py",
    ROOT / "mix" / "gpt-oss_20b" / "sentiment_to_predict.py",

    ROOT / "mix" / "gemma3_12b" / "sentiment_backtest.py",
    ROOT / "mix" / "gemma4_e2b" / "sentiment_backtest.py",
    ROOT / "mix" / "gemma4_e4b" / "sentiment_backtest.py",
    ROOT / "mix" / "qwen2.5_14b" / "sentiment_backtest.py",
    ROOT / "mix" / "qwen2.5_7b" / "sentiment_backtest.py",
    ROOT / "mix" / "qwen3_14b" / "sentiment_backtest.py",
    ROOT / "mix" / "gpt-oss_20b" / "sentiment_backtest.py",

    # ==================== RTS ====================
    ROOT / "rts" / "gemma3_12b" / "sentiment_analysis.py",
    # ROOT / "rts" / "gemma3_12b" / "sentiment_group_stats.py",
    # ROOT / "rts" / "gemma3_12b" / "rules_recommendation.py",
    ROOT / "rts" / "gemma3_12b" / "sentiment_to_predict.py",

    ROOT / "rts" / "gpt-oss_20b" / "sentiment_analysis.py",
    # ROOT / "rts" / "gpt-oss_20b" / "sentiment_group_stats.py",
    # ROOT / "rts" / "gpt-oss_20b" / "rules_recommendation.py",
    ROOT / "rts" / "gpt-oss_20b" / "sentiment_to_predict.py",

    ROOT / "rts" / "qwen3_14b" / "sentiment_analysis.py",
    # ROOT / "rts" / "qwen3_14b" / "sentiment_group_stats.py",
    # ROOT / "rts" / "qwen3_14b" / "rules_recommendation.py",
    ROOT / "rts" / "qwen3_14b" / "sentiment_to_predict.py",

    ROOT / "rts" / "qwen2.5_14b" / "sentiment_analysis.py",
    # ROOT / "rts" / "qwen2.5_14b" / "sentiment_group_stats.py",
    # ROOT / "rts" / "qwen2.5_14b" / "rules_recommendation.py",
    ROOT / "rts" / "qwen2.5_14b" / "sentiment_to_predict.py",

    ROOT / "rts" / "qwen2.5_7b" / "sentiment_analysis.py",
    # ROOT / "rts" / "qwen2.5_7b" / "sentiment_group_stats.py",
    # ROOT / "rts" / "qwen2.5_7b" / "rules_recommendation.py",
    ROOT / "rts" / "qwen2.5_7b" / "sentiment_to_predict.py",

    ROOT / "rts" / "gemma3_12b" / "sentiment_backtest.py",
    ROOT / "rts" / "gemma4_e2b" / "sentiment_backtest.py",
    ROOT / "rts" / "gemma4_e4b" / "sentiment_backtest.py",
    ROOT / "rts" / "qwen2.5_14b" / "sentiment_backtest.py",
    ROOT / "rts" / "qwen2.5_7b" / "sentiment_backtest.py",
    ROOT / "rts" / "qwen3_14b" / "sentiment_backtest.py",
    ROOT / "rts" / "gpt-oss_20b" / "sentiment_backtest.py",

    # ==================== NG ====================
    ROOT / "ng" / "gemma3_12b" / "sentiment_backtest.py",
    ROOT / "ng" / "gemma4_e2b" / "sentiment_backtest.py",
    ROOT / "ng" / "gemma4_e4b" / "sentiment_backtest.py",
    ROOT / "ng" / "qwen2.5_14b" / "sentiment_backtest.py",
    ROOT / "ng" / "qwen2.5_7b" / "sentiment_backtest.py",
    ROOT / "ng" / "qwen3_14b" / "sentiment_backtest.py",
    ROOT / "ng" / "gpt-oss_20b" / "sentiment_backtest.py",

    # ==================== SI ====================
    ROOT / "si" / "gemma4_e2b" / "sentiment_analysis.py",
    # ROOT / "si" / "gemma4_e2b" / "sentiment_group_stats.py",
    # ROOT / "si" / "gemma4_e2b" / "rules_recommendation.py",
    ROOT / "si" / "gemma4_e2b" / "sentiment_to_predict.py",

    ROOT / "si" / "qwen2.5_14b" / "sentiment_analysis.py",
    # ROOT / "si" / "qwen2.5_14b" / "sentiment_group_stats.py",
    # ROOT / "si" / "qwen2.5_14b" / "rules_recommendation.py",
    ROOT / "si" / "qwen2.5_14b" / "sentiment_to_predict.py",

    ROOT / "si" / "gemma3_12b" / "sentiment_analysis.py",
    # ROOT / "si" / "gemma3_12b" / "sentiment_group_stats.py",
    # ROOT / "si" / "gemma3_12b" / "rules_recommendation.py",
    ROOT / "si" / "gemma3_12b" / "sentiment_to_predict.py",

    ROOT / "si" / "qwen2.5_7b" / "sentiment_analysis.py",
    # ROOT / "si" / "qwen2.5_7b" / "sentiment_group_stats.py",
    # ROOT / "si" / "qwen2.5_7b" / "rules_recommendation.py",
    ROOT / "si" / "qwen2.5_7b" / "sentiment_to_predict.py",

    ROOT / "si" / "qwen3_14b" / "sentiment_analysis.py",
    # ROOT / "si" / "qwen3_14b" / "sentiment_group_stats.py",
    # ROOT / "si" / "qwen3_14b" / "rules_recommendation.py",
    ROOT / "si" / "qwen3_14b" / "sentiment_to_predict.py",

    ROOT / "si" / "gemma3_12b" / "sentiment_backtest.py",
    ROOT / "si" / "gemma4_e2b" / "sentiment_backtest.py",
    ROOT / "si" / "gemma4_e4b" / "sentiment_backtest.py",
    ROOT / "si" / "qwen2.5_14b" / "sentiment_backtest.py",
    ROOT / "si" / "qwen2.5_7b" / "sentiment_backtest.py",
    ROOT / "si" / "qwen3_14b" / "sentiment_backtest.py",
    ROOT / "si" / "gpt-oss_20b" / "sentiment_backtest.py",

    # ==================== SPYF ====================
    ROOT / "spyf" / "gemma3_12b" / "sentiment_backtest.py",
    ROOT / "spyf" / "gemma4_e2b" / "sentiment_backtest.py",
    ROOT / "spyf" / "gemma4_e4b" / "sentiment_backtest.py",
    ROOT / "spyf" / "qwen2.5_14b" / "sentiment_backtest.py",
    ROOT / "spyf" / "qwen2.5_7b" / "sentiment_backtest.py",
    ROOT / "spyf" / "qwen3_14b" / "sentiment_backtest.py",
    ROOT / "spyf" / "gpt-oss_20b" / "sentiment_backtest.py",
]


def run(script: Path, hard: bool) -> int:
    """Запускает один дочерний Python-скрипт и обрабатывает код возврата."""
    if not script.exists():
        msg = f"СКРИПТ НЕ НАЙДЕН: {script}"
        logger.error(msg)
        if hard:
            sys.exit(2)
        logger.warning(msg)
        return 2

    logger.info(f"> {'HARD' if hard else 'soft'}: {script.relative_to(ROOT)}")
    start = datetime.now()
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            check=False,
        )
        rc = proc.returncode
    except Exception as exc:
        logger.error(f"Исключение при запуске {script.name}: {exc}")
        if hard:
            sys.exit(3)
        return 3

    elapsed = (datetime.now() - start).total_seconds()
    if rc == 0:
        logger.info(f"OK: {script.name} ({elapsed:.1f} сек)")
    else:
        if hard:
            logger.error(
                f"FAIL: {script.name} код={rc} ({elapsed:.1f} сек). Останов пайплайна."
            )
            sys.exit(rc)
        logger.warning(
            f"WARN: {script.name} код={rc} ({elapsed:.1f} сек). Продолжаем (soft-fail)."
        )
    return rc


def main() -> int:
    """Выполняет ручной pipeline: HARD_STEPS, затем SOFT_STEPS."""
    logger.info(f"=== pj19 run_all.py начат: {timestamp} ===")
    logger.info(f"Python: {sys.executable}")
    logger.info(f"ROOT: {ROOT}")
    logger.info(f"HARD_STEPS: {len(HARD_STEPS)}")
    logger.info(f"SOFT_STEPS: {len(SOFT_STEPS)}")

    for step in HARD_STEPS:
        run(step, hard=True)

    logger.info("--- HARD_STEPS завершены, переходим к SOFT_STEPS ---")

    for step in SOFT_STEPS:
        run(step, hard=False)

    logger.info("=== pj19 run_all.py завершён успешно ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
