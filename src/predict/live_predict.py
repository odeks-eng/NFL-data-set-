"""Predict an upcoming week's skill-position outcomes.

This is the forward-looking counterpart to the historical backtest: same
merge logic (src/build_player_week.py), same feature engineering
(src/features/build_features.py), same model architecture and predictor
set (src/signals/model.py) -- just pointed at the current season's
not-yet-played week instead of a historical holdout.

The production model is retrained on ALL of 2021-2024 (no holdout reserved
-- the holdout's job was validating the architecture in reports/report.md,
already done). It is deliberately NOT retrained on 2025/2026 box scores,
because the official weekly stats file isn't published for those seasons
yet in this environment (see docs/source_inventory.md) and mixing in a
pbp-derived approximation of the *training* target risks subtly biasing
the model. The pbp-derived approximation (src/predict/pbp_weekly_stats.py)
is only used to build this season's *own* rolling context (what a real
player_stats file would have given us), not to expand training data.

Caveats printed at the end of every run -- read them, this is directional,
not gospel, especially early in a season with only 1-2 games of context.

Run: python -m src.predict.live_predict 2026        # auto-detects next unplayed week
Run: python -m src.predict.live_predict 2026 3       # predict a specific week
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import PROCESSED_DIR, RAW_DIR, SEASONS  # noqa: E402
from src.build_player_week import run_pipeline  # noqa: E402
from src.features.build_features import build_features  # noqa: E402
from src.predict.pbp_weekly_stats import compute_weekly_stats_from_pbp  # noqa: E402
from src.signals.model import MODEL_SPECS, get_predictor_cols, train_final_model  # noqa: E402

SKILL_POSITIONS = ["QB", "RB", "WR", "TE"]


def find_target_week(season: int) -> int:
    sched = pd.read_parquet(RAW_DIR / "schedules.parquet")
    sched = sched[(sched["season"] == season) & (sched["game_type"] == "REG")]
    unplayed = sched[sched["result"].isna()]
    if unplayed.empty:
        raise ValueError(f"No unplayed regular-season games found for {season} -- season may be over.")
    return int(unplayed["week"].min())


def build_current_season_backbone(season: int, target_week: int) -> pd.DataFrame:
    pbp = pd.read_parquet(RAW_DIR / f"pbp_{season}.parquet")
    completed = compute_weekly_stats_from_pbp(pbp[pbp["week"] < target_week])
    print(f"  derived {len(completed)} player-weeks from play-by-play for weeks < {target_week}")

    # Shell rows for the target week: one per active roster player at a
    # skill position, with every box-score column unknown (NaN) since the
    # game hasn't happened. This gives the merge/feature pipeline a row to
    # attach pre-game context to.
    roster = pd.read_parquet(RAW_DIR / f"weekly_rosters_{season}.parquet")
    roster_week = roster[roster["week"] == target_week]
    if roster_week.empty:  # fall back to the most recent published roster snapshot
        roster_week = roster[roster["week"] == roster["week"].max()]
    roster_week = roster_week[roster_week["position"].isin(SKILL_POSITIONS)]
    roster_week = roster_week.dropna(subset=["gsis_id"]).drop_duplicates(subset=["gsis_id"])

    sched = pd.read_parquet(RAW_DIR / "schedules.parquet")
    games = sched[(sched["season"] == season) & (sched["week"] == target_week)]
    team_opponent = pd.concat([
        games[["home_team", "away_team"]].rename(columns={"home_team": "recent_team", "away_team": "opponent_team"}),
        games[["away_team", "home_team"]].rename(columns={"away_team": "recent_team", "home_team": "opponent_team"}),
    ])

    shell = roster_week[["gsis_id", "position", "team"]].rename(columns={"team": "recent_team"}).merge(
        team_opponent, on="recent_team", how="inner"
    )
    shell["season"] = season
    shell["week"] = target_week
    shell["season_type"] = "REG"
    print(f"  built {len(shell)} shell rows for week {target_week} (active roster x that week's matchup)")

    # position isn't part of compute_weekly_stats_from_pbp's output -- attach
    # it (and overwrite team, which the shell rows already carry) for the
    # completed weeks too, via the same weekly-roster snapshot.
    pos_lookup = roster[["gsis_id", "week", "position"]].dropna(subset=["gsis_id"]).drop_duplicates(
        subset=["gsis_id", "week"]
    )
    completed = completed.merge(pos_lookup, on=["gsis_id", "week"], how="left")
    completed = completed[completed["position"].isin(SKILL_POSITIONS)]

    backbone = pd.concat([completed, shell], ignore_index=True)
    return backbone


def main() -> None:
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    target_week = int(sys.argv[2]) if len(sys.argv) > 2 else find_target_week(season)
    print(f"Predicting season {season}, week {target_week}\n")

    print("Building this season's backbone from play-by-play (no official player_stats file yet)...")
    backbone = build_current_season_backbone(season, target_week)

    print("\nRunning the merge pipeline for the current season...")
    merged = run_pipeline(seasons=[season], backbone=backbone)

    print("\nRunning feature engineering for the current season...")
    features = build_features([season], merged)

    target_rows = features[(features["season"] == season) & (features["week"] == target_week)].copy()
    roster = pd.read_parquet(RAW_DIR / f"weekly_rosters_{season}.parquet")
    names = roster[["gsis_id", "full_name"]].dropna(subset=["gsis_id"]).drop_duplicates(subset=["gsis_id"])
    target_rows = target_rows.merge(names, on="gsis_id", how="left").rename(columns={"full_name": "player_name"})
    print(f"\n{len(target_rows)} players to score for week {target_week}")

    print("\nLoading historical (2021-2024) feature table to train the production model...")
    hist = pd.read_parquet(PROCESSED_DIR / "player_week_features.parquet")
    hist = hist[hist["season_type"] == "REG"]
    predictor_cols = get_predictor_cols(hist)

    all_predictions = []
    for spec in MODEL_SPECS:
        print(f"\nTraining production model: {spec['name']} (all of {SEASONS}, no holdout)...")
        model, used_cols = train_final_model(hist, spec, predictor_cols, seasons=SEASONS)

        rows = target_rows[target_rows["position"].isin(spec["positions"])].copy()
        if rows.empty:
            continue
        for c in used_cols:
            if c not in rows.columns:
                rows[c] = pd.NA
        X = rows[used_cols].copy()
        for c in ["roof", "surface", "report_status", "practice_status", "depth_position"]:
            if c in X.columns:
                X[c] = X[c].astype("object").fillna("__missing__").astype("category")
        rows[f"predicted_{spec['target']}"] = model.predict(X)
        rows["model"] = spec["name"]
        all_predictions.append(
            rows[["gsis_id", "player_name", "recent_team", "opponent_team", "position", "model",
                  f"predicted_{spec['target']}"]]
        )

    out = pd.concat(all_predictions, ignore_index=True) if all_predictions else pd.DataFrame()
    out_path = PROCESSED_DIR / f"predictions_{season}_week{target_week}.csv"
    out.to_csv(out_path, index=False)
    print(f"\nWrote {len(out)} predictions to {out_path}")

    print("\n" + "=" * 70)
    print("CAVEATS -- read before using these:")
    print(f"  - Only {target_week - 1} game(s) of {season} season context exist. Every rolling")
    print("    feature is based on that tiny sample -- treat early-season predictions as")
    print("    rough, not final, regardless of what the model outputs.")
    print("  - routes_run_proxy is null this season (pbp_participation not yet published),")
    print("    so any feature derived from it (target_per_route, yards_per_route_run) is")
    print("    also null and contributes nothing this week.")
    print("  - The model was trained on 2021-2024 box scores only, not retrained on any")
    print("    pbp-derived approximation of 2025/2026 -- see the module docstring for why.")
    print("=" * 70)


if __name__ == "__main__":
    main()
