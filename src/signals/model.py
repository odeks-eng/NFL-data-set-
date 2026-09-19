"""Multivariate model: combine usage/efficiency/context features with a
gradient-boosted tree, instead of the one- and two-feature tests in
signal_testing.py.

Every predictor is a pre-kickoff feature (see the suffix convention in
docs/data_dictionary.md) or a context column that's genuinely known before
the game (rest days, roof/surface, market lines, injury/depth-chart status).
No same-week outcome column is ever used as a predictor.

Validation is deliberately conservative given the sample sizes involved
(~8-9k train rows, ~2-3k holdout rows per position group):
  1. Leave-one-season-out CV across the 3 train seasons (2021-2023) --
     this is the honest in-train estimate, not a single fixed split.
  2. A final model trained on all of 2021-2023, scored ONCE on the
     untouched 2024 holdout -- the same split signal_testing.py uses, so
     the two are directly comparable.
  3. Permutation importance on the holdout set (not the built-in impurity
     importances, which are biased toward high-cardinality features) so
     the "what is the model actually using" answer is trustworthy.

Run: python -m src.signals.model
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import r2_score, root_mean_squared_error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import HOLDOUT_SEASON, PROCESSED_DIR, TRAIN_SEASONS  # noqa: E402

PREDICTOR_SUFFIXES = ("_r3", "_r5", "_season_pre", "_std_dev_pre", "_pre")
CONTEXT_COLS = [
    "is_home", "rest_days", "opp_rest_days", "roof", "surface", "temp", "wind", "div_game",
    "spread_line", "total_line", "team_implied_total", "team_moneyline",
    "report_status", "practice_status", "depth_position", "draft_round", "draft_pick_overall",
]
CATEGORICAL_COLS = ["roof", "surface", "report_status", "practice_status", "depth_position"]

MODEL_SPECS = [
    dict(name="wr_te_receiving_yards", positions=["WR", "TE"], target="receiving_yards"),
    dict(name="rb_rushing_yards", positions=["RB"], target="rushing_yards"),
    dict(name="rb_fantasy_points_ppr", positions=["RB"], target="fantasy_points_ppr"),
]

HGB_PARAMS = dict(
    max_leaf_nodes=15, max_depth=4, learning_rate=0.05, l2_regularization=1.0,
    min_samples_leaf=30, max_iter=300, early_stopping=True, n_iter_no_change=20,
    validation_fraction=0.15, random_state=0,
)


def build_predictor_matrix(df: pd.DataFrame, predictor_cols: list[str]) -> pd.DataFrame:
    X = df[predictor_cols].copy()
    for c in CATEGORICAL_COLS:
        if c in X.columns:
            X[c] = X[c].astype("object").fillna("__missing__").astype("category")
    return X


def leave_one_season_out_cv(df: pd.DataFrame, predictor_cols: list[str], target: str) -> list[dict]:
    rows = []
    for held in TRAIN_SEASONS:
        fit_seasons = [s for s in TRAIN_SEASONS if s != held]
        train = df[df["season"].isin(fit_seasons)]
        val = df[df["season"] == held]
        X_train, y_train = build_predictor_matrix(train, predictor_cols), train[target]
        X_val, y_val = build_predictor_matrix(val, predictor_cols), val[target]

        model = HistGradientBoostingRegressor(categorical_features=[c for c in CATEGORICAL_COLS if c in X_train.columns],
                                               **HGB_PARAMS)
        model.fit(X_train, y_train)
        pred = model.predict(X_val)
        r, _ = stats.pearsonr(pred, y_val)
        rows.append({
            "held_out_season": held, "train_n": len(X_train), "val_n": len(X_val),
            "val_pearson_r": round(r, 3), "val_r2": round(r2_score(y_val, pred), 3),
            "val_rmse": round(root_mean_squared_error(y_val, pred), 2),
        })
    return rows


def run_spec(df: pd.DataFrame, spec: dict, predictor_cols: list[str]) -> dict:
    sub = df[df["position"].isin(spec["positions"])].copy()
    sub = sub.dropna(subset=[spec["target"]])
    train = sub[sub["season"].isin(TRAIN_SEASONS)]
    hold = sub[sub["season"] == HOLDOUT_SEASON]

    # Some predictors (e.g. ngs_pass_* for a WR/TE-only model) are entirely
    # null for this position group -- drop those rather than feed the
    # binner a column with fewer than 2 distinct real values.
    usable = [c for c in predictor_cols if train[c].notna().sum() >= 2 and train[c].nunique(dropna=True) >= 2]
    dropped = sorted(set(predictor_cols) - set(usable))
    predictor_cols = usable
    print(f"\n=== {spec['name']} ===  train_n={len(train)}  holdout_n={len(hold)}  "
          f"predictors={len(predictor_cols)} (dropped {len(dropped)} all-null/constant for this group)")

    cv_rows = leave_one_season_out_cv(train, predictor_cols, spec["target"])
    cv_df = pd.DataFrame(cv_rows)
    print("Leave-one-season-out CV on train seasons:")
    print(cv_df.to_string(index=False))

    X_train = build_predictor_matrix(train, predictor_cols)
    y_train = train[spec["target"]]
    X_hold = build_predictor_matrix(hold, predictor_cols)
    y_hold = hold[spec["target"]]

    model = HistGradientBoostingRegressor(
        categorical_features=[c for c in CATEGORICAL_COLS if c in X_train.columns], **HGB_PARAMS
    )
    model.fit(X_train, y_train)
    pred_hold = model.predict(X_hold)

    holdout_r, _ = stats.pearsonr(pred_hold, y_hold)
    holdout_r2 = r2_score(y_hold, pred_hold)
    holdout_rmse = root_mean_squared_error(y_hold, pred_hold)

    baseline_pred = np.full(len(y_hold), y_train.mean())
    baseline_rmse = root_mean_squared_error(y_hold, baseline_pred)

    print(f"Final model (fit on {TRAIN_SEASONS}, scored on {HOLDOUT_SEASON} holdout):")
    print(f"  holdout Pearson r = {holdout_r:.3f}   holdout R^2 = {holdout_r2:.3f}   "
          f"RMSE = {holdout_rmse:.2f}  (mean-baseline RMSE = {baseline_rmse:.2f})")

    perm = permutation_importance(model, X_hold, y_hold, n_repeats=15, random_state=0, scoring="r2")
    importance_df = (
        pd.DataFrame({"feature": predictor_cols, "perm_importance_mean": perm.importances_mean,
                      "perm_importance_std": perm.importances_std})
        .sort_values("perm_importance_mean", ascending=False)
        .reset_index(drop=True)
    )
    print("Top 10 features by holdout permutation importance:")
    print(importance_df.head(10).to_string(index=False))

    cv_df.to_csv(PROCESSED_DIR / f"model_cv_{spec['name']}.csv", index=False)
    importance_df.to_csv(PROCESSED_DIR / f"model_importance_{spec['name']}.csv", index=False)

    return {
        "name": spec["name"], "target": spec["target"], "positions": "/".join(spec["positions"]),
        "train_n": len(train), "holdout_n": len(hold),
        "cv_mean_pearson_r": round(cv_df["val_pearson_r"].mean(), 3),
        "holdout_pearson_r": round(holdout_r, 3), "holdout_r2": round(holdout_r2, 3),
        "holdout_rmse": round(holdout_rmse, 2), "baseline_rmse": round(baseline_rmse, 2),
    }


def main() -> None:
    df = pd.read_parquet(PROCESSED_DIR / "player_week_features.parquet")
    df = df[df["season_type"] == "REG"].copy()

    predictor_cols = [c for c in df.columns if c.endswith(PREDICTOR_SUFFIXES)] + \
        [c for c in CONTEXT_COLS if c in df.columns]
    predictor_cols = sorted(set(predictor_cols))
    print(f"Using {len(predictor_cols)} predictor columns")

    summaries = [run_spec(df, spec, predictor_cols) for spec in MODEL_SPECS]
    summary_df = pd.DataFrame(summaries)
    summary_df.to_csv(PROCESSED_DIR / "model_summary.csv", index=False)
    print("\n=== Summary across all model specs ===")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
