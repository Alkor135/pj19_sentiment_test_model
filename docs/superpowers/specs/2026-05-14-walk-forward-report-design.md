# Дизайн Отчёта Walk-Forward

## Цель

Добавить генератор отчётов для `walk_forward/results/`, который собирает дневные walk-forward результаты в понятный Excel workbook и HTML dashboard с графиками, рейтингами и показателями.

Генератор отчётов должен только читать существующие walk-forward артефакты и писать итоговые файлы в `walk_forward/results/`. Рабочие папки тикеров и моделей не изменяются.

## Входные Данные

Генератор читает:

```text
walk_forward/results/summary.csv
walk_forward/results/<TICKER>/<model>/summary.json
walk_forward/results/<TICKER>/<model>/trades.csv
```

`summary.csv` используется для дневных статусов, пропусков и ошибок. `trades.csv` используется для сделок, equity curve, drawdown и метрик качества модели.

## Выходные Файлы

Создать:

```text
walk_forward/results/walk_forward_report.xlsx
walk_forward/results/walk_forward_report.html
```

Оба файла считаются generated artifacts и остаются внутри уже игнорируемой папки `walk_forward/results/`.

## Архитектура

Создать модуль:

- `walk_forward/report.py`

Модуль должен содержать:

- загрузку и нормализацию `summary.csv`;
- обнаружение и загрузку всех `trades.csv`;
- расчёт leaderboard и агрегированных метрик;
- построение месячной и дневной матриц P/L;
- запись Excel workbook;
- запись HTML dashboard;
- Typer CLI-команду.

Подход можно брать из существующего `oos/report.py`, но метрики и графики должны учитывать дневную природу walk-forward результата.

## Excel Workbook

Создать листы:

- `Dashboard` — общие метрики по всему прогону:
  - тикеров;
  - моделей;
  - дней;
  - сделок;
  - общий P/L;
  - winrate;
  - profit factor;
  - max drawdown;
  - лучший тикер;
  - худший тикер;
  - лучшая модель;
  - худшая модель.
- `Leaderboard` — рейтинг всех `ticker/model`:
  - rank внутри тикера;
  - ticker;
  - model_dir;
  - sentiment_model;
  - days;
  - trades;
  - total_pnl;
  - winrate;
  - profit_factor;
  - max_drawdown;
  - recovery_factor;
  - avg_trade;
  - best_day;
  - worst_day;
  - score.
- `Ticker_Summary` — агрегаты по тикерам:
  - ticker;
  - models;
  - best_model;
  - total_pnl;
  - avg_model_pnl;
  - trades;
  - winrate;
  - max_drawdown.
- `Monthly_Matrix` — heatmap-таблица P/L по месяцам, строки `ticker / model`.
- `Daily_Matrix` — P/L по дням, строки `ticker / model`.
- Отдельные листы `RTS`, `MIX`, `NG`, `SI`, `SPYF` — по каждому тикеру:
  - leaderboard моделей тикера;
  - месячные итоги;
  - дневные итоги;
  - топ прибыльных сделок;
  - топ убыточных сделок.
- `Raw_Summary` — нормализованный `summary.csv`.
- `Raw_Trades` — объединённые сделки всех моделей.
- `Errors` — строки со статусами не `ok` и сообщениями ошибок/пропусков.

Excel должен быть удобным для ручного анализа:

- автофильтры;
- закреплённая верхняя строка;
- читаемые ширины колонок;
- цветовое выделение положительного/отрицательного P/L;
- числовые форматы для денег и процентов.

## HTML Dashboard

Создать self-contained HTML-файл без зависимости от интернета. Для графиков использовать Plotly с включением JavaScript в файл или локально доступный self-contained режим.

Структура страницы:

- верхняя панель карточек с ключевыми метриками;
- блок лучших моделей по тикерам;
- общий leaderboard;
- общий equity curve по всем моделям;
- equity curves по тикерам;
- сравнение топ-5 моделей внутри каждого тикера;
- drawdown-графики;
- месячная heatmap P/L;
- дневные bar-графики P/L;
- секции по тикерам `RTS`, `MIX`, `NG`, `SI`, `SPYF`;
- блок `Ошибки и пропуски`.

Чтобы HTML оставался читаемым, графики сравнения моделей по умолчанию показывают топ-5 моделей внутри тикера. Все модели должны оставаться доступными в таблицах.

## Метрики

Для каждой модели считать:

- `days` — количество дней в walk-forward summary;
- `trades` — количество сделок;
- `total_pnl` — суммарный P/L;
- `winrate` — доля прибыльных сделок;
- `profit_factor` — gross profit / gross loss;
- `max_drawdown` — максимальная просадка по cumulative P/L;
- `recovery_factor` — total P/L / abs(max_drawdown);
- `avg_trade` — средний P/L сделки;
- `best_day` — лучший дневной P/L;
- `worst_day` — худший дневной P/L;
- `score` — ранжирующий показатель.

Рекомендуемый `score`:

```text
score = total_pnl + max_drawdown * 0.5
```

Такой score предпочитает прибыльные модели, но штрафует глубокие просадки. Если потребуется, формулу можно вынести в отдельную функцию и позже настроить.

## CLI

Основная команда:

```powershell
.venv\Scripts\python.exe -m walk_forward.report
```

Опции:

```powershell
.venv\Scripts\python.exe -m walk_forward.report --results-dir walk_forward/results
.venv\Scripts\python.exe -m walk_forward.report --output-html walk_forward/results/walk_forward_report.html
.venv\Scripts\python.exe -m walk_forward.report --output-xlsx walk_forward/results/walk_forward_report.xlsx
```

Значения по умолчанию:

- `summary_csv`: `walk_forward/results/summary.csv`;
- `results_dir`: `walk_forward/results`;
- `output_html`: `walk_forward/results/walk_forward_report.html`;
- `output_xlsx`: `walk_forward/results/walk_forward_report.xlsx`.

## Ошибки И Пропуски

Если `summary.csv` отсутствует, CLI должен завершаться понятной ошибкой.

Если по отдельной модели отсутствует `trades.csv`, генератор не должен падать весь отчёт. Такая модель попадает в `Errors` с причиной отсутствия trade-файла.

Строки summary со статусом не `ok` должны попадать в `Errors`.

## Тесты

Добавить тесты:

- `build_leaderboard` корректно агрегирует сделки по `ticker/model`;
- `build_ticker_summary` выбирает лучшую модель тикера;
- `build_monthly_matrix` строит строки `ticker / model` и месячные колонки;
- `build_daily_matrix` строит дневные колонки;
- `build_report` создаёт HTML и Excel workbook;
- workbook содержит листы `Dashboard`, `Leaderboard`, `Ticker_Summary`, `Monthly_Matrix`, `Daily_Matrix`, тикерные листы, `Raw_Summary`, `Raw_Trades`, `Errors`;
- HTML содержит ключевые секции и названия тикеров;
- генератор не падает при отсутствующем `trades.csv`, а записывает проблему в `Errors`.

## Критерии Приёмки

- Команда `.venv\Scripts\python.exe -m walk_forward.report` создаёт Excel и HTML отчёты.
- Excel содержит общие результаты и отдельные листы по тикерам.
- HTML содержит графики equity, drawdown, heatmap и таблицы результатов.
- По умолчанию на графиках сравнения показываются топ-5 моделей по тикеру.
- Все outputs пишутся только в `walk_forward/results/`.
- Рабочие модельные папки не изменяются.
