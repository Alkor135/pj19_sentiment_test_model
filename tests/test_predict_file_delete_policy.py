import os
import importlib.util
from datetime import date, datetime
from pathlib import Path

import pytest


MODULE_PATHS = [
    path
    for ticker in ("rts", "mix", "ng", "si", "spyf")
    for path in Path(ticker).glob("*/sentiment_to_predict.py")
]


def load_module(path: Path):
    module_name = "sentiment_to_predict_" + "_".join(path.with_suffix("").parts).replace(".", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def set_mtime(path, dt: datetime) -> None:
    ts = dt.timestamp()
    os.utime(path, (ts, ts))


@pytest.mark.parametrize("module_path", MODULE_PATHS)
def test_today_predict_created_before_21_00_can_be_deleted(module_path: Path, tmp_path) -> None:
    sentiment_to_predict = load_module(module_path)
    out_file = tmp_path / "2026-04-29.txt"
    out_file.write_text("old", encoding="utf-8")
    set_mtime(out_file, datetime(2026, 4, 29, 20, 59, 59))

    assert sentiment_to_predict.should_delete_existing_predict_file(
        out_file,
        date(2026, 4, 29),
        "21:00:00",
    )


@pytest.mark.parametrize("module_path", MODULE_PATHS)
def test_today_predict_created_after_21_00_is_kept(module_path: Path, tmp_path) -> None:
    sentiment_to_predict = load_module(module_path)
    out_file = tmp_path / "2026-04-29.txt"
    out_file.write_text("fresh", encoding="utf-8")
    set_mtime(out_file, datetime(2026, 4, 29, 21, 0, 1))

    assert not sentiment_to_predict.should_delete_existing_predict_file(
        out_file,
        date(2026, 4, 29),
        "21:00:00",
    )


@pytest.mark.parametrize("module_path", MODULE_PATHS)
def test_predict_file_with_non_today_name_is_kept(module_path: Path, tmp_path) -> None:
    sentiment_to_predict = load_module(module_path)
    out_file = tmp_path / "2026-04-28.txt"
    out_file.write_text("previous day", encoding="utf-8")
    set_mtime(out_file, datetime(2026, 4, 29, 20, 59, 59))

    assert not sentiment_to_predict.should_delete_existing_predict_file(
        out_file,
        date(2026, 4, 29),
        "21:00:00",
    )
