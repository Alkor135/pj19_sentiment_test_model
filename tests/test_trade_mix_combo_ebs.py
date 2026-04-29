from pathlib import Path

import pytest
import yaml


SCRIPT_CASES = [
    ("mix", Path("trade/trade_mix_combo_ebs.py")),
    ("rts", Path("trade/trade_rts_combo_ebs.py")),
]
SETTINGS_PATH = Path("trade/settings.yaml")


@pytest.mark.parametrize(("ticker_lc", "script_path"), SCRIPT_CASES)
def test_combo_ebs_uses_account_prediction_dir_with_today_file(
    ticker_lc: str,
    script_path: Path,
) -> None:
    script = script_path.read_text(encoding="utf-8")

    assert f"ticker_lc = '{ticker_lc}'" in script
    assert "predict_dir = Path(account[ticker_lc]['predict_dir'])" in script
    assert 'current_filename = today.strftime("%Y-%m-%d") + ".txt"' in script
    assert "current_filepath = predict_dir / current_filename" in script
    assert "cfg['predict_path']" not in script


@pytest.mark.parametrize(("ticker_lc", "script_path"), SCRIPT_CASES)
def test_combo_ebs_uses_full_tri_filepath_from_settings(
    ticker_lc: str,
    script_path: Path,
) -> None:
    script = script_path.read_text(encoding="utf-8")

    assert "trade_filepath = Path(account['trade_filepath'])" in script
    assert "trade_path = trade_filepath.parent" in script
    assert 'trade_filepath = trade_path / "input.tri"' not in script


def test_trade_settings_do_not_keep_obsolete_trade_path_key() -> None:
    settings = yaml.safe_load(SETTINGS_PATH.read_text(encoding="utf-8"))

    for account in settings["accounts"].values():
        assert "trade_path" not in account


def test_ebs_rts_has_prediction_dir() -> None:
    settings = yaml.safe_load(SETTINGS_PATH.read_text(encoding="utf-8"))

    assert settings["accounts"]["ebs"]["rts"]["predict_dir"]


def test_trade_settings_define_done_marker_reset_time() -> None:
    settings = yaml.safe_load(SETTINGS_PATH.read_text(encoding="utf-8"))

    assert settings["done_marker_reset_before"] == "21:00:00"


@pytest.mark.parametrize(("ticker_lc", "script_path"), SCRIPT_CASES)
def test_combo_ebs_deletes_test_done_markers_before_configured_time(
    ticker_lc: str,
    script_path: Path,
) -> None:
    script = script_path.read_text(encoding="utf-8")

    assert "done_marker_reset_before = trade_cfg['done_marker_reset_before']" in script
    assert "should_delete_existing_done_marker(" in script
    assert "done_marker.unlink()" in script
    assert "if done_marker.exists():" in script
