from pathlib import Path

import pytest

from del_pkl import delete_files, find_pkl_files, resolve_target_roots


def test_find_pkl_files_recursively_ignores_non_pkl(tmp_path):
    root_file = tmp_path / "root.pkl"
    nested_file = tmp_path / "rts" / "model" / "sentiment_scores.pkl"
    text_file = tmp_path / "rts" / "notes.txt"
    nested_file.parent.mkdir(parents=True)
    root_file.write_text("root")
    nested_file.write_text("nested")
    text_file.write_text("ignore")

    assert find_pkl_files(tmp_path) == [root_file, nested_file]


def test_delete_files_removes_only_given_paths(tmp_path):
    first = tmp_path / "first.pkl"
    second = tmp_path / "nested" / "second.pkl"
    keep = tmp_path / "nested" / "keep.txt"
    second.parent.mkdir()
    first.write_text("first")
    second.write_text("second")
    keep.write_text("keep")

    deleted = delete_files([first, second])

    assert deleted == [first, second]
    assert not first.exists()
    assert not second.exists()
    assert keep.exists()


def test_resolve_target_roots_returns_requested_project_folders(tmp_path):
    rts = tmp_path / "rts"
    mix = tmp_path / "mix"
    rts.mkdir()
    mix.mkdir()

    assert resolve_target_roots(tmp_path, ["rts"]) == [rts]


def test_resolve_target_roots_rejects_unknown_folder(tmp_path):
    with pytest.raises(ValueError, match="Папка не найдена"):
        resolve_target_roots(tmp_path, ["unknown"])
