# Walk-forward в `pj19_sentiment_test_model`

Этот документ описывает фактическую реализацию walk-forward по логике Python-скриптов проекта. Существующие README, комментарии и docstring использовались только как навигация; все утверждения ниже сверены с исполняемым кодом.

## Кратко

В проекте есть два walk-forward-контура:

1. **Централизованный исследовательский бэктест** в `walk_forward/`.
   Он прогоняет несколько тикеров и моделей, ничего не записывает в рабочие модельные папки и сохраняет результаты в `walk_forward/results/`.
2. **Оперативный модельный контур** через `<ticker>/<model>/*_wf.py`.
   Он строит актуальные `rules_wf.yaml`, создаёт live-прогноз в обычном торговом формате и может сформировать модельный WF-отчёт рядом с обычным отчётом.

Вся расчётная логика находится в:

- `walk_forward/core.py` — дневное walk-forward-ядро;
- `walk_forward/live_predict.py` — модельный live-прогноз, модельные отчёты и тикерные WF-оркестраторы;
- `walk_forward/run_walk_forward.py` — централизованный CLI по тикерам и моделям;
- `walk_forward/report.py` — общий Excel/HTML-отчёт.

Во всех пяти тикерах и всех модельных папках проверены WF-обёртки:

- 50 файлов `rules_recommendation_wf.py` идентичны;
- 50 файлов `sentiment_to_predict_wf.py` идентичны;
- 50 файлов `sentiment_backtest_wf.py` идентичны;
- 50 файлов `run_report_fw.py` идентичны.

Они не содержат собственной расчётной логики, а только вызывают фабрики CLI из `walk_forward/live_predict.py`.

Дополнительно массово проверены все связанные модельные семейства:

- во всех 50 `sentiment_analysis.py` присутствуют формирование `next_body` по следующей торговой свече, строгий парсинг sentiment и дедупликация по `source_date`;
- во всех 50 `sentiment_group_stats.py`, 50 `rules_recommendation.py` и 50 `sentiment_backtest.py` присутствуют одинаковые ключевые расчётные этапы, на которых основан WF или сравнение с ним;
- все 50 обычных модельных `sentiment_to_predict.py` сохраняют совместимый торговый формат;
- все 50 модельных `run_trade.py` используют обычный пайплайн, а не WF;
- все 5 тикерных `run_<ticker>_trade.py` запускают модельные `run_trade.py`, shared-подготовку и обычный combine.

## Временная ось данных

Понимание `source_date` и `next_body` критично для корректной интерпретации WF.

### Как формируется одна строка sentiment

`<ticker>/shared/create_markdown_files.py` создаёт файл `YYYY-MM-DD.md` по торговому интервалу:

```text
21:00 предыдущей торговой даты -> 20:59:59 даты YYYY-MM-DD
```

Имя markdown-файла становится `source_date`.

Модельный `sentiment_analysis.py`:

1. рассчитывает один sentiment для markdown-файла;
2. дедуплицирует результат по `source_date`, оставляя последнюю обработанную строку;
3. добавляет рыночные признаки из дневной SQLite-БД;
4. сохраняет `sentiment_scores.pkl`.

Для даты `D`:

- `body(D)` — `CLOSE - OPEN` дневной свечи с меткой `D`;
- `next_body(D)` — `body` первой доступной торговой свечи строго после `D`.

Таким образом, сигнал с `source_date=D`, сформированный после 21:00 даты `D`, оценивается по движению следующей торговой сессии `next_body(D)`.

### Какие данные известны в live-режиме

При построении правил для целевой даты `D` обучение заканчивается датой `D - 1 календарный день`.

Строка `D - 1` может содержать `next_body`, соответствующий свече `D`. После завершения сессии `D` в 20:59:59 это уже известный результат, поэтому он допустим для генерации сигнала после 21:00 даты `D`.

Строка самой даты `D` используется только как текущий sentiment. Её `next_body(D)` ещё неизвестен и для live-прогноза не требуется.

Операционная схема предполагает запуск после границы `time_start`, которая сейчас равна `21:00:00`.

## Входные данные и проверки

WF читает готовый `sentiment_scores.pkl`. Сам walk-forward-контур не вызывает Ollama и не создаёт sentiment.

Для исторического бэктеста обязательны колонки:

```text
source_date, sentiment, next_body
```

Для live-прогноза текущего дня обязательны только:

```text
source_date, sentiment
```

При загрузке:

- `source_date` преобразуется в `date`;
- `sentiment` и `next_body` преобразуются в числа;
- строки с отсутствующими обязательными значениями удаляются;
- несколько строк с одинаковой `source_date` считаются ошибкой;
- данные индексируются и сортируются по `source_date`.

Исторический WF проходит только по датам, реально присутствующим в PKL. Календарные дни, торговые дни без markdown-файла и дни без sentiment-строки в тест не попадают.

## Алгоритм одного walk-forward-дня

Для тестовой даты `D` и окна `N` месяцев `walk_forward/core.py` выполняет следующие шаги.

### 1. Выбор обучающего окна

```text
train_start = D - DateOffset(months=N)
train_end   = D - 1 календарный день
test        = только строка с source_date=D
```

`DateOffset(months=N)` означает календарные месяцы, а не фиксированное число торговых дней.

Границы включительные:

```text
train_start <= source_date <= train_end
```

### 2. Проверка минимального объёма

Если число строк обучения меньше `min_train_rows`, день получает:

```text
status=skipped
skip_reason=insufficient_train_rows
```

Порог применяется ко всему обучающему окну. Отдельного минимального количества наблюдений для каждого sentiment нет.

### 3. Расчёт обучающих follow-сделок

Для каждой строки обучения сначала моделируется стратегия `follow`:

```text
sentiment >= 0 -> LONG
sentiment < 0  -> SHORT

PnL_LONG  = next_body * quantity
PnL_SHORT = -next_body * quantity
```

Комиссии, проскальзывание, гарантийное обеспечение и стоимость капитала не учитываются. P/L выражен в пунктах движения, умноженных на `quantity_test`.

### 4. Группировка по sentiment

Для каждого целого значения от `-10` до `+10` считаются:

- `count_pos` — число прибыльных follow-сделок;
- `count_neg` — число убыточных follow-сделок;
- `total_pnl` — сумма follow-P/L;
- `trades` — число наблюдений.

Решение строится по знаку `total_pnl`, а не по win rate:

```text
total_pnl > 0 -> follow
total_pnl < 0 -> invert
```

### 5. Fallback для нулевого или отсутствующего sentiment

Если `total_pnl == 0`, код ищет ближайшие sentiment слева и справа с ненулевым `total_pnl`.

Правила выбора:

1. если найден только один кандидат, берётся знак его `total_pnl`;
2. если найдены оба, берётся кандидат с большим `abs(total_pnl)`;
3. если абсолютные значения равны, эта пара игнорируется и поиск продолжается дальше;
4. если ненулевую рекомендацию определить невозможно, построение правил завершается ошибкой.

При такой ошибке тестовый день получает:

```text
status=skipped
skip_reason=rules_unavailable
```

Генератор создаёт 21 точное правило, по одному на каждое целое значение `-10..+10`. Он сам не генерирует `skip`.

### 6. Применение правил к тестовой строке

```text
action=follow:
    sentiment >= 0 -> LONG
    sentiment < 0  -> SHORT

action=invert:
    sentiment >= 0 -> SHORT
    sentiment < 0  -> LONG
```

Для `sentiment=0`:

- `follow` означает `LONG`;
- `invert` означает `SHORT`.

Если sentiment не попал ни в одно правило, используется `skip`. На практике это возможно для нецелого значения или значения вне диапазона `-10..+10`.

На одну тестовую дату формируется максимум одна сделка. Позиции между датами не переносятся: каждый результат является независимой однодневной модельной сделкой.

## Статусы дня

`run_walk_forward_day()` поддерживает следующие результаты:

| Статус | Причина | Что означает |
|---|---|---|
| `ok` | пусто | Правила построены, сделка сформирована |
| `skipped` | `no_test_row` | Для запрошенной даты нет строки |
| `skipped` | `insufficient_train_rows` | Недостаточно строк в обучающем окне |
| `skipped` | `rules_unavailable` | Правила невозможно построить |
| `skipped` | `no_trade` | Правило вернуло `skip` |

Обычный модельный цикл перебирает только доступные `source_date`, поэтому `no_test_row` в нём практически не возникает; этот статус полезен при прямом вызове одного дня.

## Два WF-контура

### Централизованный исследовательский контур

Точка входа:

```powershell
.venv/Scripts/python.exe -m walk_forward.run_walk_forward
```

Он:

1. читает `walk_forward/settings.yaml`;
2. читает `<ticker>/settings.yaml`;
3. находит модели из секции `models`, если глобальный список `models` пуст;
4. загружает готовые модельные PKL;
5. запускает полный дневной WF;
6. пишет результаты только в отдельный `output_dir`.

По умолчанию:

```yaml
tickers: [rts, mix, ng, si, spyf]
models: []
backtest_start_date: "2025-08-01"
backtest_end_date: null
train_months: 6
output_dir: "walk_forward/results"
save_daily_artifacts: false
min_train_rows: 20
keep_going: true
```

Пустой `models` означает все модели каждого тикера.

Централизованный запуск обнаруживает модели по секции `models` тикерного YAML. Тикерный `run_<ticker>_report_fw.py`, напротив, обнаруживает фактические подпапки, в которых существует `run_report_fw.py`, и исключает только `combine` и `shared`.

Отдельного WF-контура для `combine` нет. Централизованный запуск берёт только модели из секции `models`, а тикерный WF-оркестратор явно исключает папку `combine`. Обычный combine умеет читать совместимые файлы `up/down/skip`, но не строит собственные walk-forward-правила и не имеет отдельного WF-бэктеста.

CLI-параметры имеют приоритет над `walk_forward/settings.yaml`:

```powershell
.venv/Scripts/python.exe -m walk_forward.run_walk_forward `
  --tickers rts,mix `
  --models qwen3_14b,gemma4_e4b `
  --start-date 2025-09-01 `
  --end-date 2026-05-31 `
  --train-months 6 `
  --min-train-rows 20 `
  --save-daily-artifacts `
  --keep-going
```

`keep_going` позволяет продолжить остальные модели после ошибки, но итоговый процесс всё равно завершится с кодом `1`, если была хотя бы одна модельная ошибка.

### Оперативный модельный контур

В каждой модельной папке есть четыре тонкие обёртки:

| Скрипт | Назначение |
|---|---|
| `rules_recommendation_wf.py` | Строит актуальные `rules_wf.yaml` и групповую статистику |
| `sentiment_to_predict_wf.py` | Применяет `rules_wf.yaml` к sentiment целевой даты |
| `sentiment_backtest_wf.py` | Формирует модельный исторический WF XLSX и HTML |
| `run_report_fw.py` | Формирует модельный WF XLSX/HTML и при необходимости открывает Chrome |

Суффикс `fw` используется только в именах report-оркестраторов; он относится к тому же walk-forward-контуру, что и суффикс `wf` в расчётных скриптах и артефактах.

Общие параметры берутся из `<ticker>/settings.yaml`:

```yaml
rules_train_months: 6
rules_min_train_rows: 20
quantity_test: 1
sentiment_output_pkl: ...
predict_path: ...
time_start: "21:00:00"
```

Построение live-правил:

```powershell
.venv/Scripts/python.exe rts/qwen3_14b/rules_recommendation_wf.py
.venv/Scripts/python.exe rts/qwen3_14b/rules_recommendation_wf.py `
  --target-date 2026-06-05 `
  --train-months 6 `
  --min-train-rows 20
```

Результаты:

```text
rts/qwen3_14b/rules_wf.yaml
rts/qwen3_14b/group_stats/sentiment_group_stats_wf.xlsx
```

Генерация live-прогноза:

```powershell
.venv/Scripts/python.exe rts/qwen3_14b/sentiment_to_predict_wf.py
.venv/Scripts/python.exe rts/qwen3_14b/sentiment_to_predict_wf.py --target-date 2026-06-05
```

`sentiment_to_predict_wf.py` не перестраивает правила. Он использует уже существующий `rules_wf.yaml` и не проверяет, что этот файл был построен именно для целевой даты. Поэтому перед live-прогнозом необходимо явно запускать `rules_recommendation_wf.py`.

## Историческое тестирование

### Централизованный WF-бэктест

Рекомендуемый исследовательский запуск:

```powershell
.venv/Scripts/python.exe -m walk_forward.run_walk_forward `
  --tickers rts `
  --models qwen3_14b `
  --start-date 2025-09-01 `
  --train-months 6 `
  --min-train-rows 20 `
  --no-save-daily-artifacts
```

Структура результатов:

```text
walk_forward/results/
  summary.csv
  summary.xlsx
  <TICKER>/
    <model>/
      trades.csv
      trades.xlsx
      summary.json
      daily/                     # только при --save-daily-artifacts
        YYYY-MM-DD/
          group_stats.xlsx
          rules.yaml
```

`summary.csv` содержит дневные статусы всех моделей. `summary.json` внутри модельной папки содержит агрегированные показатели модели:

- число дней;
- число `ok`, `skipped` и `error` дней;
- число сделок;
- `total_pnl`;
- win rate;
- max drawdown.

### Общий WF-отчёт

```powershell
.venv/Scripts/python.exe -m walk_forward.report --no-open-browser
```

Создаются:

```text
walk_forward/results/walk_forward_report.html
walk_forward/results/walk_forward_report.xlsx
```

Рейтинг модели внутри тикера рассчитывается так:

```text
score = total_pnl + max_drawdown * 0.5
```

`max_drawdown` отрицательный, поэтому половина абсолютной просадки уменьшает score.

Excel содержит:

- `Dashboard`;
- `Leaderboard`;
- `Ticker_Summary`;
- `Monthly_Matrix`;
- `Daily_Matrix`;
- отдельные листы тикеров;
- `Raw_Summary`;
- `Raw_Trades`;
- `Errors`.

В `Errors` попадают не только ошибки, но и пропущенные WF-дни.

HTML содержит общую equity, drawdown, дневной P/L, месячную heatmap, рейтинг и top-5 equity по каждому тикеру.

### Модельный и тикерный WF-отчёт

Одна модель:

```powershell
.venv/Scripts/python.exe rts/qwen3_14b/run_report_fw.py --no-open-browser
```

Все модели одного тикера:

```powershell
.venv/Scripts/python.exe rts/run_rts_report_fw.py --no-open-browser --keep-going
.venv/Scripts/python.exe rts/run_rts_report_fw.py --only qwen3_14b,gemma4_e4b
```

Модельный отчёт пишет:

```text
<ticker>/<model>/backtest/sentiment_backtest_results_wf.xlsx
<ticker>/<model>/plots/sentiment_backtest_wf.html
```

Арифметика WF берётся из `walk_forward/core.py`. Для HTML переиспользуется функция `build_report()` из обычного модельного `sentiment_backtest.py`. QuantStats для WF-отчёта не создаётся.

Если CLI-границы не переданы, модельный WF-бэктест выбирает даты в таком порядке:

```text
start:
  wf_backtest_date_from
  -> backtest_date_from
  -> первая доступная source_date

end:
  wf_backtest_date_to
  -> backtest_date_to
  -> последняя доступная source_date
```

В текущих тикерных настройках `wf_backtest_date_from/to` не заданы, поэтому используются обычные `backtest_date_from/to`.

### Сравнение с обычным backtest

```powershell
.venv/Scripts/python.exe -m compare_backtests.build_report --no-open-browser
```

Отчёт сравнивает:

```text
обычный: <ticker>/<model>/backtest/sentiment_backtest_results.xlsx
WF:      walk_forward/results/<TICKER>/<model>/trades.xlsx
```

Сравнение выполняется только на датах, где есть сделка в обоих источниках. На этих общих датах заново считаются:

- cumulative P/L;
- total P/L;
- delta P/L;
- max drawdown;
- win rate;
- доля совпадающих `action` и `direction`.

Это не сравнение всех календарных или всех доступных sentiment-дней. Дни, пропущенные одной из стратегий, исключаются из сравнения.

Концептуальное различие источников:

- обычный backtest применяет один статический `rules.yaml` ко всему выбранному периоду;
- WF для каждой тестовой даты заново строит правила только по предшествующему обучающему окну.

### OOS не является walk-forward

Папка `oos/` реализует leave-one-month-out:

- тестовый месяц исключается;
- все остальные месяцы используются для обучения;
- в обучение явно попадают и будущие относительно тестового месяца строки.

Это полезный OOS-эксперимент, но он не является хронологически причинным walk-forward. Тест `test_leave_one_month_out_keeps_future_rows_in_training` специально закрепляет такое поведение.

## Торговля

### Формат WF-прогноза

WF-прогноз совместим с обычными торговыми скриптами:

```text
Дата: 2026-06-05
Sentiment: -3.00
Action: follow
Status: ok
Предсказанное направление: down
```

Торговые адаптеры ищут только строку:

```text
Предсказанное направление: up|down|skip
```

Они не знают, был прогноз создан обычным или WF-скриптом.

### Фактическое использование WF в текущем расписании

Стандартные модельные `<ticker>/<model>/run_trade.py` **не используют WF**. Они запускают обычные:

```text
sentiment_analysis.py
sentiment_group_stats.py
rules_recommendation.py
sentiment_backtest.py
sentiment_to_predict.py
```

Тикерные `run_<ticker>_trade.py` также запускают эти обычные модельные `run_trade.py`.

WF включён в ручное корневое расписание `run_all.py` только для текущей торговой цепочки RTS:

```text
rts/shared/download_minutes_to_db.py
rts/shared/convert_minutes_to_days.py
rts/shared/create_markdown_files.py
rts/qwen3_14b/sentiment_analysis.py
rts/qwen3_14b/sentiment_group_stats.py
rts/qwen3_14b/rules_recommendation.py
rts/qwen3_14b/rules_recommendation_wf.py
rts/qwen3_14b/sentiment_to_predict_wf.py
trade/trade_rts_ebs.py
```

Обычный `sentiment_to_predict.py` для этой RTS-модели в `run_all.py` закомментирован. Обычные `sentiment_group_stats.py` и `rules_recommendation.py` всё ещё выполняются, но WF-прогноз использует только `rules_wf.yaml`.

Для MIX и SI активные EBS-цепочки в `run_all.py` используют обычные `sentiment_to_predict.py`.

Текущая секция `accounts.ebs` в `trade/settings.yaml` задаёт:

| Тикер | Источник прогноза | `target_quantity` |
|---|---|---:|
| RTS | `rts/qwen3_14b` | 3 |
| MIX | `mix/gemma4_e4b` | 0 |
| SI | `si/qwen2.5_7b` | 0 |

Пути в таблице являются логическими окончаниями внешних `predict_dir`; фактические абсолютные пути задаются в `trade/settings.yaml`.

### Защита файла прогноза

`sentiment_to_predict_wf.py` пишет файл атомарно через временный `.tmp` и `replace()`.

Если файл целевой даты уже существует:

- файл, созданный в эту дату до `time_start`, считается тестовым и может быть заменён;
- файл, созданный после `time_start`, сохраняется без изменений;
- файл с другой датой или неожиданным `mtime` не удаляется.

Если текущей sentiment-строки нет, создаётся прогноз:

```text
Status: no_pkl_row
Предсказанное направление: skip
```

Если отсутствует `rules_wf.yaml`/PKL или срабатывает предусмотренная проверка правил, создаётся `skip` с `missing_file` или `error`. Скрипт при этом завершает работу успешно. Неожиданные исключения, не относящиеся к `FileNotFoundError` или `ValueError`, не преобразуются в `skip`.

`rules_recommendation_wf.py` ведёт себя строже: например, недостаток обучающих строк вызывает ошибку CLI. В `run_all.py` этот шаг находится в `HARD_STEPS`, поэтому торговая цепочка останавливается до создания прогноза и запуска EBS.

Это важно для торговли: `skip` для EBS означает целевую позицию `0`, то есть существующая позиция может быть закрыта. Отсутствующий или пустой файл прогноза, напротив, означает «не торговать» и не приводит позицию к нулю.

### Как EBS исполняет прогноз

`trade_rts_ebs.py`, `trade_mix_ebs.py` и `trade_si_ebs.py`:

1. читают сегодняшний файл из `accounts.ebs.<ticker>.predict_dir`;
2. преобразуют направление в целевую позицию:

```text
up   -> +target_quantity
down -> -target_quantity
skip -> 0
```

3. читают текущую позицию;
4. строят один или два рыночных ордера для перехода к целевой позиции;
5. при ролловере отдельно закрывают старый `ticker_close`;
6. дописывают транзакции в QUIK `.tri` в кодировке `cp1251`.

При развороте сначала закрывается старая позиция, затем открывается новая.

### Торговые защиты

В EBS-адаптерах реализованы следующие защиты:

- используется только файл прогноза сегодняшней даты;
- отсутствующий, пустой или невалидный прогноз не вызывает торгов;
- позиции берутся из ручного `trade/state/positions.yaml` либо из LUA-экспорта `trade/quik_export/positions.json`;
- если нет override для обоих используемых контрактов, `positions.json` обязан быть обновлён сегодня;
- устаревший экспорт позиций останавливает скрипт с ошибкой;
- `trade/state/<ticker>_<account>_<date>.done` защищает от повторной записи заявок;
- тестовый done-маркер, созданный сегодня до `done_marker_reset_before`, удаляется;
- done-маркер создаётся и тогда, когда позиция уже соответствует цели.

Торговые скрипты нельзя запускать для обычной проверки документации или тестов: они могут записать реальные `.tri`-транзакции.

## Автоматизированные тесты

Проект использует `pytest`, включая тесты в стиле `unittest`.

Полный запуск:

```powershell
.venv/Scripts/python.exe -m pytest -q
```

Основные WF-тесты:

| Файл | Что проверяется |
|---|---|
| `tests/test_walk_forward_core.py` | Окна, отсутствие тестовой строки в обучении, skip-статусы, сделки и изоляция output |
| `tests/test_walk_forward_runner.py` | CLI/YAML-приоритеты, объединение настроек и валидность `walk_forward/settings.yaml` |
| `tests/test_walk_forward_live_predict.py` | Live-правила, формат прогноза, текущая строка без `next_body`, модельные XLSX/HTML и skip без PKL |
| `tests/test_walk_forward_report.py` | Leaderboard, матрицы, Excel/HTML и ошибки загрузки |
| `tests/test_compare_backtests_report.py` | Поиск пар, сравнение только пересекающихся дат и HTML |

Связанные торговые тесты:

| Файл | Что проверяется |
|---|---|
| `tests/test_trade_rebalance.py` | Сокращение и разворот позиции |
| `tests/test_trade_ebs.py` | Пути прогнозов/`.tri`, контракты из `common`, done-marker |
| `tests/test_predict_file_delete_policy.py` | Политика перезаписи обычных прогнозов относительно 21:00 |
| `tests/test_run_all.py` | Ручное расписание корневого оркестратора |

На момент проверки 5 июня 2026 года полный набор дал:

```text
289 passed, 2 failed
```

Обе ошибки находятся в `tests/test_run_all.py`: тесты ожидают старый состав `HARD_STEPS`, тогда как фактический `run_all.py` уже переключил активную RTS-цепочку на `qwen3_14b` с WF-прогнозом и сократил активные MIX-шаги. WF-ядро, live-WF, отчёты, сравнение и торговая ребалансировка в этом прогоне прошли.

`pytest` используется тестами, но не указан в `requirements.txt`; для нового окружения его может потребоваться установить отдельно.

Автотесты не выполняют:

- реальные запросы к Ollama;
- полный WF по внешним PKL и SQLite-БД;
- реальный запуск Chrome;
- реальную запись EBS `.tri`;
- проверку исполнения заявок в QUIK.

## Ограничения и важные следствия

1. **WF не создаёт sentiment.** Результат зависит от актуальности уже существующего `sentiment_scores.pkl`.
2. **Live-правила и прогноз — два отдельных шага.** Прогноз может применить устаревший `rules_wf.yaml`, если предварительно не обновить правила.
3. **Нет проверки даты внутри `rules_wf.yaml`.** Метаданные окна находятся только в YAML-комментарии и программно не валидируются.
4. **Обучение ограничено общим числом строк, но не числом наблюдений на sentiment.** Не встречавшиеся значения получают действие через fallback соседей.
5. **Исторический тест включает только даты с sentiment-строками.** Дни без новостей/markdown не моделируются как `skip`.
6. **Сделки независимы и однодневны.** Позиция, комиссии, проскальзывание и реальные ограничения исполнения не моделируются.
7. **Сравнение ordinary/WF использует только общие даты сделок.** Оно может скрыть различия в числе пропусков.
8. **Стандартные `run_trade.py` не являются WF.** Для WF-торговли нужен явный запуск `rules_recommendation_wf.py` и `sentiment_to_predict_wf.py`.
9. **Ошибка live-прогноза часто превращается в `skip`.** Для EBS это команда перейти в нулевую позицию, а не просто отказаться от нового ордера.
10. **Отдельного WF combine нет.** WF оценивает и торгует отдельную модель; combine остаётся обычным файловым контуром согласования сигналов.
11. **Все генерируемые WF-артефакты игнорируются git.** В `.gitignore` входят `rules_wf.yaml`, `walk_forward/results/`, `*.xlsx`, `*.html`, `*.csv`, `backtest/`, `group_stats/`.

## Карта файлов

```text
walk_forward/
  core.py                 # расчёт одного дня и полного модельного WF
  live_predict.py         # live rules/predict, модельные и тикерные WF-отчёты
  run_walk_forward.py     # централизованный мульти-тикерный запуск
  report.py               # общий Excel/HTML dashboard
  settings.yaml           # настройки централизованного эксперимента

<ticker>/
  settings.yaml           # rules_train_months, rules_min_train_rows, пути, quantity
  run_<ticker>_report_fw.py
  <model>/
    rules_recommendation_wf.py
    sentiment_to_predict_wf.py
    sentiment_backtest_wf.py
    run_report_fw.py

compare_backtests/
  build_report.py         # ordinary против централизованного WF

trade/
  settings.yaml           # источник прогноза и целевой объём EBS
  read_positions.py       # позиции YAML override -> LUA JSON -> 0
  rebalance.py            # переход текущая позиция -> целевая позиция
  trade_*_ebs.py          # запись QUIK .tri

tests/
  test_walk_forward_*.py
  test_compare_backtests_report.py
  test_trade_rebalance.py
  test_trade_ebs.py
```

## Практические чек-листы

### Исследовательский WF

1. Обновить нужные `sentiment_scores.pkl`.
2. Запустить `python -m walk_forward.run_walk_forward` с явными тикерами, моделями и периодом.
3. Проверить `summary.csv` на `skipped` и `error`.
4. Построить `python -m walk_forward.report --no-open-browser`.
5. При сравнении с ordinary backtest учитывать, что compare-отчёт использует только общие даты сделок.

### Live WF-прогноз без исполнения сделки

1. Обновить минутные и дневные данные.
2. Создать markdown текущей завершённой сессии.
3. Обновить sentiment текущей даты.
4. Запустить `rules_recommendation_wf.py`.
5. Проверить период обучения и число строк в выводе.
6. Запустить `sentiment_to_predict_wf.py`.
7. Проверить `Status`, `Action` и `Предсказанное направление` в созданном файле.
8. Не запускать `trade_*_ebs.py`, если реальная запись `.tri` не требуется.
