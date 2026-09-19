# NFL Player Analytics — Signal Testing Report

**Scope:** 2021–2024 regular seasons, QB/RB/WR/TE, weekly granularity.
**Train:** 2021–2023 (n varies by feature, ~8,700–16,000 player-weeks).
**Holdout (out-of-sample):** 2024 (~2,900–5,200 player-weeks).
**Full methodology, source list, and column definitions:**
`docs/source_inventory.md`, `docs/data_dictionary.md`.

All numbers below are Pearson `r` between a **pre-kickoff** feature (a
rolling average of what happened before that week — see the `_r3` /
`_season_pre` suffix convention in the data dictionary) and that week's
actual outcome. Every feature was fit/validated with a strict train
(2021–2023) → holdout (2024) split; the `r` values quoted as "predictive
power" are the **holdout** numbers unless stated otherwise.

## Top signals, ranked

| Rank | Signal | Target | Holdout r | Stability (lag-1 autocorr) | Note |
|---|---|---|---|---|---|
| 1 | `offense_pct_r3` (snap share, last 3 games) | RB fantasy points (PPR) | **0.55** | 0.73 | Best combination of predictive power *and* stability of anything tested. Snap share is the stickiest usage metric in the dataset. |
| 2 | `target_share_season_pre` | WR/TE receiving yards | **0.53** | 0.57 | Single strongest predictor of receiving yards. Season-to-date average slightly out-predicts the 3-game window. |
| 3 | `wopr_r3` (nflverse's own blend: 1.5×target share + 0.7×air-yards share) | WR/TE receiving yards | 0.51 | 0.58 | Confirms nflverse's existing blend is good — but it does **not** beat plain target share in this test (0.51 vs 0.53). The air-yards component doesn't add much once target share is already known. |
| 4 | **Blend:** `offense_pct` × `RYOE/att` (workload × per-touch efficiency) | RB rushing yards | **0.52** (blend) vs 0.47 / 0.22 alone | — | Genuine blending win — beats both single inputs out-of-sample. See "Blends that worked" below. |
| 5 | `offense_pct_r3` (snap share) | WR/TE receiving yards | 0.46 | 0.74 | Same story as #1 for pass catchers: less predictive of yards specifically than target share, but extremely stable. |
| 6 | **Blend:** `routes_run_proxy` × `target_per_route` | WR/TE receiving yards | **0.48** (blend) vs 0.45 / 0.06 alone | — | Second confirmed blending win, but built on the free-data route *proxy* (see caveats) — treat as directional, not final. |
| 7 | `air_yards_share_r3` | WR/TE receiving yards | 0.43 | 0.50 | Weaker than target share alone; expected, since air yards share is noisier (driven by a handful of deep shots). |
| 8 | `rz_carry_share_season_pre` | RB rushing yards | 0.47 | 0.42 | Decent predictive power, but noticeably less stable than overall snap/target share — red-zone opportunity swings more week to week. |
| 9 | `rz_target_share_season_pre` | WR/TE receiving yards | 0.31 | **0.14** | Weakest stability of any usage metric tested. Red zone target share is close to noise from one week to the next, even though it has *some* predictive value on average — a good example of "average signal, bad bet-by-bet reliability." |
| 10 | `receiving_epa_r3` | WR/TE receiving yards | 0.25 | 0.09 | Low stability — EPA is a noisy per-play stat that takes a large sample to stabilize; a 3-game rolling window is not enough. |

## Blends that beat every single input, out-of-sample (2024 holdout)

| Blend | Target | Holdout r (blend) | vs. input A alone | vs. input B alone |
|---|---|---|---|---|
| Snap share × Rush Yards Over Expected per attempt | RB rushing yards | **0.515** | 0.472 (snap share) | 0.219 (RYOE/att) |
| Routes-run proxy × Targets-per-route proxy | WR/TE receiving yards | **0.477** | 0.450 (routes) | 0.062 (TPRR) |

Both blends were fit with a plain 2-feature linear regression on
2021–2023 and scored on the untouched 2024 season — this is a genuinely
out-of-sample result, not a fitted-and-graded-on-the-same-data number.
The RB blend is the more trustworthy of the two: snap share and RYOE/att
are both measured directly (no proxy involved). The WR/TE blend is
promising but rides on `routes_run_proxy`, a free-data stand-in for real
route charting (see Known Weaknesses) — worth re-testing with PFF/FTN's
actual route data before leaning on it.

## Blends that did **not** beat the single best input (be skeptical)

This matters as much as the wins:

- **Target share + separation** (0.413 blended vs. 0.415 for target share
  alone): separation adds essentially nothing once volume is known.
- **Target share + yards-per-route-run** (0.530 vs. 0.530): a flat tie —
  no gain.
- **Target share + team implied total** (0.529 vs. 0.530): team-level
  scoring context barely moves an individual player's expected yards; the
  effect is real in theory but too diluted across ~5 pass-catchers per team
  to show up in a simple linear blend.
- **Red-zone target share + target share** (0.529 vs. 0.530): red zone
  share is a subset of overall target share, so it carries little
  independent information once overall share is known.

## Surprising / counter-intuitive findings

- **NGS average separation is *negatively* correlated with receiving
  yards** (holdout r = **−0.09**), not positively as intuition (and a lot
  of fantasy content) would suggest. This likely reflects a real
  composition effect: high-separation receivers are disproportionately
  short-route/underneath/slot players who rack up easy catches but low
  gross yardage, while yardage is dominated by target *volume* and
  downfield opportunity, not per-target separation. We are flagging this
  rather than burying it — it directly contradicts a commonly repeated
  fantasy/DFS heuristic ("separation = production"), at least at the
  weekly gross-yardage level. It might behave differently against a
  catch-rate or "avoid negative game" target instead of raw yards — that's
  a natural follow-up, not something we've tested yet.
- **Opponent pass defense EPA allowed (rolling) has ~zero correlation**
  with a receiver's next-week yards (holdout r = 0.011). Aggregate defensive
  EPA allowed is too coarse — it doesn't distinguish coverage that's weak
  specifically against outside receivers vs. slot vs. tight ends. A
  position/alignment-specific opponent metric is a clear next step (flagged
  under Open Questions).
- **Rest days show no signal** in a simple bivariate test (holdout r =
  −0.01) despite being a commonly cited context factor. This doesn't mean
  rest never matters — it means it doesn't matter *on its own*, isolated
  from everything else, in a linear sense. Testing it inside a multivariate
  model (where it might matter conditionally, e.g. only after short weeks)
  is a next step, not a settled null result.

## Stability vs. predictive power — the practical takeaway

The two don't always move together, and that distinction matters for how
each signal should actually be used:

- **High stability + high predictive power** (snap share, target share):
  safe to trust on a rolling 3-game or season-to-date basis; these are the
  backbone signals for both season-long fantasy and weekly props.
  Note the two coverage caveats above (NGS 30-73% coverage) apply to
  particular efficiency metrics, not to these usage stats, which are
  computed directly from box-score data with 92%+ coverage.
- **Decent predictive power + low stability** (red zone shares, single-game
  EPA): real signal exists in the data on average, but any *one* prior
  week is a weak estimate of it — these need longer windows or shrinkage
  toward a positional/team prior before they're bet-worthy, not raw
  3-game averages.

## Multivariate model — does combining everything beat the best blend?

Everything above is a correlation or a 2-feature linear blend, deliberately
kept simple so each comparison is auditable. `src/signals/model.py` takes
the natural next step: a gradient-boosted tree
(`HistGradientBoostingRegressor`) trained on all 78 pre-kickoff predictors
at once (every `_r3`/`_r5`/`_season_pre`/`_pre` column plus context —
market lines, rest, weather, injury/depth-chart status, draft capital).

**Validation, kept conservative given the sample sizes:** leave-one-season-
out cross-validation across 2021–2023 (train on two seasons, validate on
the third, rotate), then a single final fit on all of 2021–2023 scored once
on the untouched 2024 holdout — the same split used everywhere else in this
report, so the numbers below are directly comparable to the tables above.

| Model | Target | CV mean r (train seasons) | Holdout r | Holdout R² | Holdout RMSE vs. mean-baseline RMSE |
|---|---|---|---|---|---|
| WR/TE | receiving yards | 0.543 | **0.555** | 0.308 | 27.9 vs. 33.5 |
| RB | rushing yards | 0.540 | **0.582** | 0.338 | 30.4 vs. 37.4 |
| RB | fantasy points (PPR) | 0.538 | **0.599** | 0.357 | 6.41 vs. 7.99 |

(Numbers above include `def_epa_allowed_to_position_pre`, the position-specific
opponent-context feature added after the first pass of this model — see
immediately below. Its effect was small: the WR/TE and RB-rushing holdout r
each moved up by ~0.005, within noise for this sample size, but in the
expected direction.)

Holdout r tracks the CV mean closely for all three (no sign of the model
overfitting to the training seasons), and every model beats its
mean-baseline RMSE by 15–20%.

**Compared to the single-feature and blend results earlier in this report:**

- **WR/TE receiving yards:** best single feature was `target_share_season_pre`
  at r = 0.530. The full model reaches **0.554** — a real but modest gain
  (R² goes from ~0.28 to 0.307). Combining everything helps only a little
  once target share is already known, echoing the "blend didn't beat target
  share alone" pattern from the 2-feature tests above.
- **RB rushing yards:** best single feature was `rz_carry_share_season_pre`
  (r = 0.471); best hand-built blend was snap share × RYOE/att (r = 0.515).
  The full model reaches **0.577** — this is the clearest win for going
  multivariate. RB rushing production is genuinely multi-causal (volume,
  per-touch efficiency, and — per the importance ranking below — draft
  capital as a durable talent signal), and a 2-feature linear blend
  couldn't capture all of that at once.
- **RB fantasy points (PPR):** best single feature was `offense_pct_r3`
  (r = 0.552). The full model reaches **0.599**, a modest gain in the same
  direction as receiving yards.

**What the model is actually using** (holdout permutation importance —
more trustworthy than the built-in impurity importances, which are biased
toward high-cardinality features; full lists in
`data/processed/model_importance_*.csv`):

- Usage dominates everywhere: `target_share_season_pre`,
  `fantasy_points_ppr_season_pre`, and `offense_pct_r3`/`_r5` are the top or
  near-top feature in all three models — consistent with the single-feature
  results, not a contradiction of them.
- **`draft_pick_overall` shows up as the #2 or #3 feature in every model** —
  a finding the bivariate tests never surfaced because it's a static,
  slow-moving context variable rather than a weekly one. Earlier draft
  picks (lower `draft_pick_overall`) predict higher output even after
  controlling for current usage, i.e. draft capital is carrying some
  durable talent signal beyond what's captured in this week's role. Worth
  testing on its own as a standalone context feature going forward.
- `routes_run_proxy` (WR/TE) and `ngs_rush_rush_yards_over_expected_per_att`
  (RB) both place in the top handful — the same two features behind the
  blends that beat their single inputs earlier in this report, now
  confirmed to matter inside a full model too, not just in an isolated
  2-feature test.
- `def_pass_epa_allowed_pre` (opponent pass defense) appears with a small
  but non-zero importance in the RB fantasy-points model, despite showing
  ~zero correlation as a standalone feature earlier. This is a legitimate
  and expected pattern, not a contradiction: a weak marginal signal can
  still contribute inside a multivariate model once the dominant usage
  features are already accounted for — exactly the kind of feature a
  bivariate test is the wrong tool to evaluate.

**Reading on this**: treat the multivariate numbers as the best current
estimate of the ceiling for this feature set — real, moderate, out-of-sample
lift over the best single feature or hand-built blend, driven mostly by
usage plus a genuinely new signal (draft capital) that the earlier
bivariate pass had no way to surface. It is not a large enough jump to
suggest the single-feature signals in the rest of this report are wrong or
unnecessary — they're still the right tool for auditing *why* the model
works, which is the point of running both.

## Known weaknesses

1. **`routes_run_proxy` is not real route-participation data.** It counts
   pass plays where a non-lineman was on the field, which also counts
   players who stayed in to pass-block instead of running a route (RBs and
   in-line TEs especially). True route charting (PFF, or FTN's paid tier —
   not the free play-level charting nflverse mirrors) would very likely
   sharpen both the routes-run signal and the two blends built on it.
2. **NGS coverage is volume-gated** (~30% of all WR/TE/RB weeks with any
   target, ~73% once restricted to 80+ season targets). Findings involving
   separation, CPOE, or RYOE are implicitly conditioned on players good/
   used enough to clear NGS's own publication threshold — a real form of
   survivorship bias worth remembering when reading the separation result
   above.
3. **No player-prop market data.** The game odds file only backs
   team-level implied totals — there's no way in this dataset to test
   closing-line value against an actual receiving-yards or rushing-yards
   prop line, which is the sharpest test the original brief asks for. This
   is a network-access gap in the build environment (see
   `docs/source_inventory.md`), not a fundamental data-availability one.
4. **Weekly target table (`player_stats`) lags the rest of nflverse's
   mirror** — pbp, snap counts, rosters, and NGS were all current through
   the 2025 season at pull time, but the aggregated weekly box-score table
   (the outcome we're predicting) was not. The dataset is scoped to
   2021–2024 as a result. This is very likely a temporary state of the
   specific mirror snapshot this session could reach, not a real gap —
   re-running `src/ingest/pull_all.py` later should pick up 2025 for free.
5. ~~Everything here is a bivariate test.~~ **Update:** a multivariate
   gradient-boosted model is now included (see the section above) and, as
   expected, beats every single feature and hand-built blend out-of-sample
   — most clearly for RB rushing yards (0.577 vs. 0.515 for the best
   blend). The single-feature/blend tests remain in this report because
   they're what makes the model's behavior auditable, not because they're
   competitive with it on raw predictive power.
6. **Postseason weeks are excluded** from all of the above (kept in the
   merged dataset, dropped before rolling/signal-testing) because the
   single-elimination structure and bye-week gaps break the weekly-cadence
   assumption the rolling windows rely on.

## Open questions and recommended next steps

1. **Re-run from an environment with open egress** to pick up (a) 2025
   `player_stats`, (b) point-in-time weather beyond what's in `schedules`,
   and (c) player-prop market lines for a real CLV backtest. This is the
   single highest-leverage next step and doesn't cost anything.
2. **Do not buy PFF/FTN yet.** The clearest paid-data case this analysis
   surfaced is real route-participation data (to fix `routes_run_proxy` and
   re-test the two blends that depend on it) — but test that hypothesis
   cheaply first by seeing whether a *better* free proxy (e.g. restricting
   to pass plays where the player ran more than N yards downfield, using
   `pbp_participation`'s per-play route-type field for the targeted
   receiver as a partial check) narrows the gap before paying for it.
3. **Build opponent context at the position/alignment level**, not just
   aggregate defensive EPA allowed — e.g., EPA allowed specifically to
   slot receivers, or to receivers who ran a given route type (available
   in the free `ftn_charting` and `pbp_participation` data already pulled,
   just not yet used this way).
4. **Test a shrinkage/empirical-Bayes version of the low-stability metrics**
   (red zone share, single-game EPA) instead of raw rolling means — e.g.
   blend a player's own red-zone share with the position's league-average
   red-zone share, weighted by sample size.
5. **Re-test the separation finding against a different target** (catch
   rate, or a "floor" outcome like hitting a fixed yardage threshold)
   before concluding separation is un-informative — it may simply be the
   wrong target variable for what separation actually predicts.
6. ~~Move from bivariate correlations to a proper multivariate model~~
   **Done** (see above). Natural follow-ups on the model itself: test
   `draft_pick_overall` as a standalone context feature now that it's
   shown up as a top-3 predictor; try SHAP interaction values to see
   whether opponent-defense and usage features interact (permutation
   importance only shows marginal contribution); and widen the
   leave-one-season-out CV into a small hyperparameter search once there's
   a specific accuracy target to hit rather than a fixed, deliberately
   conservative configuration.
7. ~~Build opponent context at the position/alignment level~~ **Done**:
   `def_epa_allowed_to_position_pre` (opponent's rolling EPA allowed
   specifically on throws to a receiver's own position group — WR, TE, or
   RB — instead of pass defense in aggregate) is in
   `src/features/build_features.py`. It's a small, honest improvement, not
   a breakthrough: for WR/TE receiving yards the bivariate holdout r rose
   from 0.011 (aggregate) to 0.033 (position-specific) — better, but still
   weak on its own — and it didn't crack the top-10 permutation importance
   in any of the three multivariate models, where the aggregate
   `def_pass_epa_allowed_pre` still does. Read this as: opponent pass
   defense, even split by target position, just isn't a strong signal at
   the individual-player weekly level with EPA as the yardstick. A defense
   metric built at the alignment/coverage-shell level (slot vs. perimeter,
   man vs. zone — both available in the already-pulled `ftn_charting` and
   `pbp_participation` data, just not yet used this way) is the more
   promising next attempt, not a finer position split.

## How to rerun this pipeline

```
pip install -r requirements.txt
python -m src.ingest.pull_all            # pulls all free sources into data/raw/
python -m src.build_player_week          # merges into data/processed/player_week_merged.parquet
python -m src.features.build_features    # adds engineered features -> player_week_features.parquet
python -m src.signals.signal_testing     # writes the two CSVs behind the tables above
python -m src.signals.model              # multivariate GBM model + permutation importance
```

Each step prints its own join/coverage diagnostics; `src/config.py` is the
single place that controls the season range and train/holdout split.
