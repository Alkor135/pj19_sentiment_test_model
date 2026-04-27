# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Что это

Бэктест-стенд для сравнения локальных LLM (через Ollama) на задаче sentiment-анализа новостей применительно к фьючерсам Московской биржи (RTS, MIX, NG, Si, SPYF). Это проект-«песочница», отделённый от продового pj18_sentiment, чтобы вносить тестовые изменения, не трогая реальный торговый модуль.

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

Прогон всех моделей одного тикера (автоматически находит `<model>/run_report.py`, после моделей запускает `combine/sentiment_combine.py` → `combine/sentiment_to_predict.py`):
```
.venv/Scripts/python.exe rts/run_rts.py
.venv/Scripts/python.exe rts/run_rts.py --only gemma3_12b,gemma4_e2b --keep-going
```

Прогон только combine-пайплайна (без перезапуска моделей):
```
.venv/Scripts/python.exe rts/combine/sentiment_combine.py
.venv/Scripts/python.exe rts/combine/sentiment_to_predict.py
```

Открыть HTML-отчёты бэктеста всех моделей тикера в одном окне Chrome (включая `combine/plots/*.html`):
```
.venv/Scripts/python.exe rts/html_open.py
```

Для работы Ollama должен быть запущен локально на `http://localhost:11434`, и нужная модель (`sentiment_model` из `settings.yaml`) — установлена.

## Архитектура

**Иерархия:** `<ticker>/<model>/` — каждая комбинация тикер+модель полностью изолирована, имеет свой `settings.yaml`, скрипты и артефакты. Никаких shared-модулей: скрипты модели намеренно самодостаточны, чтобы их можно было править под конкретную модель без эффекта на остальные.

**Тикеры:** `rts/`, `mix/`, `ng/`, `si/`, `spyf/`. Структура внутри идентична с точностью до значений в `settings.yaml` (`ticker`, `ticker_lc`, `ticker_close`, `ticker_open`).

**Модельные папки:** имена вида `gemma3_12b`, `qwen2.5_7b`. Соответствие имени папки ↔ имени модели Ollama: `_` между семейством и размером заменяется на `:` (например `gemma3_12b` → `gemma3:12b`).

**Пайплайн внутри модели** — 5 шагов, каждый — отдельный typer-CLI:
1. `sentiment_analysis.py` — читает md-файлы новостей из `md_path` (вне репо), для каждого делает HTTP-запрос к Ollama `/api/generate` с детерминированными параметрами (`temperature=0`, `seed=42`), парсит ответ строго как одно число от -10 до +10, прикрепляет рыночные признаки (`body`, `next_body`) из SQLite БД дневок, сохраняет PKL `sentiment_scores.pkl`. Поддерживает PKL-чекпоинты (по умолчанию каждые 10 файлов) и кэш по `content_hash` — повторный запуск пропускает неизменённые файлы.
2. `sentiment_group_stats.py` — группирует по значениям sentiment, считает follow-стратегию, пишет XLSX в `group_stats/`.
3. `rules_recommendation.py` — из XLSX генерирует `rules.yaml` рядом со скриптом (правила follow/invert/skip для каждого значения sentiment).
4. `sentiment_backtest.py` — применяет `rules.yaml` к sentiment-данным, считает P/L по `next_body`, генерирует HTML-отчёт (Plotly) и QuantStats tearsheet в `plots/`, XLSX в `backtest/`.
5. `sentiment_to_predict.py` — на основе `rules.yaml` и записи за сегодня в `sentiment_scores.pkl` пишет прогноз на текущую дату в `predict_path` (`YYYY-MM-DD.txt` со строкой `Предсказанное направление: up/down/skip`). При отсутствии данных направление = `skip`, exit code всегда 0 — сбой одной модели не блокирует пайплайн.

**Combine-пайплайн (`<ticker>/combine/`):** склеивает результаты двух моделей.
- `combine/settings.yaml` — `model_1`, `model_2` (имена папок моделей; допустимы и Ollama-имена с `:`, скрипт нормализует через `replace(":", "_")`), `notional_capital` (для QuantStats), `predict_path` с `{ticker_lc}`.
- `combine/sentiment_combine.py` — берёт `<model>/backtest/sentiment_backtest_results.xlsx` обеих моделей, inner-merge по `source_date`, оставляет только дни с совпадающими `direction` (логика «1 контракт, торгуем по согласию двух моделей»). P/L комбинации = P/L одной модели (при совпадении направления и `quantity_test=1` они равны). Сохраняет `combine/plots/sentiment_combine.html` (Plotly-отчёт по аналогии с `sentiment_backtest.html`, без панелей по action/sentiment) и `combine/plots/sentiment_combine_qs.html` (QuantStats).
- `combine/sentiment_to_predict.py` — читает за сегодня файлы прогнозов обеих моделей из `<predict_path>.parent/<model_folder>/`, вырезает строку `Предсказанное направление: ...` (но запоминает направление как `Направление: up/down/skip` в блоке модели). Финальное направление: `up`+`up` → `up`, `down`+`down` → `down`, иначе → `skip`.

**Оркестраторы:**
- `<ticker>/<model>/run_report.py` — последовательно вызывает 5 шагов через `subprocess`. Останавливается на первой ошибке.
- `<ticker>/run_<ticker>.py` — обнаруживает `<model>/run_report.py` через `iterdir()` и запускает их по очереди, затем (если не указан `--only`) последовательно прогоняет `combine/sentiment_combine.py` и `combine/sentiment_to_predict.py`. Поддерживает `--only` (фильтр моделей; при этом combine пропускается) и `--keep-going` (не останавливаться при падении одной модели или combine-шага).
- `run.py` (корень) — перебирает тикеры, прокидывает `--only` и `--keep-going` дальше.

**Конфиг:** `settings.yaml` в каждой модельной папке — плоский (без секций). Скрипты читают его через `yaml.safe_load` и применяют подстановку `{ticker}`/`{ticker_lc}` в строковых значениях. Ключи внешних путей (`md_path`, `db_news_dir`, `path_db_day`) одинаковы во всех моделях одного тикера.

## Соглашения, которые не очевидны из кода

**Никаких хардкоженных имён тикеров в скриптах.** Скрипты определяют свой тикер/модель через `Path(__file__).resolve().parent` (для модельных скриптов это папка модели, для корневых оркестраторов — папка тикера). При копировании в новую папку-тикер/модель код адаптируется автоматически; правится только `settings.yaml`.

**Плоский YAML — это сознательный выбор.** В исходном pj18_sentiment настройки разнесены по секциям `common`/`sentiment_gemma`/`sentiment_qwen` с merge-логикой. Здесь от этого ушли — каждая папка-модель имеет свой плоский `settings.yaml`, чтобы конфиги моделей не зависели друг от друга.

**При добавлении новой модели для тикера:** скопировать существующую папку-модель, в `settings.yaml` поменять `sentiment_model` (и заголовок-комментарий). Корневой оркестратор `run_<ticker>.py` подхватит её автоматически (ищет `run_report.py` в подпапках).

**При добавлении нового тикера:** скопировать структуру `rts/` целиком (включая `combine/`), в каждом `settings.yaml` обновить `ticker`/`ticker_lc`/`ticker_close`/`ticker_open`, переименовать `run_<ticker>.py`. Папка `combine/` универсальна — внутри нет хардкоженых тикеров, скрипты выводят тикер из `Path(__file__).resolve().parents[1].name`; править нужно только `combine/settings.yaml` (модели и при необходимости `notional_capital`). Регулярная замена `rts`→`<new>` опасна: она цепляет английские слова `startswith`, `reports` и т.п. Использовать regex с не-буквенными границами: `(?<![a-zA-Z])rts(?![a-zA-Z])`.

**Артефакты пайплайна:** `*.html`, `*.xlsx`, `*.pkl`, `plots/`, `log/`, `backtest/`, `group_stats/`, `rules.yaml` — в `.gitignore`. `rules.yaml` генерируется `rules_recommendation.py` и у каждой локальной машины свой (зависит от прогонов sentiment-анализа). У `<ticker>/combine/` те же исключения — `plots/` и `log/` локальные, не коммитятся.

**Внешние пути в settings.yaml** указывают на машину разработчика (`C:/Users/Alkor/gd/...`) — md-файлы новостей и SQLite-базы котировок лежат вне репозитория и не версионируются.
