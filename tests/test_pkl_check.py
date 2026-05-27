import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TICKERS = ("rts", "mix", "ng", "si", "spyf")


def model_dirs():
    """Возвращает модельные папки, перечисленные в settings.yaml тикеров."""
    dirs = []
    for ticker in TICKERS:
        settings_path = PROJECT_ROOT / ticker / "settings.yaml"
        settings = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
        for model_name in settings.get("models", {}):
            dirs.append(PROJECT_ROOT / ticker / model_name)
    return dirs


def test_pkl_check_script_exists_in_every_model_dir():
    """Проверяет, что pkl_check.py есть в каждой модельной папке."""
    missing = [
        str(model_dir.relative_to(PROJECT_ROOT))
        for model_dir in model_dirs()
        if not (model_dir / "pkl_check.py").is_file()
    ]

    assert missing == []


def test_pkl_check_prints_columns_head_and_tail_for_selected_columns(tmp_path):
    """Проверяет вывод колонок, первых строк и последних строк PKL-файла."""
    source_script = PROJECT_ROOT / "rts" / "gpt-oss_20b" / "pkl_check.py"
    script_dir = tmp_path / "model"
    script_dir.mkdir()
    script_path = script_dir / "pkl_check.py"
    script_path.write_text(source_script.read_text(encoding="utf-8"), encoding="utf-8")

    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=6).strftime("%Y-%m-%d"),
            "ticker": ["RTS"] * 6,
            "model": ["test_model"] * 6,
            "prompt_tokens": [101, 102, 103, 104, 105, 106],
            "raw_response": ["1", "2", "3", "4", "5", "6"],
            "sentiment": [1, 2, 3, 4, 5, 6],
            "body": [10, 20, 30, 40, 50, 60],
            "next_body": [11, 21, 31, 41, 51, 61],
            "extra_col": [f"extra_{i}" for i in range(6)],
        }
    )
    df.to_pickle(script_dir / "sentiment_scores.pkl")

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=script_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Колонки df:" in result.stdout
    assert "extra_col" in result.stdout
    assert "Первые 5 строк по COLUMNS:" in result.stdout
    assert "Последние 5 строк по COLUMNS:" in result.stdout
    assert "2026-01-01" in result.stdout
    assert "2026-01-06" in result.stdout
