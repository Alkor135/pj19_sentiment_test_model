from datetime import date
from pathlib import Path

from walk_forward import run_walk_forward


def test_parse_csv_returns_default_for_empty_value() -> None:
    assert run_walk_forward.parse_csv(None, ("rts", "mix")) == ["rts", "mix"]
    assert run_walk_forward.parse_csv("", ("rts", "mix")) == ["rts", "mix"]
    assert run_walk_forward.parse_csv("rts, mix", ()) == ["rts", "mix"]


def test_merge_run_options_applies_cli_overrides(tmp_path: Path) -> None:
    settings = {
        "tickers": ["rts", "mix"],
        "models": [],
        "backtest_start_date": "2025-04-01",
        "backtest_end_date": None,
        "train_months": 6,
        "output_dir": "walk_forward/results",
        "save_daily_artifacts": False,
        "min_train_rows": 20,
        "keep_going": True,
    }

    options = run_walk_forward.merge_run_options(
        settings,
        tickers="si",
        models="gemma3_12b,qwen3_14b",
        start_date="2025-05-01",
        end_date="2025-05-31",
        train_months=3,
        output_dir=tmp_path,
        save_daily_artifacts=True,
        min_train_rows=5,
        keep_going=False,
    )

    assert options.tickers == ["si"]
    assert options.models == ["gemma3_12b", "qwen3_14b"]
    assert options.backtest_start_date == date(2025, 5, 1)
    assert options.backtest_end_date == date(2025, 5, 31)
    assert options.train_months == 3
    assert options.output_dir == tmp_path
    assert options.save_daily_artifacts is True
    assert options.min_train_rows == 5
    assert options.keep_going is False


def test_load_model_settings_merges_common_defaults_and_model_overrides() -> None:
    raw = {
        "common": {"ticker": "RTS", "ticker_lc": "rts", "quantity_test": 2},
        "model_defaults": {
            "sentiment_output_pkl": "{ticker_lc}/{model_dir}/sentiment_scores.pkl",
            "sentiment_model": "{model_dir}",
        },
        "models": {
            "gemma3_12b": {
                "sentiment_model": "gemma3:12b",
                "quantity_test": 3,
            }
        },
    }

    settings = run_walk_forward.build_model_settings(raw, "gemma3_12b")

    assert settings["ticker"] == "RTS"
    assert settings["quantity_test"] == 3
    assert settings["sentiment_model"] == "gemma3:12b"
    assert settings["sentiment_output_pkl"] == "rts/gemma3_12b/sentiment_scores.pkl"


def test_settings_file_is_valid_for_experiments() -> None:
    settings = run_walk_forward.load_yaml(run_walk_forward.SETTINGS_PATH)

    required = {
        "tickers",
        "models",
        "backtest_start_date",
        "backtest_end_date",
        "train_months",
        "output_dir",
        "save_daily_artifacts",
        "min_train_rows",
        "keep_going",
    }
    assert required <= set(settings)

    options = run_walk_forward.merge_run_options(
        settings,
        tickers=None,
        models=None,
        start_date=None,
        end_date=None,
        train_months=None,
        output_dir=None,
        save_daily_artifacts=None,
        min_train_rows=None,
        keep_going=None,
    )

    assert options.tickers
    assert options.backtest_start_date == run_walk_forward.parse_date(settings["backtest_start_date"])
    assert options.train_months >= 1
    assert options.min_train_rows >= 1
    assert isinstance(options.save_daily_artifacts, bool)
    assert isinstance(options.keep_going, bool)
    assert options.output_dir.is_absolute()
