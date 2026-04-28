from pathlib import Path

import run_trade


def test_build_ticker_command_uses_configured_models_and_keep_going() -> None:
    runner = Path("rts/run_rts_trade.py")
    config = {
        "only": ["gemma3_12b", "qwen3_14b", "combine"],
        "keep_going": True,
    }

    command = run_trade.build_ticker_command(runner, config)

    assert command == [
        run_trade.sys.executable,
        str(runner),
        "--only",
        "gemma3_12b,qwen3_14b,combine",
        "--keep-going",
    ]


def test_select_ticker_runs_filters_requested_tickers() -> None:
    runs = {
        "mix": {"only": ["combine"], "keep_going": True},
        "rts": {"only": ["gemma3_12b"], "keep_going": True},
    }

    selected = run_trade.select_ticker_runs(runs, "rts")

    assert selected == {"rts": runs["rts"]}
