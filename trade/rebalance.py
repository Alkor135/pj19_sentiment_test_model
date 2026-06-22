"""Расчёт заявок для перехода от текущей позиции к целевой."""


def build_rebalance_orders(current_position: int, target_position: int) -> list[tuple[str, int, str]]:
    """Возвращает список QUIK-действий (Покупка/Продажа), объёмов и причин.

    Функция не знает про тикер, счёт и файлы транзакций: она только раскладывает
    переход между знаковыми позициями на один или два рыночных ордера. При
    развороте позиции сначала закрывает старое направление, затем открывает новое.
    """
    delta = target_position - current_position
    if delta == 0:
        return []

    if delta > 0:
        if current_position < 0 and target_position > 0:
            return [
                ("Покупка", abs(current_position), "Закрытие шорта"),
                ("Покупка", target_position, "Открытие лонга"),
            ]
        if current_position < 0:
            reason = "Закрытие шорта" if target_position == 0 else "Сокращение шорта"
        else:
            reason = "Открытие лонга" if current_position == 0 else "Увеличение лонга"
        return [("Покупка", delta, reason)]

    quantity = abs(delta)
    if current_position > 0 and target_position < 0:
        return [
            ("Продажа", current_position, "Закрытие лонга"),
            ("Продажа", abs(target_position), "Открытие шорта"),
        ]
    if current_position > 0:
        reason = "Закрытие лонга" if target_position == 0 else "Сокращение лонга"
    else:
        reason = "Открытие шорта" if current_position == 0 else "Увеличение шорта"
    return [("Продажа", quantity, reason)]


def build_rollover_orders(
    current_position: int,
    target_position: int,
    old_position: int,
) -> list[tuple[str, str, int, str]]:
    """Возвращает заявки нового и старого контрактов при ролловере.

    Сначала сохраняет обычный порядок ребалансировки нового контракта, включая
    закрытие и открытие при перевороте. Затем, независимо от дельты нового
    контракта, добавляет закрытие ненулевой позиции старого контракта.
    """
    orders = [
        ("ticker_open", action, quantity, reason)
        for action, quantity, reason in build_rebalance_orders(
            current_position,
            target_position,
        )
    ]

    if old_position != 0:
        action = "Продажа" if old_position > 0 else "Покупка"
        reason = (
            "Ролловер: закрытие лонга"
            if old_position > 0
            else "Ролловер: закрытие шорта"
        )
        orders.append(("ticker_close", action, abs(old_position), reason))

    return orders
