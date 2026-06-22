"""Проверки планирования заявок при ролловере фьючерсного контракта."""

from trade.rebalance import build_rollover_orders


def test_rollover_closes_old_long_when_new_position_is_already_target() -> None:
    """Закрывает старый лонг даже при нулевой дельте нового контракта."""
    assert build_rollover_orders(0, 0, 2) == [
        ("ticker_close", "Продажа", 2, "Ролловер: закрытие лонга"),
    ]


def test_rollover_keeps_new_contract_reversal_before_old_close() -> None:
    """Сохраняет закрытие и открытие переворота до закрытия старого контракта."""
    assert build_rollover_orders(-2, 3, 4) == [
        ("ticker_open", "Покупка", 2, "Закрытие шорта"),
        ("ticker_open", "Покупка", 3, "Открытие лонга"),
        ("ticker_close", "Продажа", 4, "Ролловер: закрытие лонга"),
    ]
