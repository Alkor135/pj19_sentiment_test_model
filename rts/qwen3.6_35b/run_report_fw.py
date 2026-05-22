"""Строит WF-отчёт одной модели и открывает созданный HTML в Chrome.

Расчётная логика находится в ``walk_forward.live_predict``; этот файл нужен
как тонкая CLI-обёртка для запуска из папки ``<ticker>/<model>``.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from walk_forward.live_predict import run_report_fw_app

app = run_report_fw_app(__file__)


if __name__ == "__main__":
    app()
