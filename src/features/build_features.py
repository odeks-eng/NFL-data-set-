"""Feature engineering on top of a merged player-week table.

Every feature that will be used to *predict* a week's outcome is built so it
only uses information available before that week's kickoff:
  - Rolling/expanding usage & efficiency stats are shifted by one game within
    a player-season (week N's feature uses weeks < N only).
  - Opponent-defense context is the opponent's own rolling defensive EPA
    allowed through the prior week, not including the game being predicted.
  - Context features that are legitimately known pre-kickoff (rest days,
    roof/surface, temp/wind, injury/depth-chart status, market lines) are
    used as-is -- they describe the upcoming game, not its outcome.

build_features(seasons, merged_df) is reused by src/predict/live_predict.py
for a single current season; main() below is the historical research path
(config.SEASONS, reading/writing data/processed/player_week_*.parquet).

Run: python -m src.features.build_features
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import PROCESSED_DIR, RAW_DIR, SEASONS  # noqa: E402


def load_pbp(seasons: list[int]) -> pd.DataFrame:
    frames = [pd.read_parquet(RAW_DIR / f"pbp_{s}.parquet") for s in seasons]
    return pd.concat(frames, ignore_index=True)


def build_team_week_context(pbp: pd.DataFrame) -> pd.DataFrame:
    live = pbp[pbp["play_type"].isin(["pass", "run"])].copy()
    grp = live.groupby(["posteam", "season", "week"])
    ctx = grp.agg(
        team_plays=("play_type", "size"),
        team_pass_plays=("play_type", lambda s: (s == "pass").sum()),
        team_off_epa_per_play=("epa", "mean"),
    ).reset_index()
    ctx["team_pass_rate"] = ctx["team_pass_plays"] / ctx["team_plays"]
    return ctx.rename(columns={"posteam": "team"})


def build_position_lookup(seasons: list[int]) -> pd.DataFrame:
    """gsis_id+season -> WR/TE/RB/other, from weekly rosters. Used to find
    *who* a defense's pass plays were thrown at, not just how many EPA they
    allowed in aggregate."""
    frames = []
    for s in seasons:
        wr = pd.read_parquet(RAW_DIR / f"weekly_rosters_{s}.parquet")
        frames.append(wr[["season", "gsis_id", "position"]].dropna(subset=["gsis_id"]))
    lookup = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["season", "gsis_id"])
    lookup["position_group"] = np.where(
        lookup["position"].isin(["WR", "TE", "RB"]), lookup["position"], "OTHER"
    )
    return lookup[["season", "gsis_id", "position_group"]]


def build_defense_week_context_by_target_position(pbp: pd.DataFrame, position_lookup: pd.DataFrame) -> pd.DataFrame:
    """Same idea as build_defense_week_context, but split by the position
    of the targeted receiver -- an aggregate 'pass defense EPA allowed'
    can't tell you a defense is soft against TEs and tough against WRs;
    this can."""
    passes = pbp[pbp["play_type"] == "pass"].dropna(subset=["receiver_player_id"]).copy()
    passes = passes.merge(
        position_lookup, left_on=["season", "receiver_player_id"], right_on=["season", "gsis_id"], how="left"
    )
    passes["position_group"] = passes["position_group"].fillna("OTHER")

    ctx = (
        passes.groupby(["defteam", "season", "week", "position_group"])["epa"]
        .agg(def_epa_allowed_to_position="mean", def_plays_faced_at_position="size")
        .reset_index()
    )
    return ctx.rename(columns={"defteam": "team"})


def build_defense_week_context(pbp: pd.DataFrame) -> pd.DataFrame:
    live = pbp[pbp["play_type"].isin(["pass", "run"])].copy()
    pass_epa = (
        live[live["play_type"] == "pass"].groupby(["defteam", "season", "week"])["epa"]
        .mean().rename("def_pass_epa_allowed")
    )
    rush_epa = (
        live[live["play_type"] == "run"].groupby(["defteam", "season", "week"])["epa"]
        .mean().rename("def_rush_epa_allowed")
    )
    plays_faced = live.groupby(["defteam", "season", "week"]).size().rename("def_plays_faced")
    ctx = pd.concat([pass_epa, rush_epa, plays_faced], axis=1).reset_index()
    return ctx.rename(columns={"defteam": "team"})


def add_causal_rolling(ctx: pd.DataFrame, group_cols: list[str] | str, cols: list[str]) -> pd.DataFrame:
    """Shift-then-roll so week N's context uses weeks < N only, within a season."""
    if isinstance(group_cols, str):
        group_cols = [group_cols]
    ctx = ctx.sort_values([*group_cols, "season", "week"]).reset_index(drop=True)
    for col in cols:
        g = ctx.groupby([*group_cols, "season"])[col]
        ctx[f"{col}_pre"] = g.transform(lambda s: s.shift(1).expanding(min_periods=1).mean())
    return ctx


def build_redzone_usage(pbp: pd.DataFrame) -> pd.DataFrame:
    rz = pbp[(pbp["yardline_100"] <= 20) & pbp["play_type"].isin(["pass", "run"])].copy()

    targets = (
        rz[rz["play_type"] == "pass"]
        .dropna(subset=["receiver_player_id"])
        .groupby(["receiver_player_id", "season", "week"])
        .size()
        .rename("rz_targets")
        .reset_index()
        .rename(columns={"receiver_player_id": "gsis_id"})
    )
    carries = (
        rz[rz["play_type"] == "run"]
        .dropna(subset=["rusher_player_id"])
        .groupby(["rusher_player_id", "season", "week"])
        .size()
        .rename("rz_carries")
        .reset_index()
        .rename(columns={"rusher_player_id": "gsis_id"})
    )
    usage = targets.merge(carries, on=["gsis_id", "season", "week"], how="outer").fillna(
        {"rz_targets": 0, "rz_carries": 0}
    )

    team_rz_pass = (
        rz[rz["play_type"] == "pass"].groupby(["posteam", "season", "week"]).size().rename("team_rz_pass_attempts")
    ).reset_index()
    team_rz_rush = (
        rz[rz["play_type"] == "run"].groupby(["posteam", "season", "week"]).size().rename("team_rz_rush_attempts")
    ).reset_index()

    return usage, team_rz_pass.rename(columns={"posteam": "team"}), team_rz_rush.rename(columns={"posteam": "team"})


ROLLING_METRICS = [
    "target_share", "air_yards_share", "wopr", "offense_pct", "routes_run_proxy",
    "target_per_route", "yards_per_route_run", "receiving_epa", "rushing_epa", "passing_epa",
    "ngs_rec_avg_separation", "ngs_rush_rush_yards_over_expected_per_att", "ngs_pass_completion_percentage_above_expectation",
    "rz_target_share", "rz_carry_share", "fantasy_points_ppr",
]


def add_player_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["gsis_id", "season", "week"]).reset_index(drop=True)
    for col in ROLLING_METRICS:
        if col not in df.columns:
            continue
        g = df.groupby(["gsis_id", "season"])[col]
        df[f"{col}_r3"] = g.transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
        df[f"{col}_r5"] = g.transform(lambda s: s.shift(1).rolling(5, min_periods=1).mean())
        df[f"{col}_std_dev_pre"] = g.transform(lambda s: s.shift(1).rolling(5, min_periods=2).std())
        df[f"{col}_season_pre"] = g.transform(lambda s: s.shift(1).expanding(min_periods=1).mean())
    return df


def build_features(seasons: list[int], merged_df: pd.DataFrame) -> pd.DataFrame:
    df = merged_df
    pbp = load_pbp(seasons)

    print("Building team offensive context (pace, pass rate, EPA/play)...")
    team_ctx = build_team_week_context(pbp)
    team_ctx = add_causal_rolling(team_ctx, "team", ["team_pass_rate", "team_off_epa_per_play", "team_plays"])

    print("Building opponent defensive context (EPA allowed, causal)...")
    def_ctx = build_defense_week_context(pbp)
    def_ctx = add_causal_rolling(def_ctx, "team", ["def_pass_epa_allowed", "def_rush_epa_allowed"])

    print("Building position-specific opponent defensive context (EPA allowed by WR/TE/RB target)...")
    position_lookup = build_position_lookup(seasons)
    def_ctx_pos = build_defense_week_context_by_target_position(pbp, position_lookup)
    def_ctx_pos = add_causal_rolling(def_ctx_pos, ["team", "position_group"], ["def_epa_allowed_to_position"])

    print("Building red zone usage shares...")
    rz_usage, team_rz_pass, team_rz_rush = build_redzone_usage(pbp)

    # Attach team's own pre-game rolling context (this game's team is known before kickoff)
    team_ctx = team_ctx.rename(columns={"team": "recent_team"})
    df = df.merge(
        team_ctx[["recent_team", "season", "week", "team_pass_rate_pre", "team_off_epa_per_play_pre", "team_plays_pre"]],
        on=["recent_team", "season", "week"], how="left",
    )

    # Attach OPPONENT's pre-game rolling defensive context -- this is the matchup signal
    opp_ctx = def_ctx[["team", "season", "week", "def_pass_epa_allowed_pre", "def_rush_epa_allowed_pre"]].rename(
        columns={"team": "opponent_team"}
    )
    df = df.merge(opp_ctx, on=["opponent_team", "season", "week"], how="left")

    # Position-specific matchup signal: for a WR, this is the opponent's rolling
    # EPA allowed specifically on throws to WRs (not TEs, not RBs, not the
    # team's pass defense in aggregate). Only meaningful for WR/TE/RB.
    df["position_group"] = np.where(df["position"].isin(["WR", "TE", "RB"]), df["position"], "OTHER")
    opp_ctx_pos = def_ctx_pos[["team", "season", "week", "position_group", "def_epa_allowed_to_position_pre"]].rename(
        columns={"team": "opponent_team"}
    )
    df = df.merge(opp_ctx_pos, on=["opponent_team", "season", "week", "position_group"], how="left")
    df = df.drop(columns=["position_group"])

    # Red zone shares (this week's actual usage -- will be rolled below, not used raw as a predictor)
    df = df.merge(rz_usage, on=["gsis_id", "season", "week"], how="left")
    df[["rz_targets", "rz_carries"]] = df[["rz_targets", "rz_carries"]].fillna(0)
    df = df.merge(team_rz_pass.rename(columns={"team": "recent_team"}), on=["recent_team", "season", "week"], how="left")
    df = df.merge(team_rz_rush.rename(columns={"team": "recent_team"}), on=["recent_team", "season", "week"], how="left")
    df["rz_target_share"] = (df["rz_targets"] / df["team_rz_pass_attempts"]).replace([np.inf, -np.inf], np.nan)
    df["rz_carry_share"] = (df["rz_carries"] / df["team_rz_rush_attempts"]).replace([np.inf, -np.inf], np.nan)

    # Route efficiency (free-data proxy route count as denominator)
    df["target_per_route"] = (df["targets"] / df["routes_run_proxy"]).replace([np.inf, -np.inf], np.nan)
    df["yards_per_route_run"] = (df["receiving_yards"] / df["routes_run_proxy"]).replace([np.inf, -np.inf], np.nan)

    print("Building causal rolling windows for player usage/efficiency metrics...")
    df = add_player_rolling_features(df)
    return df


def main() -> None:
    merged = pd.read_parquet(PROCESSED_DIR / "player_week_merged.parquet")
    print(f"Loaded merged table: {merged.shape}")

    df = build_features(SEASONS, merged)

    out_path = PROCESSED_DIR / "player_week_features.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df)} rows x {len(df.columns)} cols to {out_path}")


if __name__ == "__main__":
    main()
