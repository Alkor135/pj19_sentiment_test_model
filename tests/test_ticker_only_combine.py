import importlib
from pathlib import Path

import pytest
import typer


ORCHESTRATOR_MODULES = [
    "rts.run_rts",
    "rts.run_rts_report",
    "rts.run_rts_trade",
    "mix.run_mix",
    "mix.run_mix_report",
    "mix.run_mix_trade",
    "ng.run_ng",
    "ng.run_ng_report",
    "ng.run_ng_trade",
    "si.run_si",
    "si.run_si_report",
    "si.run_si_trade",
    "spyf.run_spyf",
    "spyf.run_spyf_report",
    "spyf.run_spyf_trade",
]


def combine_plan_kwargs(module: object, ticker: str) -> dict[str, Path]:
    if hasattr(module, "COMBINE_RUNNER"):
        return {"combine_runner": Path(ticker) / "combine" / module.COMBINE_RUNNER}
    return {"combine_dir": Path(ticker) / "combine"}


@pytest.mark.parametrize("module_name", ORCHESTRATOR_MODULES)
def test_only_can_include_models_and_combine(module_name: str) -> None:
    module = importlib.import_module(module_name)
    ticker = module_name.split(".")[0]
    runner_name = module.MODEL_RUNNER
    runners = [
        Path(ticker) / "gemma3_12b" / runner_name,
        Path(ticker) / "qwen3_14b" / runner_name,
    ]

    selected, run_combine = module.build_run_plan(
        all_runners=runners,
        only="gemma3_12b,combine",
        **combine_plan_kwargs(module, ticker),
    )

    assert selected == [runners[0]]
    assert run_combine is True


@pytest.mark.parametrize("module_name", ORCHESTRATOR_MODULES)
def test_only_rejects_unknown_but_accepts_combine(module_name: str) -> None:
    module = importlib.import_module(module_name)
    ticker = module_name.split(".")[0]
    runners = [Path(ticker) / "gemma3_12b" / module.MODEL_RUNNER]

    with pytest.raises(typer.BadParameter) as exc:
        module.build_run_plan(
            all_runners=runners,
            only="gemma3_12b,combine,missing_model",
            **combine_plan_kwargs(module, ticker),
        )

    message = str(exc.value)
    assert "['missing_model']" in message
    assert "combine" in message
