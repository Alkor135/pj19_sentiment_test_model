# Rollover Close Orders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Закрывать позицию старого контракта при ролловере, даже если позиция нового уже совпадает с целью.

**Architecture:** В `trade/rebalance.py` добавить чистую функцию, которая объединяет существующие заявки ребалансировки нового контракта и независимое закрытие старого. EBS-адаптеры передают в неё позиции и записывают заявки в возвращённом порядке: существующая ребалансировка нового, затем закрытие старого.

**Tech Stack:** Python 3, pytest, существующие EBS-адаптеры QUIK.

---

### Task 1: Закрепить планирование заявок тестами

**Files:**
- Modify: `tests/test_trade_rebalance.py`
- Test: `tests/test_trade_rebalance.py`

- [ ] **Step 1: Добавить падающие тесты для ролловера при нулевой дельте и переворота.**

```python
def test_build_rollover_orders_closes_old_long_when_new_position_is_already_target():
    assert build_rollover_orders(0, 0, 2) == [
        ("ticker_close", "Продажа", 2, "Ролловер: закрытие лонга"),
    ]


def test_build_rollover_orders_keeps_new_contract_reversal_before_old_close():
    assert build_rollover_orders(-2, 3, 4) == [
        ("ticker_open", "Покупка", 2, "Закрытие шорта"),
        ("ticker_open", "Покупка", 3, "Открытие лонга"),
        ("ticker_close", "Продажа", 4, "Ролловер: закрытие лонга"),
    ]
```

- [ ] **Step 2: Запустить новые тесты до реализации.**

Run: `.venv/Scripts/python.exe -m pytest tests/test_trade_rebalance.py -q`

Expected: `ImportError` для отсутствующей `build_rollover_orders`.

### Task 2: Добавить чистое планирование ролловера

**Files:**
- Modify: `trade/rebalance.py`
- Test: `tests/test_trade_rebalance.py`

- [ ] **Step 1: Добавить `build_rollover_orders(current_position, target_position, old_position)`.**

```python
def build_rollover_orders(
    current_position: int,
    target_position: int,
    old_position: int,
) -> list[tuple[str, str, int, str]]:
    orders = [
        ("ticker_open", action, quantity, reason)
        for action, quantity, reason in build_rebalance_orders(current_position, target_position)
    ]
    if old_position != 0:
        action = "Продажа" if old_position > 0 else "Покупка"
        reason = "Ролловер: закрытие лонга" if old_position > 0 else "Ролловер: закрытие шорта"
        orders.append(("ticker_close", action, abs(old_position), reason))
    return orders
```

- [ ] **Step 2: Повторно запустить тесты.**

Run: `.venv/Scripts/python.exe -m pytest tests/test_trade_rebalance.py -q`

Expected: PASS.

### Task 3: Подключить планировщик к EBS-адаптерам

**Files:**
- Modify: `trade/trade_mix_ebs.py:15-270`
- Modify: `trade/trade_rts_ebs.py:15-270`
- Modify: `trade/trade_si_ebs.py:15-270`
- Modify: `tests/test_trade_ebs.py`

- [ ] **Step 1: Импортировать `build_rollover_orders` и заменить ранний выход.**

```python
old_position = get_position(trade_account, ticker_close) if ticker_close != ticker_open else 0
orders = build_rollover_orders(current_position, target_position, old_position)
if not orders:
    done_marker.touch()
    sys.exit(0)
```

Для каждой записи `contract_role, action, quantity, reason` использовать `ticker_open` для `ticker_open` и `ticker_close` для `ticker_close`, сохраняя текущий порядок записей.

- [ ] **Step 2: Добавить статический контрактный тест для всех трёх адаптеров.**

```python
assert "from rebalance import build_rebalance_orders, build_rollover_orders" in script
assert "if delta == 0:" not in script
```

- [ ] **Step 3: Запустить связанные тесты.**

Run: `.venv/Scripts/python.exe -m pytest tests/test_trade_rebalance.py tests/test_trade_ebs.py -q`

Expected: PASS.

### Task 4: Проверить итоговую регрессию

**Files:**
- Verify only: `trade/rebalance.py`, `trade/trade_mix_ebs.py`, `trade/trade_rts_ebs.py`, `trade/trade_si_ebs.py`, `tests/test_trade_rebalance.py`, `tests/test_trade_ebs.py`

- [ ] **Step 1: Проверить синтаксис изменённых Python-файлов.**

Run: `.venv/Scripts/python.exe -m py_compile trade/rebalance.py trade/trade_mix_ebs.py trade/trade_rts_ebs.py trade/trade_si_ebs.py`

Expected: exit code 0.

- [ ] **Step 2: Выполнить полный набор тестов.**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: отсутствие новых падений; отдельно зафиксировать уже существующие падения, если они останутся.
