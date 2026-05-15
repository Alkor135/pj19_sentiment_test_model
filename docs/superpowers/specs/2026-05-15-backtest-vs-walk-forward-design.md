# Backtest vs Walk-Forward Comparison Report

## Goal

Build a separate report that compares ordinary model backtest results from ticker folders with walk-forward results from `walk_forward/results`.

The report must make the equity curves comparable by using only dates that exist in both sources for each ticker/model pair. This avoids showing a walk-forward curve that starts later against a longer ordinary backtest curve.

## Sources

Ordinary backtest source:

`<ticker>/<model>/backtest/sentiment_backtest_results.xlsx`

Walk-forward source:

`walk_forward/results/<WF_TICKER>/<model>/trades.xlsx`

Ticker directory mapping:

| Ticker folder | Walk-forward folder |
| --- | --- |
| `rts` | `RTS` |
| `mix` | `MIX` |
| `ng` | `NG` |
| `si` | `Si` |
| `spyf` | `SPYF` |

## Data Contract

Both sources are expected to contain:

- `source_date`
- `sentiment`
- `action`
- `direction`
- `next_body`
- `quantity`
- `pnl`
- `cum_pnl`

Walk-forward also contains metadata columns such as `ticker`, `model_dir`, `sentiment_model`, `train_start`, `train_end`, and `train_rows`.

The comparison script must ignore source `cum_pnl` and recalculate cumulative P/L from filtered overlap rows so both curves start at zero on the same first comparable date.

## Architecture

Create a new folder:

`compare_backtests/`

Initial files:

- `compare_backtests/__init__.py`
- `compare_backtests/build_report.py`

The CLI script will:

1. Discover ticker/model pairs from `walk_forward/results/<WF_TICKER>/<model>/trades.xlsx`.
2. Resolve the matching ordinary backtest file in `<ticker>/<model>/backtest/sentiment_backtest_results.xlsx`.
3. Skip pairs where either file is missing, while recording the skip in an errors table.
4. Read both XLSX files with pandas.
5. Normalize `source_date` to date values and numeric `pnl`.
6. Keep only dates present in both sources for that pair.
7. Recalculate `cum_pnl` on the overlap subset for both sources.
8. Build summary metrics and an HTML report.

Default output:

`compare_backtests/results/backtest_vs_walk_forward.html`

## Report Layout

The HTML report should contain:

- Header with generation context and count of comparable pairs.
- Summary leaderboard across all pairs.
- One section per ticker.
- For each ticker/model pair:
  - equity curve with two lines: ordinary backtest and walk-forward;
  - optional drawdown comparison based on the recalculated cumulative P/L;
  - compact metrics table.

Recommended metrics:

- overlap date range;
- overlap rows;
- ordinary backtest total P/L on overlap dates;
- walk-forward total P/L on overlap dates;
- delta P/L (`walk_forward - ordinary_backtest`);
- ordinary and walk-forward max drawdown;
- ordinary and walk-forward win rate;
- signal match rate based on matching `action` and `direction`.

## Error Handling

The script should continue when one pair is not usable. It should record:

- missing ordinary backtest file;
- missing walk-forward trades file;
- unreadable XLSX;
- missing required columns;
- no overlapping dates.

The HTML report should include an errors and skipped pairs table at the end.

## CLI

Default command:

```powershell
.venv\Scripts\python.exe -m compare_backtests.build_report
```

Useful options:

- `--walk-results-dir`, default `walk_forward/results`;
- `--output-html`, default `compare_backtests/results/backtest_vs_walk_forward.html`;
- `--tickers`, optional comma-separated ticker folders;
- `--models`, optional comma-separated model folder names;
- `--open-browser`, optional flag for later if needed, but not required for the first version.

The first version should generate only HTML. CSV/XLSX exports can be added later if the comparison report becomes part of a broader analysis workflow.

## Testing

Add focused unit tests for pure helpers:

- ticker folder mapping;
- pair discovery;
- overlap filtering and cumulative P/L recalculation;
- summary metrics, including no-overlap behavior.

Also run a real smoke test against existing local artifacts:

```powershell
.venv\Scripts\python.exe -m compare_backtests.build_report
```

The smoke test must create the default HTML report without running trade scripts or modifying model folders.
