"""Оркестратор WF-отчётов всех моделей тикера SI.

Запускает модельные ``run_report_fw.py``, собирает созданные
``plots/sentiment_backtest_wf.html`` и открывает их в одном новом окне Chrome.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from walk_forward.live_predict import run_ticker_report_fw_app

app = run_ticker_report_fw_app(__file__)


if __name__ == "__main__":
    app()
