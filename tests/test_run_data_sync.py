import run_data_sync


def test_run_data_sync_keeps_manual_step_lists() -> None:
    assert run_data_sync.HARD_STEPS
    assert run_data_sync.SOFT_STEPS == []


def test_run_data_sync_runs_beget_and_all_ticker_minute_downloads() -> None:
    expected_steps = [
        run_data_sync.ROOT / "beget" / "sync_files.py",
        run_data_sync.ROOT / "mix" / "shared" / "download_minutes_to_db.py",
        run_data_sync.ROOT / "ng" / "shared" / "download_minutes_to_db.py",
        run_data_sync.ROOT / "rts" / "shared" / "download_minutes_to_db.py",
        run_data_sync.ROOT / "si" / "shared" / "download_minutes_to_db.py",
        run_data_sync.ROOT / "spyf" / "shared" / "download_minutes_to_db.py",
    ]

    assert run_data_sync.HARD_STEPS == expected_steps


def test_run_data_sync_does_not_run_trade_or_model_pipelines() -> None:
    all_steps = run_data_sync.HARD_STEPS + run_data_sync.SOFT_STEPS

    assert all("trade" not in step.parts for step in all_steps)
    assert all(step.name != "sentiment_analysis.py" for step in all_steps)
    assert all(step.name != "sentiment_to_predict.py" for step in all_steps)
