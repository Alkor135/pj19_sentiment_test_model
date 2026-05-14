# Walk-Forward Backtest Design

## Goal

Add a daily walk-forward backtest that compares existing ticker/model sentiment signals without changing working model scripts or overwriting their artifacts.

The new workflow must read existing `sentiment_scores.pkl` files and write every generated artifact under `walk_forward/results/`.

## Scope

Included:

- New isolated `walk_forward/` package.
- Daily rolling walk-forward evaluation.
- Configuration in `walk_forward/settings.yaml`.
- CLI runner for selected tickers and models.
- Summary and per-model trade outputs.
- Optional diagnostic daily artifacts controlled by config.
- Tests for date windows, isolation, rule generation, and result output.

Excluded:

- Running Ollama sentiment analysis.
- Modifying ticker/model `run_report.py`, `rules_recommendation.py`, `sentiment_backtest.py`, or generated artifacts in model folders.
- Writing predictions for live trading.
- Changing the existing `oos/` methodology.

## Configuration

Default `walk_forward/settings.yaml`:

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

Rules:

- `models: []` means discover all models from each ticker's `settings.yaml`.
- `backtest_end_date: null` means use the last available date in the loaded sentiment PKL.
- `train_months` defines the rolling training lookback for each tested day.
- `save_daily_artifacts: false` keeps output compact by default.

## Architecture

Create these files:

- `walk_forward/__init__.py`
- `walk_forward/settings.yaml`
- `walk_forward/core.py`
- `walk_forward/run_walk_forward.py`
- `walk_forward/README.md`

Optional follow-up:

- `walk_forward/report.py` for an HTML/XLSX dashboard after the core runner is stable.

The implementation should reuse or mirror pure logic from `oos/core.py` where appropriate:

- sentiment PKL normalization;
- follow-trade grouping by sentiment;
- rule recommendation;
- rule matching;
- backtest row construction.

The new package should not import or execute model-folder scripts because those scripts write into working artifact directories.

## Algorithm

For each selected `ticker/model`:

1. Load ticker/model settings using the same merge behavior as the current OOS runner.
2. Resolve and read `sentiment_output_pkl`.
3. Normalize to a date-indexed frame with `sentiment` and `next_body`.
4. Build the list of test dates from `backtest_start_date` through `backtest_end_date` or the last available PKL date.
5. For each test date `D`:
   - training start = `D - train_months`;
   - training end = `D - 1 day`;
   - training frame = rows from training start through training end;
   - test frame = row for `D`;
   - skip or record an error if training rows are below `min_train_rows`;
   - build group stats from training frame;
   - build rules from group stats;
   - apply rules to the single test day;
   - append the resulting trade or skip status to the per-model result.
6. Save per-model trades and a global summary.

The training window must never include the test day or any later date.

## Output Layout

Always write:

```text
walk_forward/results/summary.csv
walk_forward/results/summary.xlsx
walk_forward/results/<TICKER>/<model>/trades.xlsx
walk_forward/results/<TICKER>/<model>/trades.csv
walk_forward/results/<TICKER>/<model>/summary.json
```

When `save_daily_artifacts: true`, additionally write:

```text
walk_forward/results/<TICKER>/<model>/daily/YYYY-MM-DD/group_stats.xlsx
walk_forward/results/<TICKER>/<model>/daily/YYYY-MM-DD/rules.yaml
```

No files should be written to `<ticker>/<model>/`, `backtest/`, `group_stats/`, `plots/`, or existing `oos/results/`.

## CLI

Primary command:

```powershell
.venv\Scripts\python.exe -m walk_forward.run_walk_forward
```

Useful overrides:

```powershell
.venv\Scripts\python.exe -m walk_forward.run_walk_forward --tickers rts --models gemma3_12b --start-date 2025-04-01 --train-months 6
```

CLI options should override `walk_forward/settings.yaml`.

## Error Handling

With `keep_going: true`, errors for a single ticker/model/date are recorded in summary output and the runner continues.

Expected recoverable errors:

- missing PKL;
- no test row for a date;
- insufficient training rows;
- all training `total_pnl` values are zero and rules cannot be inferred;
- generated rules produce no trade for the test date.

With `keep_going: false`, the first error exits with a non-zero status.

## Tests

Add focused tests under `tests/`:

- training window excludes test day and future dates;
- `train_months: 6` selects the correct rolling lookback;
- result writing stays inside a provided temporary output directory;
- `save_daily_artifacts: false` does not create daily rules or group stats;
- CLI/settings merge respects overrides;
- summary rows distinguish ok, skipped, and error statuses.

## Acceptance Criteria

- Running the walk-forward CLI does not modify existing model folders.
- Default config uses `backtest_start_date: "2025-04-01"`, `train_months: 6`, and `save_daily_artifacts: false`.
- For each tested day, rules are generated only from data before that day.
- Summary and per-model outputs are written only under `walk_forward/results/`.
- Tests cover the rolling-window behavior and artifact isolation.
