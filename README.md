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
| Multivariate model results (CV, holdout, permutation importance) | `data/processed/model_summary.csv`, `model_cv_*.csv`, `model_importance_*.csv` |
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
python -m src.signals.model              # -> multivariate GBM model, data/processed/model_*.csv
```

`src/config.py` controls the season range and the train/holdout split used
in signal testing.

## Forward-looking predictions (current season)

```bash
python -m src.predict.pull_current_season 2026   # refresh this season's raw data
python -m src.predict.live_predict 2026           # auto-detects the next unplayed week
```

This reuses the exact same merge/feature/model code as the historical
pipeline above, just pointed at the current, in-progress season instead of
a historical holdout. Output: `data/processed/predictions_<season>_week<N>.csv`
(predicted receiving yards, rushing yards, and RB PPR fantasy points per
active skill-position player). Read the caveats it prints before using the
numbers -- early in a season there's very little in-season data to build
rolling features from, and a couple of sources (route-participation data,
this season's depth charts under nflverse's new schema) aren't available
yet. Full detail on what's used, what's skipped, and why in
`reports/report.md`.

### Automatic weekly refresh

`.github/workflows/weekly-predictions.yml` runs the two commands above on
GitHub's own schedule (Wednesdays, no laptop or chat session needs to stay
open) and opens a pull request with the refreshed predictions CSV if
anything changed -- nothing lands in the repo without a human merging it.

GitHub only starts firing a `schedule` trigger once the workflow file is on
the repository's **default branch**, so this stays dormant until PR #1 is
merged into `main`. Until then, it can be run manually from the repo's
Actions tab (`Run workflow`, the `workflow_dispatch` trigger) on this
branch to test it. If the auto-PR step ever fails with a permissions error
after merging, check Settings -> Actions -> General -> "Allow GitHub
Actions to create pull requests" is enabled -- that's a separate repo
setting from the workflow's own permissions block.

## Headline findings

Snap share and target share (rolling 3-game / season-to-date) are the
strongest and most stable single signals in this dataset for predicting
next-week receiving yards / fantasy points. Two hand-built blends beat
every single input they were built from, out-of-sample: **snap share ×
rush yards over expected per attempt** (RB rushing yards) and **route
participation × targets-per-route** (WR/TE receiving yards, though this one
rides on a free-data route proxy — see caveats).

A multivariate gradient-boosted model combining all 78 pre-kickoff features
beats every single feature and hand-built blend out-of-sample on all three
targets tested — most clearly for RB rushing yards (holdout r = 0.577 vs.
0.515 for the best 2-feature blend) — and surfaces one signal the simpler
tests couldn't: **draft capital (`draft_pick_overall`)** ranks as a top-3
predictor in every model, even after controlling for current usage.

Full ranked results, including the blends and single features that
*didn't* help, are in [`reports/report.md`](reports/report.md).
