# pj19_sentiment_test_model
Для тестирования больших языковых моделей (локальных), по определению настроения ранка для нескольких фьючерсов мосбиржи. 

## Дополнительные утилиты

- `buhinvest_analize/` — построение PNG/HTML-отчётов по Excel-выгрузке Buhinvest.
- `beget/` — синхронизация RSS SQLite-баз с удалённого сервера; `beget/server/` хранится как копия серверных RSS-скраперов и локально не запускается.
- `trade/` — копия QUIK trade-скриптов из `pj18_sentiment/trade`, адаптированная к конфигам этого проекта. Runtime-файлы `log/`, `state/`, `quik_export/*.csv/json/tmp` не версионируются.
- `<ticker>/settings.yaml` — единый секционный конфиг тикера для `shared`, всех моделей и `combine`.
- `<ticker>/shared/` — общие скрипты подготовки данных: минутки MOEX, дневные свечи и markdown-файлы новостей.

Запускать скрипты из этого проекта можно тем же интерпретатором:

```powershell
.venv/Scripts/python.exe buhinvest_analize/pl_buhinvest_interactive.py
.venv/Scripts/python.exe beget/check_rss_db.py
.venv/Scripts/python.exe rts/shared/create_markdown_files.py
```

`trade/` читает торговые лимиты и QUIK-пути из `trade/settings.yaml`, а прогнозные пути и активные контракты — из `<ticker>/settings.yaml` через `<ticker>/config_loader.py`. Lua-экспорт QUIK пишет файлы в `trade/quik_export/`.
