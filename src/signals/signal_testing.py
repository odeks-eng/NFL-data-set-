"""Signal testing: stability, next-week predictive power, and blended-feature
comparisons, validated out-of-sample on a held-out season.

Every feature tested here is the pre-kickoff ("_pre" / "_r3" / "_season_pre")
version built in src/features/build_features.py -- i.e., we are always
correlating "what we knew before week N" against "what happened in week N",
never against the same week's own box score.

Run: python -m src.signals.signal_testing
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import HOLDOUT_SEASON, PROCESSED_DIR, TRAIN_SEASONS  # noqa: E402

MIN_N = 30  # don't report a correlation built on a handful of rows


def _clean_pair(df: pd.DataFrame, x: str, y: str) -> pd.DataFrame:
    return df[[x, y]].replace([np.inf, -np.inf], np.nan).dropna()


def stability(df: pd.DataFrame, col: str) -> tuple[float, int]:
    """Lag-1 within-season autocorrelation of the RAW (not rolling) weekly
    value -- how sticky is this metric from one week to the next?"""
    d = df.sort_values(["gsis_id", "season", "week"]).copy()
    d["_lag"] = d.groupby(["gsis_id", "season"])[col].shift(1)
    pair = _clean_pair(d, col, "_lag")
    if len(pair) < MIN_N:
        return np.nan, len(pair)
    r, _ = stats.pearsonr(pair[col], pair["_lag"])
    return r, len(pair)


def predictive_power(df: pd.DataFrame, feature: str, target: str, seasons: list[int]) -> tuple[float, float, int]:
    sub = df[df["season"].isin(seasons)]
    pair = _clean_pair(sub, feature, target)
    if len(pair) < MIN_N:
        return np.nan, np.nan, len(pair)
    r, _ = stats.pearsonr(pair[feature], pair[target])
    rho, _ = stats.spearmanr(pair[feature], pair[target])
    return r, rho, len(pair)


def evaluate_single_features(df: pd.DataFrame, specs: list[dict]) -> pd.DataFrame:
    rows = []
    for spec in specs:
        pos_mask = df["position"].isin(spec["positions"])
        sub = df[pos_mask]
        stab_r, stab_n = stability(sub, spec["raw_col"])
        train_r, train_rho, train_n = predictive_power(sub, spec["feature"], spec["target"], TRAIN_SEASONS)
        hold_r, hold_rho, hold_n = predictive_power(sub, spec["feature"], spec["target"], [HOLDOUT_SEASON])
        rows.append({
            "feature": spec["feature"], "target": spec["target"], "positions": "/".join(spec["positions"]),
            "stability_autocorr": round(stab_r, 3) if pd.notna(stab_r) else np.nan, "stability_n": stab_n,
            "train_pearson_r": round(train_r, 3) if pd.notna(train_r) else np.nan,
            "train_spearman_rho": round(train_rho, 3) if pd.notna(train_rho) else np.nan, "train_n": train_n,
            "holdout_pearson_r": round(hold_r, 3) if pd.notna(hold_r) else np.nan,
            "holdout_spearman_rho": round(hold_rho, 3) if pd.notna(hold_rho) else np.nan, "holdout_n": hold_n,
        })
    return pd.DataFrame(rows)


def evaluate_blend(df: pd.DataFrame, feat_a: str, feat_b: str, target: str, positions: list[str]) -> dict:
    """Fit a 2-feature linear blend on TRAIN_SEASONS, score on holdout, and
    compare against each input feature alone (holdout Pearson r) -- this is
    the "does the blend beat each input alone" test the brief asks for."""
    sub = df[df["position"].isin(positions)].copy()
    train = sub[sub["season"].isin(TRAIN_SEASONS)][[feat_a, feat_b, target]].replace(
        [np.inf, -np.inf], np.nan).dropna()
    hold = sub[sub["season"] == HOLDOUT_SEASON][[feat_a, feat_b, target]].replace(
        [np.inf, -np.inf], np.nan).dropna()
    if len(train) < MIN_N or len(hold) < MIN_N:
        return {"feature_a": feat_a, "feature_b": feat_b, "target": target,
                "positions": "/".join(positions), "note": f"insufficient data (train={len(train)}, hold={len(hold)})"}

    model = LinearRegression().fit(train[[feat_a, feat_b]], train[target])
    blend_pred = model.predict(hold[[feat_a, feat_b]])
    blend_r, _ = stats.pearsonr(blend_pred, hold[target])

    r_a, _ = stats.pearsonr(hold[feat_a], hold[target])
    r_b, _ = stats.pearsonr(hold[feat_b], hold[target])

    return {
        "feature_a": feat_a, "feature_b": feat_b, "target": target, "positions": "/".join(positions),
        "train_n": len(train), "holdout_n": len(hold),
        "holdout_r_feature_a_alone": round(r_a, 3), "holdout_r_feature_b_alone": round(r_b, 3),
        "holdout_r_blend": round(blend_r, 3),
        "blend_beats_best_single": round(blend_r, 3) > round(max(abs(r_a), abs(r_b)), 3),
        "blend_coef_a": round(model.coef_[0], 4), "blend_coef_b": round(model.coef_[1], 4),
    }


def main() -> None:
    df = pd.read_parquet(PROCESSED_DIR / "player_week_features.parquet")
    df = df[df["season_type"] == "REG"].copy()
    print(f"Regular-season player-weeks: {len(df)} (train seasons {TRAIN_SEASONS}, holdout {HOLDOUT_SEASON})")

    WR_TE = ["WR", "TE"]
    RB = ["RB"]
    ALL_SKILL = ["QB", "RB", "WR", "TE"]

    single_feature_specs = [
        # Usage
        dict(feature="target_share_r3", raw_col="target_share", target="receiving_yards", positions=WR_TE),
        dict(feature="target_share_season_pre", raw_col="target_share", target="receiving_yards", positions=WR_TE),
        dict(feature="air_yards_share_r3", raw_col="air_yards_share", target="receiving_yards", positions=WR_TE),
        dict(feature="offense_pct_r3", raw_col="offense_pct", target="receiving_yards", positions=WR_TE),
        dict(feature="offense_pct_r3", raw_col="offense_pct", target="fantasy_points_ppr", positions=RB),
        dict(feature="routes_run_proxy_r3", raw_col="routes_run_proxy", target="receiving_yards", positions=WR_TE),
        dict(feature="rz_target_share_season_pre", raw_col="rz_target_share", target="receiving_yards", positions=WR_TE),
        dict(feature="rz_carry_share_season_pre", raw_col="rz_carry_share", target="rushing_yards", positions=RB),
        dict(feature="wopr_r3", raw_col="wopr", target="receiving_yards", positions=WR_TE),
        # Efficiency
        dict(feature="yards_per_route_run_r3", raw_col="yards_per_route_run", target="receiving_yards", positions=WR_TE),
        dict(feature="ngs_rec_avg_separation_r3", raw_col="ngs_rec_avg_separation", target="receiving_yards", positions=WR_TE),
        dict(feature="ngs_rec_avg_separation_season_pre", raw_col="ngs_rec_avg_separation", target="receiving_yards", positions=WR_TE),
        dict(feature="target_per_route_r3", raw_col="target_per_route", target="receiving_yards", positions=WR_TE),
        dict(feature="receiving_epa_r3", raw_col="receiving_epa", target="receiving_yards", positions=WR_TE),
        dict(feature="ngs_rush_rush_yards_over_expected_per_att_season_pre", raw_col="ngs_rush_rush_yards_over_expected_per_att",
             target="rushing_yards", positions=RB),
        # Context
        dict(feature="team_implied_total", raw_col="team_implied_total", target="fantasy_points_ppr", positions=ALL_SKILL),
        dict(feature="def_pass_epa_allowed_pre", raw_col="def_pass_epa_allowed_pre", target="receiving_yards", positions=WR_TE),
        dict(feature="def_epa_allowed_to_position_pre", raw_col="def_epa_allowed_to_position_pre", target="receiving_yards", positions=WR_TE),
        dict(feature="def_epa_allowed_to_position_pre", raw_col="def_epa_allowed_to_position_pre", target="fantasy_points_ppr", positions=RB),
        dict(feature="rest_days", raw_col="rest_days", target="fantasy_points_ppr", positions=ALL_SKILL),
        # Draft capital -- static per-player, never tested standalone before (only showed up
        # inside the multivariate model). Note: its "stability" is mechanically ~1.0 since the
        # raw value doesn't change week to week within a career -- that's an artifact of the
        # metric, not a finding, and is called out as such in reports/report.md.
        dict(feature="draft_pick_overall", raw_col="draft_pick_overall", target="receiving_yards", positions=WR_TE),
        dict(feature="draft_pick_overall", raw_col="draft_pick_overall", target="rushing_yards", positions=RB),
        dict(feature="draft_pick_overall", raw_col="draft_pick_overall", target="fantasy_points_ppr", positions=RB),
    ]

    print("\n=== Single-feature signal test ===")
    single_results = evaluate_single_features(df, single_feature_specs)
    print(single_results.to_string(index=False))
    single_results.to_csv(PROCESSED_DIR / "signal_test_single_features.csv", index=False)

    print("\n=== Blended-feature test (does combining beat either input alone, out-of-sample?) ===")
    blend_specs = [
        ("target_share_season_pre", "ngs_rec_avg_separation_season_pre", "receiving_yards", WR_TE),
        ("target_share_season_pre", "yards_per_route_run_season_pre", "receiving_yards", WR_TE),
        ("routes_run_proxy_season_pre", "target_per_route_season_pre", "receiving_yards", WR_TE),
        ("offense_pct_season_pre", "ngs_rush_rush_yards_over_expected_per_att_season_pre", "rushing_yards", RB),
        ("target_share_season_pre", "team_implied_total", "receiving_yards", WR_TE),
        ("rz_target_share_season_pre", "target_share_season_pre", "receiving_yards", WR_TE),
        # Does draft capital add independent information beyond current usage,
        # or is it redundant with "early picks get more usage anyway"?
        ("target_share_season_pre", "draft_pick_overall", "receiving_yards", WR_TE),
        ("offense_pct_season_pre", "draft_pick_overall", "rushing_yards", RB),
        ("offense_pct_season_pre", "draft_pick_overall", "fantasy_points_ppr", RB),
    ]
    blend_rows = [evaluate_blend(df, a, b, t, pos) for a, b, t, pos in blend_specs]
    blend_results = pd.DataFrame(blend_rows)
    print(blend_results.to_string(index=False))
    blend_results.to_csv(PROCESSED_DIR / "signal_test_blends.csv", index=False)


if __name__ == "__main__":
    main()
