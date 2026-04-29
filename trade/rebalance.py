def build_rebalance_orders(current_position: int, target_position: int) -> list[tuple[str, int, str]]:
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
