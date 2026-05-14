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

## Логика

Для каждой тестовой даты `D` правила строятся на окне `D - train_months` .. `D - 1 день`.
Тестовый день и более поздние даты в обучение не попадают.

## Артефакты

- `walk_forward/results/summary.csv`
- `walk_forward/results/summary.xlsx`
- `walk_forward/results/<TICKER>/<model>/trades.csv`
- `walk_forward/results/<TICKER>/<model>/trades.xlsx`
- `walk_forward/results/<TICKER>/<model>/summary.json`

При `save_daily_artifacts: true` дополнительно пишутся дневные `group_stats.xlsx` и `rules.yaml`.
