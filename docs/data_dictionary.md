# Data Dictionary — `data/processed/player_week_features.parquet`

Key: **`gsis_id` + `season` + `week`** (one row per skill-position player-week,
`season_type` in `{REG, POST}`; signal testing uses `REG` only). 22,579 rows,
204 columns, seasons 2021–2024.

Naming convention for engineered features — read this before the column
tables below:

| Suffix | Meaning |
|---|---|
| *(none)* | Raw value for **this week** (the outcome, if used as a target — never use a bare column as a predictor of itself) |
| `_r3` | Mean over the player's **prior** 3 games this season (shifted 1 game, so week N excludes week N) |
| `_r5` | Mean over the player's **prior** 5 games this season |
| `_season_pre` | Expanding mean over **all prior** games this season (season-to-date, excluding the current week) |
| `_std_dev_pre` | Rolling std-dev over the prior 5 games — a volatility/consistency measure |
| `_pre` (team/opponent context) | Same causal shift, applied to team- or opponent-level aggregates instead of player-level ones |

Every `_r3` / `_r5` / `_season_pre` / `_pre` column is safe to use as a
predictor of that week's outcome. **Never** use the bare (unsuffixed) version
of a usage/efficiency stat as a predictor — it's part of the outcome you're
trying to predict, not information you had before kickoff.

## Identity / join columns

| Column | Description |
|---|---|
| `gsis_id` | Master player ID (also the join key) |
| `player_name`, `player_display_name` | Player name (as of that week's roster) |
| `position`, `position_group` | Player position |
| `recent_team`, `opponent_team` | Team codes for that week's game |
| `season`, `week`, `season_type` | Season, week number, REG/POST |

## Target / outcome columns (raw weekly box score — from nflverse `player_stats`)

`completions`, `attempts`, `passing_yards`, `passing_tds`, `interceptions`,
`passing_epa`, `carries`, `rushing_yards`, `rushing_tds`, `rushing_epa`,
`receptions`, `targets`, `receiving_yards`, `receiving_tds`, `receiving_epa`,
`target_share`, `air_yards_share`, `wopr`, `racr`, `pacr`, `dakota`,
`fantasy_points`, `fantasy_points_ppr`.

`wopr` (Weighted Opportunity Rating) and `dakota` are themselves
nflverse-published **blended** metrics (wopr = 1.5·target_share +
0.7·air_yards_share; dakota blends EPA and CPOE for QBs) — worth knowing
before "discovering" that a blend beats a single input; nflverse already
built the obvious ones.

## Usage features (see suffix table above for the `_r3`/`_r5`/`_season_pre` versions)

| Base column | Description | Source |
|---|---|---|
| `target_share`, `air_yards_share`, `wopr` | Share of team's targets / air yards; blended opportunity score | nflverse `player_stats` |
| `offense_pct` | Snap share (offensive snaps ÷ team offensive plays) | PFR snap counts, joined via `pfr_id` crosswalk |
| `routes_run_proxy` | **Free-data proxy** for routes run: count of pass plays where this player (a non-lineman) was on the field | Built from `pbp_participation`; see Known Weaknesses — this over-counts players who stayed in to block |
| `target_per_route` | `targets / routes_run_proxy` | Derived |
| `yards_per_route_run` | `receiving_yards / routes_run_proxy` | Derived |
| `rz_targets`, `rz_carries` | Raw count of targets/carries inside the opponent 20 | Derived from play-by-play |
| `rz_target_share`, `rz_carry_share` | Player's red zone touches ÷ team's red zone pass/rush attempts that week | Derived |

## Efficiency / talent features

| Base column | Description | Source |
|---|---|---|
| `ngs_rec_avg_separation`, `ngs_rec_avg_cushion` | Average separation/cushion at catch point (yards) | NGS receiving |
| `ngs_rec_avg_yac_above_expectation` | YAC above what an average player would get given the catch location | NGS receiving |
| `ngs_pass_completion_percentage_above_expectation` (CPOE) | QB completion % above expectation given throw difficulty | NGS passing |
| `ngs_rush_rush_yards_over_expected_per_att` (RYOE/att) | Rush yards over expectation, per attempt, given blocking/box count | NGS rushing |
| `pfr_rec_receiving_broken_tackles`, `pfr_rec_receiving_drop`, `pfr_rec_receiving_drop_pct` | Broken tackles forced, drops, drop rate | PFR advanced stats, joined via `pfr_id` crosswalk |
| `pfr_rush_rushing_yards_after_contact`, `_avg` | Yards after first contact | PFR advanced stats |
| `pfr_pass_times_pressured`, `_pct`, `times_sacked`, `times_hurried`, `times_hit` | O-line/pressure context for the QB | PFR advanced stats |

## Context features (known pre-kickoff — safe to use unshifted)

| Column | Description | Source |
|---|---|---|
| `is_home`, `rest_days`, `opp_rest_days` | Home/away, days of rest for each team | nflverse `schedules` |
| `roof`, `surface`, `temp`, `wind` | Stadium roof type, surface, kickoff temperature (°F) and wind (mph) — `temp`/`wind` are `NaN` for domes, which is correct, not missing data | nflverse `schedules` |
| `div_game` | Divisional matchup flag | nflverse `schedules` |
| `spread_line`, `total_line`, `team_moneyline` | Closing market lines for the game | nflverse `schedules` |
| `team_implied_total` | Derived: `total_line/2 ± spread_line/2` depending on home/away and favorite | Derived |
| `report_status`, `report_primary_injury`, `practice_status` | Official injury report for that week (status heading into the game) | nflverse `injuries` |
| `depth_position`, `formation` | Depth-chart slot | nflverse `depth_charts` |
| `draft_round`, `draft_pick_overall` | Draft capital (career-level context, not week-varying) | nflverse `draft_picks` |
| `team_pass_rate_pre`, `team_off_epa_per_play_pre`, `team_plays_pre` | This player's own team's rolling pace/tendency through the prior week | Derived from play-by-play |
| `def_pass_epa_allowed_pre`, `def_rush_epa_allowed_pre` | **Opponent's** rolling defensive EPA allowed through the prior week — the matchup-difficulty signal | Derived from play-by-play |

## Known coverage limitations (see `data/processed/feature_coverage.csv` and `join_quality_log.csv` for exact numbers)

- **NGS columns** only populate for players/games meeting the NFL's own
  minimum-volume threshold for publishing a reliable tracking average.
  Coverage for `ngs_rec_avg_separation` among all WR/TE/RB weeks with at
  least 1 target is ~30%, rising to ~73% once restricted to players with
  80+ season targets — this is a real coverage gap, not a join bug (verified
  by manually checking a full-season workload player, who was ~95% covered).
- **Snap counts / PFR advanced stats** are joined through a `pfr_id`
  crosswalk built from `weekly_rosters`, which only has a non-null `pfr_id`
  for ~64% of player-week rows. Coverage after the join, restricted to
  skill positions, is still ~75–93% because the missing 36% skews toward
  players who also have few offensive snaps.
- **`routes_run_proxy`** is a free-data stand-in, not real route charting —
  see Usage table above and Known Weaknesses in `reports/report.md`.
- **Injury report join**: a player not appearing in `injuries` that week
  means "not on the report" (presumed healthy), not "missing data."
