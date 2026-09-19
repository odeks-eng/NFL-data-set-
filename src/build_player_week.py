"""Merge every pulled source into one player-week table.

Key: gsis_id (player_id) + season + week. Only regular-season weeks make it
into the final modeling table (postseason has byes/single-elimination
structure that breaks the weekly cadence rolling-window features assume),
but everything is merged first so the join-quality stats below are honest
about the full pull.

Run: python -m src.build_player_week
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import FTN_MIN_SEASON, PROCESSED_DIR, RAW_DIR, SEASONS  # noqa: E402

pd.set_option("display.max_columns", None)

UNMATCHED_LOG = []


def _log_unmatched(name: str, total: int, matched: int) -> None:
    unmatched = total - matched
    pct = 0.0 if total == 0 else 100 * unmatched / total
    UNMATCHED_LOG.append(
        {"source": name, "rows": total, "matched": matched, "unmatched": unmatched, "unmatched_pct": round(pct, 2)}
    )
    print(f"  {name}: {matched}/{total} matched ({pct:.1f}% unmatched)")


def load_backbone() -> pd.DataFrame:
    """player_stats is the target-outcome table and the player-week backbone."""
    frames = [pd.read_parquet(RAW_DIR / f"player_stats_{s}.parquet") for s in SEASONS]
    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns={"player_id": "gsis_id"})
    return df


def build_id_crosswalk() -> pd.DataFrame:
    """gsis_id <-> pfr_id per season, from weekly rosters (most complete ID table)."""
    frames = []
    for s in SEASONS:
        wr = pd.read_parquet(RAW_DIR / f"weekly_rosters_{s}.parquet")
        cw = (
            wr[["season", "gsis_id", "pfr_id", "espn_id", "sleeper_id", "position"]]
            .dropna(subset=["gsis_id"])
            .drop_duplicates(subset=["season", "gsis_id"])
        )
        frames.append(cw)
    return pd.concat(frames, ignore_index=True)


def merge_ngs(df: pd.DataFrame) -> pd.DataFrame:
    for stat_type, prefix in [("passing", "ngs_pass"), ("rushing", "ngs_rush"), ("receiving", "ngs_rec")]:
        ngs = pd.read_parquet(RAW_DIR / f"ngs_{stat_type}.parquet")
        ngs = ngs[ngs["season"].isin(SEASONS) & (ngs["week"] > 0)].copy()
        keep_cols = [c for c in ngs.columns if c not in ("player_display_name", "player_position", "team_abbr",
                                                          "player_first_name", "player_last_name",
                                                          "player_jersey_number", "player_short_name",
                                                          "receptions", "targets", "yards", "attempts",
                                                          "completions", "rush_attempts", "rush_yards",
                                                          "rec_touchdowns", "rush_touchdowns", "pass_yards",
                                                          "pass_touchdowns", "interceptions")]
        ngs = ngs[keep_cols].rename(columns={c: f"{prefix}_{c}" for c in keep_cols if c not in
                                              ("season", "week", "season_type", "player_gsis_id")})
        ngs = ngs.rename(columns={"player_gsis_id": "gsis_id"})
        before = len(df)
        join_cols = {"season", "week", "season_type", "gsis_id"}
        first_new_col = next(c for c in keep_cols if c not in join_cols)
        df = df.merge(ngs, on=["gsis_id", "season", "week", "season_type"], how="left")
        matched = df[f"{prefix}_{first_new_col}"].notna().sum()
        _log_unmatched(f"ngs_{stat_type}", len(df), matched)
        assert before == len(df), "NGS merge should not change row count"
    return df


def merge_via_pfr_crosswalk(df: pd.DataFrame, source: pd.DataFrame, source_name: str,
                             value_cols: list[str], crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Sources keyed on pfr_player_id need a season-specific pfr_id -> gsis_id map."""
    cw = crosswalk.dropna(subset=["pfr_id"]).drop_duplicates(subset=["season", "pfr_id"])
    src = source.merge(
        cw[["season", "pfr_id", "gsis_id"]],
        left_on=["season", "pfr_player_id"], right_on=["season", "pfr_id"], how="left",
    )
    total = len(src)
    matched = src["gsis_id"].notna().sum()
    _log_unmatched(f"{source_name} [source-side: raw rows -> gsis_id via pfr_id crosswalk]", total, matched)

    src = src.dropna(subset=["gsis_id"])[["gsis_id", "season", "week"] + value_cols].drop_duplicates(
        subset=["gsis_id", "season", "week"]
    )
    df = df.merge(src, on=["gsis_id", "season", "week"], how="left")
    return df


def merge_snap_counts(df: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    frames = [pd.read_parquet(RAW_DIR / f"snap_counts_{s}.parquet") for s in SEASONS]
    sc = pd.concat(frames, ignore_index=True)
    return merge_via_pfr_crosswalk(
        df, sc, "snap_counts",
        ["offense_snaps", "offense_pct", "defense_snaps", "defense_pct", "st_snaps", "st_pct"],
        crosswalk,
    )


def merge_pfr_advstats(df: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    specs = {
        "pass": ["passing_bad_throws", "passing_bad_throw_pct", "times_sacked", "times_blitzed",
                 "times_hurried", "times_hit", "times_pressured", "times_pressured_pct"],
        "rec": ["receiving_broken_tackles", "receiving_drop", "receiving_drop_pct",
                "receiving_int", "receiving_rat"],
        "rush": ["rushing_yards_before_contact", "rushing_yards_before_contact_avg",
                 "rushing_yards_after_contact", "rushing_yards_after_contact_avg", "rushing_broken_tackles"],
    }
    for stat_type, cols in specs.items():
        frames = [pd.read_parquet(RAW_DIR / f"pfr_advstats_week_{stat_type}_{s}.parquet") for s in SEASONS]
        adv = pd.concat(frames, ignore_index=True)
        prefixed = {c: f"pfr_{stat_type}_{c}" for c in cols}
        adv = adv.rename(columns=prefixed)
        df = merge_via_pfr_crosswalk(df, adv, f"pfr_advstats_{stat_type}", list(prefixed.values()), crosswalk)
    return df


def merge_injuries(df: pd.DataFrame) -> pd.DataFrame:
    frames = [pd.read_parquet(RAW_DIR / f"injuries_{s}.parquet") for s in SEASONS]
    inj = pd.concat(frames, ignore_index=True)
    inj = inj[["gsis_id", "season", "week", "report_status", "report_primary_injury",
               "practice_status"]].dropna(subset=["gsis_id"]).drop_duplicates(subset=["gsis_id", "season", "week"])
    inj["_on_injury_report"] = True
    total = len(df)
    df = df.merge(inj, on=["gsis_id", "season", "week"], how="left")
    matched = df["_on_injury_report"].fillna(False).sum()
    df = df.drop(columns=["_on_injury_report"])
    _log_unmatched(
        "injuries (row present on that week's report at all; report_status is separately "
        "often blank for full-participation players -- that's not a join failure)",
        total, matched,
    )
    return df


def merge_depth_charts(df: pd.DataFrame) -> pd.DataFrame:
    frames = [pd.read_parquet(RAW_DIR / f"depth_charts_{s}.parquet") for s in SEASONS]
    dc = pd.concat(frames, ignore_index=True)
    dc = dc[["gsis_id", "season", "week", "depth_position", "formation"]].dropna(
        subset=["gsis_id"]
    ).drop_duplicates(subset=["gsis_id", "season", "week"])
    total = len(df)
    df = df.merge(dc, on=["gsis_id", "season", "week"], how="left")
    matched = df["depth_position"].notna().sum()
    _log_unmatched("depth_charts", total, matched)
    return df


def build_routes_run_proxy(crosswalk_positions: pd.DataFrame) -> pd.DataFrame:
    """Free-data proxy for 'routes run': plays where a non-lineman was on the
    field for a pass play (per nflverse's charted participation data).

    This is NOT the same as PFF/FTN route charting (which distinguishes an
    actual route from staying in to pass-block) -- it's an upper bound on
    routes run. Flagged clearly in the data dictionary. Position comes from
    the weekly-roster crosswalk (not the participation file's own
    `offense_positions` column, which is absent in the 2021-2022 schema) so
    the OL/non-OL filter is consistent across all seasons.
    """
    OL_POSITIONS = {"T", "G", "C", "OL", "OT", "OG"}
    frames = []
    for s in SEASONS:
        part_path = RAW_DIR / f"pbp_participation_{s}.parquet"
        if not part_path.exists():
            continue
        part = pd.read_parquet(part_path, columns=["nflverse_game_id", "play_id", "offense_players"])
        pbp = pd.read_parquet(RAW_DIR / f"pbp_{s}.parquet", columns=["game_id", "play_id", "week", "play_type"])
        part = part.merge(
            pbp, left_on=["nflverse_game_id", "play_id"], right_on=["game_id", "play_id"], how="inner"
        )
        part = part[part["play_type"] == "pass"].copy()
        part["season"] = s

        exploded = part[["season", "week"]].assign(gsis_id=part["offense_players"].str.split(";")).explode(
            "gsis_id"
        )
        exploded = exploded.merge(crosswalk_positions, on=["season", "gsis_id"], how="left")
        exploded = exploded[~exploded["position"].isin(OL_POSITIONS)]
        counts = (
            exploded.groupby(["gsis_id", "season", "week"], as_index=False)
            .size()
            .rename(columns={"size": "routes_run_proxy"})
        )
        frames.append(counts)
    if not frames:
        return pd.DataFrame(columns=["gsis_id", "season", "week", "routes_run_proxy"])
    return pd.concat(frames, ignore_index=True)


def merge_schedule_context(df: pd.DataFrame) -> pd.DataFrame:
    sched = pd.read_parquet(RAW_DIR / "schedules.parquet")
    sched = sched[sched["season"].isin(SEASONS)].copy()

    home = sched.rename(columns={
        "home_team": "team", "away_team": "opponent", "home_rest": "rest_days",
        "away_rest": "opp_rest_days", "home_moneyline": "team_moneyline",
    }).assign(is_home=1)
    away = sched.rename(columns={
        "away_team": "team", "home_team": "opponent", "away_rest": "rest_days",
        "home_rest": "opp_rest_days", "away_moneyline": "team_moneyline",
    }).assign(is_home=0)

    ctx_cols = ["game_id", "season", "week", "team", "opponent", "is_home", "rest_days", "opp_rest_days",
                "roof", "surface", "temp", "wind", "div_game", "spread_line", "total_line", "team_moneyline"]
    ctx = pd.concat([home[ctx_cols], away[ctx_cols]], ignore_index=True)

    # implied team total: favorite is home if spread_line < 0 by nflverse convention
    # (spread_line = home_score - away_score expectation; positive means home favored)
    ctx["team_implied_total"] = np.where(
        ctx["is_home"] == 1,
        ctx["total_line"] / 2 + ctx["spread_line"] / 2,
        ctx["total_line"] / 2 - ctx["spread_line"] / 2,
    )

    total = len(df)
    df = df.merge(
        ctx.drop(columns=["game_id"]), left_on=["season", "week", "recent_team"],
        right_on=["season", "week", "team"], how="left",
    )
    matched = df["team_implied_total"].notna().sum()
    _log_unmatched("schedule_context (team-week join)", total, matched)
    return df.drop(columns=["team"])


def merge_draft_context(df: pd.DataFrame) -> pd.DataFrame:
    draft = pd.read_parquet(RAW_DIR / "draft_picks.parquet")
    draft = draft[["gsis_id", "round", "pick"]].dropna(subset=["gsis_id"]).drop_duplicates(subset=["gsis_id"])
    draft = draft.rename(columns={"round": "draft_round", "pick": "draft_pick_overall"})
    total = len(df)
    df = df.merge(draft, on="gsis_id", how="left")
    matched = df["draft_pick_overall"].notna().sum()
    _log_unmatched("draft_picks (undrafted players legitimately have no match)", total, matched)
    return df


def main() -> None:
    print("Loading backbone (player_stats)...")
    df = load_backbone()
    print(f"  backbone: {len(df)} player-weeks, seasons {sorted(df.season.unique())}")

    print("Building ID crosswalk from weekly rosters...")
    crosswalk = build_id_crosswalk()

    print("Merging Next Gen Stats...")
    df = merge_ngs(df)

    print("Merging snap counts (via pfr_id crosswalk)...")
    df = merge_snap_counts(df, crosswalk)

    print("Merging PFR advanced stats (via pfr_id crosswalk)...")
    df = merge_pfr_advstats(df, crosswalk)

    print("Merging injury reports...")
    df = merge_injuries(df)

    print("Merging depth charts...")
    df = merge_depth_charts(df)

    print("Building routes-run proxy from play participation data...")
    routes = build_routes_run_proxy(crosswalk[["season", "gsis_id", "position"]])
    if len(routes):
        total = len(df)
        df = df.merge(routes, on=["gsis_id", "season", "week"], how="left")
        matched = df["routes_run_proxy"].notna().sum()
        _log_unmatched("routes_run_proxy (0 is a legitimate value for a play-caller/OL/DEF row, not a miss)", total, matched)
    else:
        df["routes_run_proxy"] = np.nan
        print("  routes_run_proxy: SKIPPED (pbp_participation_{season}.parquet not found in data/raw)")

    print("Merging schedule/context (rest, roof, surface, weather, market lines)...")
    df = merge_schedule_context(df)

    print("Merging draft context...")
    df = merge_draft_context(df)

    print("\nBackbone-side coverage (fraction of skill-position player-weeks with a non-null value):")
    skill = df[df["position"].isin(["QB", "RB", "WR", "TE"])]
    coverage_cols = [
        "offense_pct", "ngs_rec_avg_separation", "ngs_pass_avg_time_to_throw", "ngs_rush_efficiency",
        "pfr_rec_receiving_drop", "pfr_pass_times_pressured", "pfr_rush_rushing_yards_after_contact",
        "routes_run_proxy", "depth_position", "draft_pick_overall",
    ]
    coverage = pd.DataFrame({
        "column": coverage_cols,
        "pct_nonnull_skill_positions": [round(100 * skill[c].notna().mean(), 1) for c in coverage_cols],
    })
    print(coverage.to_string(index=False))
    coverage.to_csv(PROCESSED_DIR / "feature_coverage.csv", index=False)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "player_week_merged.parquet"
    df.to_parquet(out_path, index=False)
    print(f"\nWrote {len(df)} rows x {len(df.columns)} cols to {out_path}")

    log_df = pd.DataFrame(UNMATCHED_LOG)
    log_path = PROCESSED_DIR / "join_quality_log.csv"
    log_df.to_csv(log_path, index=False)
    print(f"Wrote join-quality log to {log_path}")
    print(log_df.to_string(index=False))


if __name__ == "__main__":
    main()
