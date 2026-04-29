from trade.rebalance import build_rebalance_orders


def test_reducing_short_buys_only_delta_to_target() -> None:
    assert build_rebalance_orders(-4, -2) == [
        ("Покупка", 2, "Сокращение шорта"),
    ]


def test_reducing_long_sells_only_delta_to_target() -> None:
    assert build_rebalance_orders(4, 2) == [
        ("Продажа", 2, "Сокращение лонга"),
    ]


def test_reversing_short_to_long_closes_then_opens() -> None:
    assert build_rebalance_orders(-4, 2) == [
        ("Покупка", 4, "Закрытие шорта"),
        ("Покупка", 2, "Открытие лонга"),
    ]


def test_reversing_long_to_short_closes_then_opens() -> None:
    assert build_rebalance_orders(4, -2) == [
        ("Продажа", 4, "Закрытие лонга"),
        ("Продажа", 2, "Открытие шорта"),
    ]
