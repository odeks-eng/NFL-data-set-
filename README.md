# NFL Player Analytics Dataset

Player-level NFL analytics pipeline: pulls weekly stats, Next Gen Stats,
snap counts, injuries, depth charts, play-by-play-derived context, and
market/schedule data from free/open sources, merges everything into one
player-week table, engineers usage/efficiency/context features with no
lookahead leakage, and signal-tests them (single features and blends)
out-of-sample.

## Deliverables

| What | Where |
|---|---|
| Source inventory (what was pulled, from where, coverage, cost, reliability) | [`docs/source_inventory.md`](docs/source_inventory.md) |
| Data dictionary for the merged/feature dataset | [`docs/data_dictionary.md`](docs/data_dictionary.md) |
| Clean merged player-week dataset | [`data/processed/player_week_merged.parquet`](data/processed/player_week_merged.parquet) |
| Feature-engineered dataset (rolling windows, causal) used for signal testing | [`data/processed/player_week_features.parquet`](data/processed/player_week_features.parquet) |
| Join-quality / coverage logs (unmatched records) | `data/processed/join_quality_log.csv`, `feature_coverage.csv` |
| Signal-testing results (single features + blends, out-of-sample) | `data/processed/signal_test_single_features.csv`, `signal_test_blends.csv` |
| Written report: top signals, blends that worked/didn't, known weaknesses, next steps | [`reports/report.md`](reports/report.md) |
| Pipeline code (rerunnable) | `src/` |

## Scope

- Seasons 2021–2024 (regular season for signal testing; postseason merged
  but excluded from rolling-window analysis — see report for why).
- Positions QB/RB/WR/TE.
- Everything pulled is free/open (nflverse's GitHub-hosted mirrors of
  official NFL data, NGS, PFR advanced stats, and historical game odds).
  **No paid source was accessed or subscribed to.** See
  `docs/source_inventory.md` for what paid sources would add and why they
  weren't pulled in this environment.

## Quickstart

```bash
pip install -r requirements.txt
python -m src.ingest.pull_all            # -> data/raw/ (gitignored, ~110MB)
python -m src.build_player_week          # -> data/processed/player_week_merged.parquet
python -m src.features.build_features    # -> data/processed/player_week_features.parquet
python -m src.signals.signal_testing     # -> data/processed/signal_test_*.csv
```

`src/config.py` controls the season range and the train/holdout split used
in signal testing.

## Headline finding

Snap share and target share (rolling 3-game / season-to-date) are the
strongest and most stable single signals in this dataset for predicting
next-week receiving yards / fantasy points. Two blended features beat every
single input they were built from, out-of-sample: **snap share × rush
yards over expected per attempt** (RB rushing yards) and **route
participation × targets-per-route** (WR/TE receiving yards, though this one
rides on a free-data route proxy — see caveats). Full ranked results,
including the blends and single features that *didn't* help, are in
[`reports/report.md`](reports/report.md).
