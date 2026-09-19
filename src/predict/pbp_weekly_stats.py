"""Derive a player_stats-equivalent weekly box-score table directly from
play-by-play, for a season whose official nflverse `player_stats` file
isn't published yet (true for the current, in-progress season).

Mirrors nflverse's own methodology closely enough for this pipeline's
purposes: pass_attempt/rush_attempt/complete_pass/pass_touchdown/
rush_touchdown/interception/epa/air_yards are all official per-play columns
nflverse computes and QAs upstream -- this just aggregates them to
player-week, the same operation `player_stats` itself is built from.

Known simplifications vs. the official file (kept deliberately out of
scope -- see docs/data_dictionary.md): fumbles are not attributed to a
specific player, and two-point conversions are ignored. Both are rare
enough per week to leave fantasy-point estimates close but not exact.

Not part of the validated 2021-2024 research pipeline -- only used by
src/predict/live_predict.py for the current season.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_weekly_stats_from_pbp(pbp: pd.DataFrame) -> pd.DataFrame:
    pbp = pbp[pbp["season_type"] == "REG"].copy()

    passing = (
        pbp[pbp["pass_attempt"] == 1]
        .groupby(["passer_player_id", "season", "week"])
        .agg(
            completions=("complete_pass", "sum"),
            attempts=("pass_attempt", "sum"),
            passing_yards=("passing_yards", "sum"),
            passing_tds=("pass_touchdown", "sum"),
            interceptions=("interception", "sum"),
            passing_air_yards=("air_yards", "sum"),
            passing_epa=("epa", "sum"),
            recent_team=("posteam", "first"),
            opponent_team=("defteam", "first"),
        )
        .reset_index()
        .rename(columns={"passer_player_id": "gsis_id"})
    )

    rushing = (
        pbp[pbp["rush_attempt"] == 1]
        .groupby(["rusher_player_id", "season", "week"])
        .agg(
            carries=("rush_attempt", "sum"),
            rushing_yards=("rushing_yards", "sum"),
            rushing_tds=("rush_touchdown", "sum"),
            rushing_epa=("epa", "sum"),
            recent_team=("posteam", "first"),
            opponent_team=("defteam", "first"),
        )
        .reset_index()
        .rename(columns={"rusher_player_id": "gsis_id"})
    )

    receiving = (
        pbp[(pbp["pass_attempt"] == 1) & pbp["receiver_player_id"].notna()]
        .groupby(["receiver_player_id", "season", "week"])
        .agg(
            targets=("pass_attempt", "sum"),
            receptions=("complete_pass", "sum"),
            receiving_yards=("receiving_yards", "sum"),
            receiving_tds=("pass_touchdown", "sum"),
            receiving_air_yards=("air_yards", "sum"),
            receiving_yards_after_catch=("yards_after_catch", "sum"),
            receiving_epa=("epa", "sum"),
            recent_team=("posteam", "first"),
            opponent_team=("defteam", "first"),
        )
        .reset_index()
        .rename(columns={"receiver_player_id": "gsis_id"})
    )

    df = passing.merge(rushing, on=["gsis_id", "season", "week"], how="outer", suffixes=("", "_rush"))
    df = df.merge(receiving, on=["gsis_id", "season", "week"], how="outer", suffixes=("", "_rec"))

    # Coalesce team/opponent across the three role tables (a player has one
    # team; whichever role table it came from should agree).
    for col in ["recent_team", "opponent_team"]:
        parts = [c for c in [col, f"{col}_rush", f"{col}_rec"] if c in df.columns]
        df[col] = df[parts].bfill(axis=1).iloc[:, 0]
    df = df.drop(columns=[c for c in df.columns if c.endswith(("_rush", "_rec")) and c not in
                           ("recent_team", "opponent_team")], errors="ignore")

    stat_cols = ["completions", "attempts", "passing_yards", "passing_tds", "interceptions",
                 "passing_air_yards", "passing_epa", "carries", "rushing_yards", "rushing_tds",
                 "rushing_epa", "targets", "receptions", "receiving_yards", "receiving_tds",
                 "receiving_air_yards", "receiving_yards_after_catch", "receiving_epa"]
    for c in stat_cols:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = df[c].fillna(0.0)

    # Team-week totals for target/air-yards share. The denominator is
    # *targeted* pass attempts (a receiver was actually assigned), not every
    # pass_attempt row -- throwaways/spikes/broken plays can have
    # pass_attempt==1 with no receiver_player_id, and nflverse's own
    # target_share excludes those (verified against the official 2024 file).
    targeted = pbp[(pbp["pass_attempt"] == 1) & pbp["receiver_player_id"].notna()]
    team_pass_attempts = targeted.groupby(["posteam", "season", "week"]).size().rename("team_pass_attempts")
    team_air_yards = targeted.groupby(["posteam", "season", "week"])["air_yards"].sum().rename("team_air_yards")
    team_totals = pd.concat([team_pass_attempts, team_air_yards], axis=1).reset_index()
    team_totals = team_totals.rename(columns={"posteam": "recent_team"})

    df = df.merge(team_totals, on=["recent_team", "season", "week"], how="left")
    df["target_share"] = (df["targets"] / df["team_pass_attempts"]).replace([np.inf, -np.inf], np.nan)
    df["air_yards_share"] = (df["receiving_air_yards"] / df["team_air_yards"]).replace([np.inf, -np.inf], np.nan)
    df["wopr"] = 1.5 * df["target_share"].fillna(0) + 0.7 * df["air_yards_share"].fillna(0)
    df = df.drop(columns=["team_pass_attempts", "team_air_yards"])

    # Standard PPR scoring. Fumbles and 2-point conversions are not modeled
    # (rare enough per week that this stays close, not exact).
    df["fantasy_points"] = (
        df["passing_yards"] * 0.04 + df["passing_tds"] * 4 - df["interceptions"] * 2
        + df["rushing_yards"] * 0.1 + df["rushing_tds"] * 6
        + df["receiving_yards"] * 0.1 + df["receiving_tds"] * 6
    )
    df["fantasy_points_ppr"] = df["fantasy_points"] + df["receptions"]

    df["season_type"] = "REG"
    df = df.dropna(subset=["gsis_id"])
    return df
