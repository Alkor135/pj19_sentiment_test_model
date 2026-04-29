# Анализ доходности из Buhinvest (RUR)

Папка предназначена для визуализации и анализа данных о доходности торговых операций из Excel-файла Buhinvest в рублях (RUR).

## Функционал

Скрипт `pl_buhinvest.py` строит PNG-графики:

1. **Чтение данных**:
   - Загружает лист `Data` из Excel-файла.
   - Использует колонки: `Дата`, `Profit/Loss к предыдущему`, `Общ. прибыль Руб.`.

2. **Обработка данных**:
   - Преобразует даты и числовые столбцы.
   - Удаляет некорректные значения.
   - Агрегирует данные по месяцам и дням.

3. **Генерация графиков**:
   - **`pl_by_month.png`** — столбчатый график ежемесячного Profit/Loss.
     - Положительные значения: синие столбцы.
     - Отрицательные значения: красные столбцы.
     - Подписи значений над/под столбцами.
   - **`cumulative_profit.png`** — линейный график накопительной прибыли по дням.

Скрипт `pl_buhinvest_interactive.py` строит HTML-отчёты:
- `pl_buhinvest_interactive.html` — интерактивный Plotly-отчёт.
- `pl_buhinvest_interactive_qs.html` — QuantStats tearsheet.

## Конфигурация

Путь к Excel-файлу задаётся в `settings.yaml`:

```yaml
buhinvest_excel_path: "C:/Users/Alkor/gd/ВТБ_ЕБС_SPBFUT192yc.xlsx"
```

Путь можно переопределить при запуске через `--file`.

## Использование

Из корня проекта:

```powershell
.venv/Scripts/python.exe buhinvest_analize/pl_buhinvest.py
.venv/Scripts/python.exe buhinvest_analize/pl_buhinvest.py --file C:/Users/Alkor/gd/ВТБ_ЕБС_SPBFUT192yc.xlsx
.venv/Scripts/python.exe buhinvest_analize/pl_buhinvest_interactive.py
```

Результаты сохраняются в `buhinvest_analize/`.

## Требования

- Python 3.10+
- pandas
- matplotlib
- plotly
- quantstats_lumi
- PyYAML

---

*Автор: Alkor135*  
*Дата: 2025*
