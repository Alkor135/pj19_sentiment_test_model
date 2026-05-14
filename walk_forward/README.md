# Walk-Forward Backtest

Дневной walk-forward бэктест читает готовые `sentiment_scores.pkl` из модельных настроек тикеров и пишет результаты только в `walk_forward/results/`.

## Запуск

```powershell
.venv\Scripts\python.exe -m walk_forward.run_walk_forward
```

Одна модель:

```powershell
.venv\Scripts\python.exe -m walk_forward.run_walk_forward --tickers rts --models gemma3_12b --start-date 2025-04-01 --train-months 6
```

Собрать Excel и HTML отчёты по уже созданным результатам:

```powershell
.venv\Scripts\python.exe -m walk_forward.report
```

## Логика

Для каждой тестовой даты `D` правила строятся на окне `D - train_months` .. `D - 1 день`.
Тестовый день и более поздние даты в обучение не попадают.

## Артефакты

- `walk_forward/results/summary.csv`
- `walk_forward/results/summary.xlsx`
- `walk_forward/results/<TICKER>/<model>/trades.csv`
- `walk_forward/results/<TICKER>/<model>/trades.xlsx`
- `walk_forward/results/<TICKER>/<model>/summary.json`
- `walk_forward/results/walk_forward_report.xlsx`
- `walk_forward/results/walk_forward_report.html`

При `save_daily_artifacts: true` дополнительно пишутся дневные `group_stats.xlsx` и `rules.yaml`.
