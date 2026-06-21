"""Проверки подключения планирования ролловера к EBS-адаптерам."""

from pathlib import Path

import pytest


SCRIPT_PATHS = [
    Path("trade/trade_mix_ebs.py"),
    Path("trade/trade_rts_ebs.py"),
    Path("trade/trade_si_ebs.py"),
]


@pytest.mark.parametrize("script_path", SCRIPT_PATHS)
def test_ebs_adapter_plans_old_contract_close_independently_of_new_delta(
    script_path: Path,
) -> None:
    """Не завершает ролловер только потому, что новый контракт уже в цели."""
    script = script_path.read_text(encoding="utf-8")

    assert "from rebalance import build_rebalance_orders, build_rollover_orders" in script
    assert "orders = build_rollover_orders(" in script
    assert "if delta == 0:" not in script
