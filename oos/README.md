# OOS Backtest

Leave-one-month-out OOS-проверка строит правила на всех месяцах, кроме тестового,
и применяет их только к тестовому месяцу. Рабочие модельные папки при этом не
изменяются: `sentiment_scores.pkl` только читается, все артефакты пишутся в
`oos/results/`.

Пример запуска одной модели:

```powershell
.venv\Scripts\python.exe -m oos.run_oos --tickers rts --models gemma3_12b --start-month 2025-10 --end-month 2025-12
```

Пример запуска всех тикеров и моделей с октября 2025 до конца доступных данных:

```powershell
.venv\Scripts\python.exe -m oos.run_oos --start-month 2025-10
```

Для каждого `ticker/model/month` создаются:

- `group_stats.xlsx` — статистика follow-стратегии на обучающей части;
- `rules.yaml` — правила, построенные без тестового месяца;
- `backtest.xlsx` — сделки за тестовый месяц;
- `summary.json` — краткие метрики месяца.

Сводные файлы:

- `oos/results/summary.csv`
- `oos/results/summary.xlsx`

## Отчет

После OOS-прогона можно собрать HTML dashboard и Excel workbook:

```powershell
.venv\Scripts\python.exe -m oos.report
```

Генератор читает `oos/results/summary.csv` и создает:

- `oos/results/oos_report.html` — основная страница с общими метриками,
  leaderboard, месячной heatmap, блоками по тикерам и списком ошибок;
- `oos/results/oos_report.xlsx` — рабочая книга с листами `Dashboard`,
  `Leaderboard`, `Monthly_Matrix`, листами по тикерам, `Raw_Summary` и `Errors`.
