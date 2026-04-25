# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Что это

Бэктест-стенд для сравнения локальных LLM (через Ollama) на задаче sentiment-анализа новостей применительно к фьючерсам Московской биржи (RTS, MIX, NG). Это проект-«песочница», отделённый от продового pj18_sentiment, чтобы вносить тестовые изменения, не трогая реальный торговый модуль.

## Запуск

Активировать venv не обязательно — все команды используют интерпретатор напрямую:
```
.venv/Scripts/python.exe <script>
```

Прогон одной модели (4 шага: sentiment_analysis → sentiment_group_stats → rules_recommendation → sentiment_backtest):
```
.venv/Scripts/python.exe rts/gemma3_12b/run_gemma3_12b.py
.venv/Scripts/python.exe rts/gemma3_12b/run_gemma3_12b.py --only sentiment_backtest
```

Прогон всех моделей одного тикера (автоматически находит `<model>/run_<model>.py`):
```
.venv/Scripts/python.exe rts/run_rts.py
.venv/Scripts/python.exe rts/run_rts.py --only gemma3_12b,gemma4_e2b --keep-going
```

Открыть HTML-отчёты бэктеста всех моделей тикера в одном окне Chrome:
```
.venv/Scripts/python.exe rts/html_open.py
```

Для работы Ollama должен быть запущен локально на `http://localhost:11434`, и нужная модель (`sentiment_model` из `settings.yaml`) — установлена.

## Архитектура

**Иерархия:** `<ticker>/<model>/` — каждая комбинация тикер+модель полностью изолирована, имеет свой `settings.yaml`, скрипты и артефакты. Никаких shared-модулей: скрипты модели намеренно самодостаточны, чтобы их можно было править под конкретную модель без эффекта на остальные.

**Тикеры:** `rts/`, `mix/`, `ng/`. Структура внутри идентична с точностью до значений в `settings.yaml` (`ticker`, `ticker_lc`, `ticker_close`, `ticker_open`).

**Модельные папки:** имена вида `gemma3_12b`, `qwen2.5_7b`. Соответствие имени папки ↔ имени модели Ollama: `_` между семейством и размером заменяется на `:` (например `gemma3_12b` → `gemma3:12b`).

**Пайплайн внутри модели** — 4 шага, каждый — отдельный typer-CLI:
1. `sentiment_analysis.py` — читает md-файлы новостей из `md_path` (вне репо), для каждого делает HTTP-запрос к Ollama `/api/generate` с детерминированными параметрами (`temperature=0`, `seed=42`), парсит ответ строго как одно число от -10 до +10, прикрепляет рыночные признаки (`body`, `next_body`) из SQLite БД дневок, сохраняет PKL `sentiment_scores_<model_slug>.pkl`. Поддерживает PKL-чекпоинты (по умолчанию каждые 10 файлов) и кэш по `content_hash` — повторный запуск пропускает неизменённые файлы.
2. `sentiment_group_stats.py` — группирует по значениям sentiment, считает follow-стратегию, пишет XLSX в `group_stats/`.
3. `rules_recommendation.py` — из XLSX генерирует `rules.yaml` рядом со скриптом (правила follow/invert/skip для каждого значения sentiment).
4. `sentiment_backtest.py` — применяет `rules.yaml` к sentiment-данным, считает P/L по `next_body`, генерирует HTML-отчёт (Plotly) и QuantStats tearsheet в `plots/`, XLSX в `backtest/`.

**Оркестраторы:**
- `<ticker>/<model>/run_<model>.py` — последовательно вызывает 4 шага через `subprocess`. Останавливается на первой ошибке.
- `<ticker>/run_<ticker>.py` — обнаруживает `<model>/run_<model>.py` через `iterdir()` и запускает их по очереди. Поддерживает `--only` (фильтр моделей) и `--keep-going` (не останавливаться при падении одной модели).

**Конфиг:** `settings.yaml` в каждой модельной папке — плоский (без секций). Скрипты читают его через `yaml.safe_load` и применяют подстановку `{ticker}`/`{ticker_lc}` в строковых значениях. Ключи внешних путей (`md_path`, `db_news_dir`, `path_db_day`) одинаковы во всех моделях одного тикера.

## Соглашения, которые не очевидны из кода

**Никаких хардкоженных имён тикеров в скриптах.** Скрипты определяют свой тикер/модель через `Path(__file__).resolve().parent` (для модельных скриптов это папка модели, для корневых оркестраторов — папка тикера). При копировании в новую папку-тикер/модель код адаптируется автоматически; правится только `settings.yaml`.

**Плоский YAML — это сознательный выбор.** В исходном pj18_sentiment настройки разнесены по секциям `common`/`sentiment_gemma`/`sentiment_qwen` с merge-логикой. Здесь от этого ушли — каждая папка-модель имеет свой плоский `settings.yaml`, чтобы конфиги моделей не зависели друг от друга.

**При добавлении новой модели для тикера:** скопировать существующую папку-модель, в `settings.yaml` поменять `sentiment_model` (и заголовок-комментарий), переименовать `run_<model>.py`. Корневой оркестратор `run_<ticker>.py` подхватит её автоматически.

**При добавлении нового тикера:** скопировать структуру `rts/` целиком, в каждом `settings.yaml` обновить `ticker`/`ticker_lc`/`ticker_close`/`ticker_open`, переименовать `run_<ticker>.py`. Регулярная замена `rts`→`<new>` опасна: она цепляет английские слова `startswith`, `reports` и т.п. Использовать regex с не-буквенными границами: `(?<![a-zA-Z])rts(?![a-zA-Z])`.

**Артефакты пайплайна:** `*.html`, `*.xlsx`, `*.pkl`, `plots/`, `log/`, `backtest/`, `group_stats/` — в `.gitignore`. `rules.yaml` коммитится (это конфиг, а не артефакт), хотя и генерируется `rules_recommendation.py`.

**Внешние пути в settings.yaml** указывают на машину разработчика (`C:/Users/Alkor/gd/...`) — md-файлы новостей и SQLite-базы котировок лежат вне репозитория и не версионируются.
