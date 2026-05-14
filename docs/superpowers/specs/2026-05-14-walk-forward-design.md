# Дизайн Walk-Forward Бэктеста

## Цель

Добавить дневной walk-forward бэктест для сравнения уже рассчитанных sentiment-сигналов по тикерам и моделям, не меняя рабочие модельные скрипты и не перезаписывая их артефакты.

Новый пайплайн должен читать существующие файлы `sentiment_scores.pkl` и записывать все создаваемые артефакты только в `walk_forward/results/`.

## Область Работ

Входит в задачу:

- Новый изолированный пакет `walk_forward/`.
- Дневная rolling walk-forward проверка.
- Конфигурация в `walk_forward/settings.yaml`.
- CLI-запуск для выбранных тикеров и моделей.
- Сводные результаты и отдельные trade-файлы по моделям.
- Опциональные дневные диагностические артефакты, управляемые настройкой.
- Тесты окон дат, изоляции, генерации правил и записи результатов.

Не входит в задачу:

- Запуск Ollama sentiment analysis.
- Изменение тикерных/модельных `run_report.py`, `rules_recommendation.py`, `sentiment_backtest.py` или созданных артефактов в модельных папках.
- Запись прогнозов для live-торговли.
- Изменение существующей методологии `oos/`.

## Конфигурация

Настройки по умолчанию в `walk_forward/settings.yaml`:

```yaml
tickers: [rts, mix, ng, si, spyf]
models: []
backtest_start_date: "2025-04-01"
backtest_end_date: null
train_months: 6
output_dir: "walk_forward/results"
save_daily_artifacts: false
min_train_rows: 20
keep_going: true
```

Правила интерпретации:

- `models: []` означает автоматическое обнаружение всех моделей из `settings.yaml` каждого тикера.
- `backtest_end_date: null` означает использование последней доступной даты из загруженного sentiment PKL.
- `train_months` задаёт rolling-окно обучения для каждого тестируемого дня.
- `save_daily_artifacts: false` по умолчанию оставляет результаты компактными.

## Архитектура

Создать следующие файлы:

- `walk_forward/__init__.py`
- `walk_forward/settings.yaml`
- `walk_forward/core.py`
- `walk_forward/run_walk_forward.py`
- `walk_forward/README.md`

Опциональное развитие после стабилизации базового runner:

- `walk_forward/report.py` для HTML/XLSX dashboard.

Реализация должна переиспользовать или повторить чистую логику из `oos/core.py`, где это уместно:

- нормализация sentiment PKL;
- группировка follow-сделок по sentiment;
- рекомендация правил;
- подбор правила под значение sentiment;
- построение строк бэктеста.

Новый пакет не должен импортировать или запускать скрипты из модельных папок, потому что эти скрипты пишут в рабочие директории артефактов.

## Алгоритм

Для каждой выбранной пары `ticker/model`:

1. Загрузить настройки тикера/модели с тем же поведением merge, что и в текущем OOS runner.
2. Разрешить путь и прочитать `sentiment_output_pkl`.
3. Нормализовать данные в date-indexed frame с колонками `sentiment` и `next_body`.
4. Построить список тестовых дат от `backtest_start_date` до `backtest_end_date` или последней доступной даты в PKL.
5. Для каждой тестовой даты `D`:
   - начало обучения = `D - train_months`;
   - конец обучения = `D - 1 день`;
   - training frame = строки от начала обучения до конца обучения;
   - test frame = строка за дату `D`;
   - пропустить дату или записать ошибку, если строк обучения меньше `min_train_rows`;
   - построить group stats по training frame;
   - построить rules по group stats;
   - применить rules к одному тестовому дню;
   - добавить полученную сделку или статус skip в результат модели.
6. Сохранить сделки по модели и общую сводку.

Окно обучения никогда не должно включать тестовый день или любую более позднюю дату.

## Структура Вывода

Всегда записывать:

```text
walk_forward/results/summary.csv
walk_forward/results/summary.xlsx
walk_forward/results/<TICKER>/<model>/trades.xlsx
walk_forward/results/<TICKER>/<model>/trades.csv
walk_forward/results/<TICKER>/<model>/summary.json
```

Если `save_daily_artifacts: true`, дополнительно записывать:

```text
walk_forward/results/<TICKER>/<model>/daily/YYYY-MM-DD/group_stats.xlsx
walk_forward/results/<TICKER>/<model>/daily/YYYY-MM-DD/rules.yaml
```

Файлы не должны записываться в `<ticker>/<model>/`, `backtest/`, `group_stats/`, `plots/` или существующий `oos/results/`.

## CLI

Основная команда:

```powershell
.venv\Scripts\python.exe -m walk_forward.run_walk_forward
```

Полезные переопределения:

```powershell
.venv\Scripts\python.exe -m walk_forward.run_walk_forward --tickers rts --models gemma3_12b --start-date 2025-04-01 --train-months 6
```

CLI-опции должны иметь приоритет над `walk_forward/settings.yaml`.

## Обработка Ошибок

При `keep_going: true` ошибки отдельного тикера/модели/даты записываются в summary, а runner продолжает работу.

Ожидаемые восстанавливаемые ошибки:

- отсутствует PKL;
- нет тестовой строки за дату;
- недостаточно строк обучения;
- все обучающие значения `total_pnl` равны нулю, и правила нельзя вывести;
- построенные правила не дают сделки на тестовую дату.

При `keep_going: false` первая ошибка завершает процесс с ненулевым кодом.

## Тесты

Добавить сфокусированные тесты в `tests/`:

- окно обучения исключает тестовый день и будущие даты;
- `train_months: 6` выбирает корректное rolling-окно;
- запись результатов остаётся внутри переданной временной output-директории;
- `save_daily_artifacts: false` не создаёт дневные rules или group stats;
- merge CLI/settings учитывает переопределения;
- строки summary различают статусы ok, skipped и error.

## Критерии Приёмки

- Запуск walk-forward CLI не изменяет существующие модельные папки.
- Конфиг по умолчанию использует `backtest_start_date: "2025-04-01"`, `train_months: 6` и `save_daily_artifacts: false`.
- Для каждого тестируемого дня rules строятся только по данным до этого дня.
- Summary и результаты по моделям записываются только в `walk_forward/results/`.
- Тесты покрывают rolling-window поведение и изоляцию артефактов.
