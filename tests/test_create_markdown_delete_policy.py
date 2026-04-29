import importlib
from datetime import datetime

import pytest


MODULES = [
    "rts.shared.create_markdown_files",
    "mix.shared.create_markdown_files",
    "ng.shared.create_markdown_files",
    "si.shared.create_markdown_files",
    "spyf.shared.create_markdown_files",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_markdown_created_before_today_21_00_can_be_deleted(module_name: str) -> None:
    create_markdown_files = importlib.import_module(module_name)
    now = datetime(2026, 4, 29, 21, 5, 0)
    mtime = datetime(2026, 4, 29, 20, 59, 59)

    assert create_markdown_files.should_delete_latest_markdown_file(mtime, now)


@pytest.mark.parametrize("module_name", MODULES)
def test_markdown_created_after_today_21_00_is_kept(module_name: str) -> None:
    create_markdown_files = importlib.import_module(module_name)
    now = datetime(2026, 4, 29, 21, 5, 0)
    mtime = datetime(2026, 4, 29, 21, 0, 1)

    assert not create_markdown_files.should_delete_latest_markdown_file(mtime, now)


@pytest.mark.parametrize("module_name", MODULES)
def test_markdown_created_exactly_at_today_21_00_is_kept(module_name: str) -> None:
    create_markdown_files = importlib.import_module(module_name)
    now = datetime(2026, 4, 29, 21, 5, 0)
    mtime = datetime(2026, 4, 29, 21, 0, 0)

    assert not create_markdown_files.should_delete_latest_markdown_file(mtime, now)
