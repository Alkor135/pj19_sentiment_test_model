# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Что это

Бэктест-стенд для сравнения локальных LLM (через Ollama) на задаче sentiment-анализа новостей применительно к фьючерсам Московской биржи (RTS, MIX, NG, SI, SPYF). Это проект-«песочница», отделённый от продового pj18_sentiment, чтобы вносить тестовые изменения, не трогая реальный торговый модуль.

## Запуск

Активировать venv не обязательно — все команды используют интерпретатор напрямую:
```
.venv/Scripts/python.exe <script>
```

Прогон одной модели (4 шага: sentiment_analysis → sentiment_group_stats → rules_recommendation → sentiment_backtest):
```
.venv/Scripts/python.exe rts/gemma3_12b/run_report.py
.venv/Scripts/python.exe rts/gemma3_12b/run_report.py --only sentiment_backtest
```

Прогон всех моделей одного тикера (автоматически находит `<model>/run_report.py`):
```
.venv/Scripts/python.exe rts/run_rts.py
.venv/Scripts/python.exe rts/run_rts.py --only gemma3_12b,gemma4_e2b --keep-going
```

Открыть HTML-отчёты бэктеста всех моделей тикера в одном окне Chrome:
```
.venv/Scripts/python.exe rts/html_open.py
```

Для работы Ollama должен быть запущен локально на `http://localhost:11434`, и нужная модель (`sentiment_model` из конфигурации тикера) — установлена.

В проект также перенесены вспомогательные папки из соседних проектов:
- `buhinvest_analize/` — отчёты по Excel-выгрузке Buhinvest. Путь к Excel задаётся в `buhinvest_analize/settings.yaml`, также его можно переопределить через `--file`.
- `beget/` — локальная синхронизация RSS-баз через WSL/rsync и копия серверных RSS-скраперов. Локальная синхронизация читает `beget/settings.yaml`; `beget/server/` хранится как копия кода, который работает на удалённом сервере, и локально в этом проекте не запускается.
- `trade/` — QUIK trade-скрипты и Lua-экспорт. EBS-скрипты `trade_mix_ebs.py`/`trade_rts_ebs.py` используют `trade/settings.yaml` для QUIK-аккаунта, `.tri`-файла, объёмов и `predict_dir`; активные контракты `ticker_open`/`ticker_close` читают напрямую из секции `common` файла `<ticker>/settings.yaml`.

Примеры:
```
.venv/Scripts/python.exe buhinvest_analize/pl_buhinvest.py
.venv/Scripts/python.exe buhinvest_analize/pl_buhinvest_interactive.py --file C:/Users/Alkor/gd/ВТБ_ЕБС_SPBFUT192yc.xlsx
.venv/Scripts/python.exe beget/check_rss_db.py
.venv/Scripts/python.exe beget/collect_rss_links_to_yaml.py
```

## Архитектура

**Иерархия:** `<ticker>/<model>/` — каждая комбинация тикер+модель имеет свои скрипты и артефакты. Настройки тикера вынесены в единый секционный файл `<ticker>/settings.yaml`; модельные папки, `<ticker>/combine/` и `<ticker>/shared/` локальных `settings.yaml` не содержат.

**Тикеры:** `rts/`, `mix/`, `ng/`, `si/`, `spyf/`. У каждого тикера конфиг лежит в `<ticker>/settings.yaml`.

**Модельные папки:** имена вида `gemma3_12b`, `qwen2.5_7b`. Соответствие имени папки ↔ имени модели Ollama: `_` между семейством и размером заменяется на `:` (например `gemma3_12b` → `gemma3:12b`).

**Отчётный пайплайн внутри модели** — 4 шага, каждый — отдельный typer-CLI:
1. `sentiment_analysis.py` — читает md-файлы новостей из `md_path` (вне репо), для каждого делает HTTP-запрос к Ollama `/api/generate` с детерминированными параметрами (`temperature=0`, `seed=42`), парсит ответ строго как одно число от -10 до +10, прикрепляет рыночные признаки (`body`, `next_body`) из SQLite БД дневок, сохраняет PKL `sentiment_scores.pkl`. Поддерживает PKL-чекпоинты (по умолчанию каждые 10 файлов) и кэш по `content_hash` — повторный запуск пропускает неизменённые файлы.
2. `sentiment_group_stats.py` — группирует по значениям sentiment, считает follow-стратегию, пишет XLSX в `group_stats/`.
3. `rules_recommendation.py` — из XLSX генерирует `rules.yaml` рядом со скриптом (правила follow/invert/skip для каждого значения sentiment).
4. `sentiment_backtest.py` — применяет `rules.yaml` к sentiment-данным, считает P/L по `next_body`, генерирует HTML-отчёт (Plotly) и QuantStats tearsheet в `plots/`, XLSX в `backtest/`.

**Торговый модельный пайплайн** добавляет к этим 4 шагам `sentiment_to_predict.py` — генерацию файла `<predict_path>/YYYY-MM-DD.txt` со строкой `Предсказанное направление: up/down/skip`. Этот шаг входит в `<ticker>/<model>/run_trade.py`, но не входит в `<ticker>/<model>/run_report.py`.

**Оркестраторы:**
- `<ticker>/<model>/run_report.py` — последовательно вызывает 4 шага через `subprocess`. Останавливается на первой ошибке.
- `<ticker>/<model>/run_trade.py` — последовательно вызывает 5 шагов: 4 отчётных шага и `sentiment_to_predict.py`. Используется на основной торговой машине для единого источника прогнозов.
- `<ticker>/run_<ticker>.py` — обнаруживает `<model>/run_report.py` через `iterdir()` и запускает их по очереди, затем при необходимости запускает combine-пайплайн. Поддерживает `--only` (фильтр моделей/`combine`) и `--keep-going` (не останавливаться при падении одной модели).
- `<ticker>/shared/` — общие для тикера утилиты подготовки данных: скачивание минуток MOEX, конвертация минуток в дневки и генерация markdown-файлов новостей. Trade-оркестратор `<ticker>/run_<ticker>_trade.py` всегда запускает эти три shared-скрипта первыми: `download_minutes_to_db.py` → `convert_minutes_to_days.py` → `create_markdown_files.py`.
- `trade/` — локальные скрипты выставления заявок через QUIK `.tri` и Lua-экспорт текущих минуток/позиций. `trade_mix_ebs.py` и `trade_rts_ebs.py` читают прогноз из `predict_dir/YYYY-MM-DD.txt`, приводят позицию счёта `accounts.ebs.trade_account` к целевой и защищаются от повторной записи маркером `trade/state/{ticker}_{trade_account}_{date}.done`. Lua-файлы пишут в `trade/quik_export/`; runtime-файлы `trade/log/`, `trade/state/`, `trade/quik_export/*.csv/json/tmp` игнорируются git.

**Конфиг тикера:** `<ticker>/settings.yaml` — секционный файл с полной картиной настроек тикера. `common` содержит тикерные параметры, активные контракты, внешние пути и единые окна дат `stats_date_from`/`stats_date_to`/`backtest_date_from`/`backtest_date_to`; `shared` — параметры подготовки данных; `model_defaults` — общие настройки моделей; `models` — различия конкретных моделей; `combine` — параметры объединённого сигнала. Модельные/shared/combine-скрипты читают его через `<ticker>/config_loader.py`, который применяет подстановки `{ticker}`, `{ticker_lc}`, `{model_dir}`. EBS trade-скрипты читают `common` напрямую из `<ticker>/settings.yaml`, а торговые параметры — из `trade/settings.yaml`.

## Соглашения, которые не очевидны из кода

**Никаких хардкоженных имён тикеров в модельных/shared/combine-скриптах.** Эти скрипты определяют свой тикер/модель через расположение файла и `<ticker>/config_loader.py`. При копировании в новую модель правится только секция `models` в `<ticker>/settings.yaml`. Исключение — EBS trade-адаптеры `trade_mix_ebs.py`/`trade_rts_ebs.py`: они явно задают `ticker_lc`, потому что привязаны к конкретному тикеру и секции `accounts.ebs` в `trade/settings.yaml`.

**Единый YAML тикера — сознательный выбор.** Настройки больше не дублируются по папкам моделей: при ручном редактировании вся картина тикера видна в одном файле `<ticker>/settings.yaml`.

**При добавлении новой модели:** скопировать существующую папку-модель и добавить запись в секцию `models` файла `<ticker>/settings.yaml` (`sentiment_model` и при необходимости переопределения). Корневой оркестратор `run_<ticker>.py` подхватит её автоматически (ищет `run_report.py` в подпапках).

**При добавлении нового тикера на базе RTS:** скопировать структуру `rts/` целиком, в новом `<ticker>/settings.yaml` обновить `ticker`/`ticker_lc`/`ticker_close`/`ticker_open`, переименовать `run_<ticker>.py`. Регулярная замена `rts`→`<new>` опасна: она цепляет английские слова `startswith`, `reports` и т.п. Использовать regex с не-буквенными границами: `(?<![a-zA-Z])rts(?![a-zA-Z])`.

**Артефакты пайплайна:** `*.html`, `*.xlsx`, `*.pkl`, `plots/`, `log/`, `backtest/`, `group_stats/`, `rules.yaml` — в `.gitignore`. `rules.yaml` генерируется `rules_recommendation.py` и у каждой локальной машины свой (зависит от прогонов sentiment-анализа).

**Внешние пути в settings.yaml** указывают на машину разработчика (`C:/Users/Alkor/gd/...`) — md-файлы новостей и SQLite-базы котировок лежат вне репозитория и не версионируются.

**Buhinvest и Beget тоже завязаны на внешнюю среду.** `buhinvest_analize/settings.yaml` указывает на локальный Excel-файл вне репозитория. `beget/sync_files.py` требует WSL, `rsync` и SSH-доступ к `remote_host`. `beget/server/` не является локальным рантаймом проекта; это копия серверных скриптов и их серверных настроек.

**Trade-скрипты не запускать для проверки без явного запроса.** Они могут писать `.tri` в папку QUIK и рассчитаны на ручной контроль торгового окружения. Для адаптации допустимы безопасные проверки вроде `py_compile` и чтения конфигов; полноценный запуск — только когда пользователь явно просит.
