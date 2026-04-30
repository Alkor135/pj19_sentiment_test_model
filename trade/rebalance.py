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
