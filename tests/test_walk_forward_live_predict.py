from __future__ import annotations

from datetime import date
import pickle

import pandas as pd
import yaml

from walk_forward import live_predict


def _write_model_tree(tmp_path, rows: list[dict]) -> tuple:
    ticker_dir = tmp_path / "rts"
    model_dir = ticker_dir / "gemma3_12b"
    model_dir.mkdir(parents=True)
    pkl_path = model_dir / "sentiment_scores.pkl"
    with pkl_path.open("wb") as f:
        pickle.dump(rows, f)

    settings = {
        "common": {
            "ticker": "RTS",
            "ticker_lc": "rts",
            "quantity_test": 1,
            "time_start": "21:00:00",
            "rules_train_months": 1,
            "rules_min_train_rows": 2,
            "predict_path": str(model_dir / "predict"),
            "sentiment_output_pkl": str(pkl_path),
        },
        "model_defaults": {},
        "models": {"gemma3_12b": {"sentiment_model": "gemma3:12b"}},
    }
    (ticker_dir / "settings.yaml").write_text(
        yaml.safe_dump(settings, allow_unicode=True),
        encoding="utf-8",
    )
    return model_dir, model_dir / "rules_recommendation_wf.py"


def test_write_rules_wf_outputs_use_only_training_window_before_target_date(tmp_path) -> None:
    model_dir, script_path = _write_model_tree(
        tmp_path,
        [
            {"source_date": "2025-03-31", "sentiment": 1, "next_body": 10},
            {"source_date": "2025-04-01", "sentiment": -1, "next_body": 5},
            {"source_date": "2025-04-02", "sentiment": 1, "next_body": -1000},
        ],
    )

    result = live_predict.write_rules_wf_outputs(
        script_path,
        target_date=date(2025, 4, 2),
    )

    rules_path = model_dir / "rules_wf.yaml"
    group_stats_path = model_dir / "group_stats" / "sentiment_group_stats_wf.xlsx"
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))["rules"]
    sentiment_one = next(rule for rule in rules if rule["min"] == 1)
    grouped = pd.read_excel(group_stats_path)

    assert result.train_start == date(2025, 3, 2)
    assert result.train_end == date(2025, 4, 1)
    assert result.train_rows == 2
    assert sentiment_one["action"] == "follow"
    assert grouped.loc[grouped["sentiment"] == 1, "total_pnl"].iloc[0] == 10


def test_write_predict_wf_uses_rules_wf_yaml_and_keeps_predict_file_format(tmp_path) -> None:
    model_dir, script_path = _write_model_tree(
        tmp_path,
        [{"source_date": "2025-04-02", "sentiment": 1, "next_body": 0}],
    )
    (model_dir / "rules_wf.yaml").write_text(
        "rules:\n  - {min: 1, max: 1, action: invert}\n",
        encoding="utf-8",
    )

    out_file = live_predict.write_predict_wf(
        model_dir / "sentiment_to_predict_wf.py",
        target_date=date(2025, 4, 2),
    )

    content = out_file.read_text(encoding="utf-8")
    assert out_file == model_dir / "predict" / "2025-04-02.txt"
    assert "Дата: 2025-04-02" in content
    assert "Sentiment: 1.00" in content
    assert "Action: invert" in content
    assert "Status: ok" in content
    assert "Предсказанное направление: down" in content


def test_write_backtest_wf_outputs_model_backtest_xlsx(tmp_path) -> None:
    model_dir, script_path = _write_model_tree(
        tmp_path,
        [
            {"source_date": "2025-03-30", "sentiment": 1, "next_body": 5},
            {"source_date": "2025-03-31", "sentiment": -1, "next_body": 6},
            {"source_date": "2025-04-01", "sentiment": 1, "next_body": 7},
            {"source_date": "2025-04-02", "sentiment": -1, "next_body": 8},
        ],
    )

    output_xlsx = live_predict.write_backtest_wf_outputs(
        model_dir / "sentiment_backtest_wf.py",
        start_date=date(2025, 4, 1),
        end_date=date(2025, 4, 2),
    )

    result = pd.read_excel(output_xlsx)
    assert output_xlsx == model_dir / "backtest" / "sentiment_backtest_results_wf.xlsx"
    assert result["source_date"].dt.date.tolist() == [date(2025, 4, 1), date(2025, 4, 2)]
    assert {"train_start", "train_end", "train_rows"}.issubset(result.columns)
