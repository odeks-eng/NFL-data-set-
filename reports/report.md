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
5. **Everything here is a bivariate test.** These are correlations and
   2-feature linear blends, deliberately kept simple and transparent so
   the "does A beat B" comparisons are easy to audit. A tree-based
   multivariate model (see Next Steps) would almost certainly do better
   than any single number above — that's expected, and not itself
   evidence these simpler signals are wrong.
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
6. **Move from bivariate correlations to a proper multivariate model**
   (gradient-boosted trees are the natural choice given the mix of usage/
   efficiency/context features here) once the team is comfortable with
   what each input signal does and doesn't do on its own — that context is
   exactly what this report is for.

## How to rerun this pipeline

```
pip install -r requirements.txt
python -m src.ingest.pull_all            # pulls all free sources into data/raw/
python -m src.build_player_week          # merges into data/processed/player_week_merged.parquet
python -m src.features.build_features    # adds engineered features -> player_week_features.parquet
python -m src.signals.signal_testing     # writes the two CSVs behind the tables above
```

Each step prints its own join/coverage diagnostics; `src/config.py` is the
single place that controls the season range and train/holdout split.
