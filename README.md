# pj19_sentiment_test_model
Для тестирования локальных больших языковых моделей на задаче sentiment-анализа новостей для фьючерсов Московской биржи.

## Дополнительные утилиты

- `buhinvest_analize/` — построение PNG/HTML-отчётов по Excel-выгрузке Buhinvest.
- `beget/` — синхронизация RSS SQLite-баз с удалённого сервера; `beget/server/` хранится как копия серверных RSS-скраперов и локально не запускается.
- `trade/` — QUIK trade-скрипты, адаптированные к конфигам этого проекта. Runtime-файлы `log/`, `state/`, `quik_export/*.csv/json/tmp` не версионируются.
- `<ticker>/settings.yaml` — единый секционный конфиг тикера для `shared`, всех моделей и `combine`.
- `<ticker>/shared/` — общие скрипты подготовки данных: минутки MOEX, дневные свечи и markdown-файлы новостей.

Запускать скрипты из этого проекта можно тем же интерпретатором:

```powershell
.venv/Scripts/python.exe buhinvest_analize/pl_buhinvest_interactive.py
.venv/Scripts/python.exe beget/check_rss_db.py
.venv/Scripts/python.exe rts/shared/create_markdown_files.py
```

`trade/trade_mix_ebs.py` и `trade/trade_rts_ebs.py` работают с секцией `accounts.ebs` в `trade/settings.yaml`: оттуда берут торговый счёт, путь к `.tri`, объём и `predict_dir`. Активные контракты `ticker_open`/`ticker_close` читаются напрямую из секции `common` файла `<ticker>/settings.yaml`. Сам торговый сигнал берётся только из `<predict_dir>/YYYY-MM-DD.txt` по строке `Предсказанное направление: up/down/skip`; поэтому источник сигнала меняется настройкой `predict_dir`, без правки Python-кода. Lua-экспорт QUIK пишет файлы в `trade/quik_export/`.
