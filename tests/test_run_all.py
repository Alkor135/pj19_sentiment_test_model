import run_all


def test_run_all_keeps_manual_hard_and_soft_step_lists() -> None:
    assert run_all.HARD_STEPS
    assert run_all.SOFT_STEPS
    assert run_all.ROOT / "beget" / "sync_files.py" in run_all.HARD_STEPS
    assert run_all.ROOT / "rts" / "shared" / "download_minutes_to_db.py" in run_all.HARD_STEPS
    assert run_all.ROOT / "rts" / "qwen2.5_7b" / "sentiment_analysis.py" in run_all.HARD_STEPS
    assert run_all.ROOT / "trade" / "trade_mix_ebs.py" in run_all.HARD_STEPS
    assert run_all.ROOT / "trade" / "trade_rts_ebs.py" in run_all.HARD_STEPS
    assert run_all.ROOT / "rts" / "gemma3_12b" / "sentiment_backtest.py" in run_all.SOFT_STEPS


def test_run_all_does_not_delegate_to_root_orchestrators_by_default() -> None:
    forbidden = {
        run_all.ROOT / "run.py",
        run_all.ROOT / "run_trade.py",
        run_all.ROOT / "run_report.py",
    }

    assert forbidden.isdisjoint(run_all.HARD_STEPS)
    assert forbidden.isdisjoint(run_all.SOFT_STEPS)


def test_legacy_root_orchestrators_are_removed() -> None:
    assert not (run_all.ROOT / "run.py").exists()
    assert not (run_all.ROOT / "run_trade.py").exists()


def test_run_all_groups_model_steps_by_ticker() -> None:
    mix_analysis = run_all.ROOT / "mix" / "gemma3_12b" / "sentiment_analysis.py"
    mix_predict = run_all.ROOT / "mix" / "gemma4_e4b" / "sentiment_to_predict.py"
    mix_trade = run_all.ROOT / "trade" / "trade_mix_ebs.py"
    ng_analysis = run_all.ROOT / "ng" / "gemma3_12b" / "sentiment_analysis.py"

    assert run_all.HARD_STEPS.index(mix_analysis) < run_all.HARD_STEPS.index(mix_predict)
    assert run_all.HARD_STEPS.index(mix_predict) < run_all.HARD_STEPS.index(mix_trade)
    assert run_all.HARD_STEPS.index(mix_trade) < run_all.HARD_STEPS.index(ng_analysis)

    mix_backtest = run_all.ROOT / "mix" / "qwen3_14b" / "sentiment_backtest.py"
    ng_backtest = run_all.ROOT / "ng" / "gemma3_12b" / "sentiment_backtest.py"

    assert run_all.SOFT_STEPS.index(mix_backtest) < run_all.SOFT_STEPS.index(ng_backtest)
