"""
Корневой оркестратор pj19 для дневной синхронизации данных.

Это намеренно простой файл-расписание: порядок запуска меняется переносом строк
в HARD_STEPS и SOFT_STEPS. HARD_STEPS останавливают весь пайплайн при ошибке;
SOFT_STEPS логируют ошибку и продолжают выполнение.

По умолчанию скрипт запускает:
1. beget/sync_files.py
2. shared/download_minutes_to_db.py для всех тикеров: mix, ng, rts, si, spyf

Запуск:
.venv/Scripts/python.exe run_data_sync.py

Пример расписания: 12:00, 15:00, 18:00, 22:00. В планировщике Windows лучше
запретить параллельные экземпляры этой задачи, чтобы следующий запуск не
наложился на предыдущий.
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
log_file = LOG_DIR / f"run_data_sync_{timestamp}.txt"


logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=build_handlers(log_file),
    force=True,
)
logger = logging.getLogger("run_data_sync")

for old in sorted(LOG_DIR.glob("run_data_sync_*.txt"))[:-20]:
    try:
        old.unlink()
    except OSError:
        pass


HARD_STEPS: list[Path] = [
    # Общий этап: синхронизация RSS-БД и логов с удалённого сервера.
    ROOT / "beget" / "sync_files.py",

    # ==================== MIX ====================
    ROOT / "mix" / "shared" / "download_minutes_to_db.py",

    # ==================== NG ====================
    ROOT / "ng" / "shared" / "download_minutes_to_db.py",

    # ==================== RTS ====================
    ROOT / "rts" / "shared" / "download_minutes_to_db.py",

    # ==================== SI ====================
    ROOT / "si" / "shared" / "download_minutes_to_db.py",

    # ==================== SPYF ====================
    ROOT / "spyf" / "shared" / "download_minutes_to_db.py",
]

SOFT_STEPS: list[Path] = [
    # Сюда можно перенести необязательные шаги, если один тикер не должен
    # останавливать обновление остальных.
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
    """Выполняет дневную синхронизацию: HARD_STEPS, затем SOFT_STEPS."""
    logger.info(f"=== pj19 run_data_sync.py начат: {timestamp} ===")
    logger.info(f"Python: {sys.executable}")
    logger.info(f"ROOT: {ROOT}")
    logger.info(f"HARD_STEPS: {len(HARD_STEPS)}")
    logger.info(f"SOFT_STEPS: {len(SOFT_STEPS)}")

    for step in HARD_STEPS:
        run(step, hard=True)

    if SOFT_STEPS:
        logger.info("--- HARD_STEPS завершены, переходим к SOFT_STEPS ---")

    for step in SOFT_STEPS:
        run(step, hard=False)

    logger.info("=== pj19 run_data_sync.py завершён успешно ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
