# Source Inventory

Pull environment note: outbound network access in the build environment is
restricted by an organization egress policy. `github.com`,
`raw.githubusercontent.com`, and PyPI are reachable; direct requests to
`pro-football-reference.com`, ESPN's public JSON API, `the-odds-api.com`, and
weather APIs (open-meteo, etc.) returned `403` from the egress proxy. In
practice this is not very limiting: nflverse republishes NGS, PFR advanced
stats, and FTN Data's charting as flat files on GitHub Releases under an
open license, so nearly everything on the free/open list below was pulled
from **one** canonical host: `github.com/nflverse/nflverse-data`. Anything
that could *not* be reached is flagged explicitly in the "Access" column.

All "pull date" values below are 2026-09-19. All free sources are pulled via
direct HTTPS GET of versioned CSV/Parquet release assets (no scraping,
no ToS issues — this is nflverse's documented, intended distribution
mechanism; `nfl_data_py`/`nflreadr` are thin wrappers around the same URLs).

## 1. Free / open — pulled into this dataset

| Source | Metrics offered | Coverage (years) | Update frequency | Access method | Cost | Reliability notes |
|---|---|---|---|---|---|---|
| nflverse play-by-play (`pbp`) | Every charted play: EPA, WPA, CPOE, air yards, YAC, pass rush/coverage context, participation | 1999–present (2025 complete season confirmed pulled; 2026 in progress, partial) | Live during season (~few times/week), finalized ~48h after final games | `github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.parquet` | Free (CC-BY 4.0 style attribution) | Very reliable; nflverse's own QA passes flow through here first. Source of truth for the target outcome if `player_stats` lags. |
| nflverse weekly player stats (`player_stats`) | Box-score stats + fantasy points (standard/PPR/half) per player-week | Per-year files confirmed present for 2021–2024. **2025 and 2026 per-year files were not yet published at pull time**; the rolling combined file (`player_stats.parquet`) was also stuck at max season 2024 in this environment's mirror. Flagged as a known gap — see Data Dictionary / Known Weaknesses. | Weekly during season | `.../player_stats/player_stats_{year}.parquet` | Free | High — this is the standard fantasy-scoring reference table used across the industry. |
| Next Gen Stats (NGS), official NFL tracking data, mirrored by nflverse | Passing: time to throw, CPOE, aggressiveness. Rushing: RYOE, time behind LOS, 8+ defenders in box rate. Receiving: separation, cushion, YAC above expectation | 2016–2026 (confirmed live through current season) | Weekly | `.../nextgen_stats/ngs_{receiving,passing,rushing}.parquet` | Free | High; official NFL source. Only covers players who see enough volume for NGS to publish (min. attempt/target thresholds), so coverage thins for low-usage players. |
| Snap counts (PFR-derived, mirrored by nflverse) | Offensive/defensive/ST snaps and snap % per player-game | 2012–present (2021–2026 confirmed, current season live) | Weekly | `.../snap_counts/snap_counts_{year}.parquet` | Free | High; matches PFR box scores by construction. |
| Injury reports (official, mirrored by nflverse) | Practice/game status (Questionable/Doubtful/Out), injury body part, by week | 2009–present (2021–2025 confirmed) | Weekly | `.../injuries/injuries_{year}.parquet` | Free | High; official club-submitted reports. Known for boilerplate/generic designations in some seasons — treat status as directional, not precise. |
| Depth charts (official, mirrored by nflverse) | Starter/backup ordering by position, per week | 2001–present | Weekly | `.../depth_charts/depth_charts_{year}.parquet` | Free | Medium — depth chart entries are self-reported by clubs and sometimes stale between real changes. |
| Weekly rosters (`weekly_rosters`) | ID crosswalk (gsis_id, espn_id, pfr_id, sleeper_id, yahoo_id, pff_id...), position, status, team, jersey # | 2002–present | Weekly | `.../weekly_rosters/roster_weekly_{year}.csv` | Free | High; this is the master ID-crosswalk table used to join everything else on `gsis_id`. |
| FTN Data charting, mirrored by nflverse (free tier of a normally-paid product) | **Play-level** charting: formation, personnel, motion, play-action, screen, RPO, blitzers/pass-rushers, drop type, throwaway/contested-ball/drop tags | **2022–present only** (confirmed 2022–2025) | Weekly | `.../ftn_charting/ftn_charting_{year}.parquet` | Free (this specific extract) | Medium. Correction from an earlier draft of this inventory: the free mirror is **play-level** charting keyed on `nflverse_play_id`, not per-player route data. It does not contain a "routes run per player" field — that granularity is part of FTN's/PFF's paid route-charting product, which we did not purchase. See `pbp_participation` below for the free proxy we built instead, and Known Weaknesses in the report for why it's an imperfect substitute. |
| Play participation (`pbp_participation`), mirrored by nflverse | Personnel on the field per play (`offense_players`, `offense_positions`), formation, box count, pass-rush count, target's route type, coverage shell | 2016–present (2021–2024 confirmed) | Weekly | `.../pbp_participation/pbp_participation_{year}.parquet` | Free | High for who-was-on-the-field; used to build `routes_run_proxy` (count of pass plays where a non-lineman was on the field) as our free-data stand-in for true route participation. This over-counts players who stayed in to pass-block instead of running a route, so it's an upper bound, not the real thing — flagged wherever it's used. |
| Pro Football Reference advanced stats, mirrored by nflverse | Pass: pressure-adjusted stats, air yards. Rec: YAC, broken tackles, drop rate. Rush: yards after contact, broken tackles. Def: pass rush/coverage stats | Season-level 2018–present; week-level split by stat type, 2018–present | Weekly (in-season), season file finalized post-season | `.../pfr_advstats/advstats_{season,week}_{pass,rec,rush,def}.parquet` | Free (mirrored under PFR's data-use terms) | High for the underlying box-score-adjacent stats; PFR's "broken tackle"/"drop" judgment calls are subjective, same caveat as FTN. |
| Schedules (`schedules`) | Game metadata: kickoff time, network, roof, surface, divisional game flag, `gameday` — used to derive rest days and travel | 1999–present | Weekly | `.../nflverse-data/releases/download/schedules/games.csv` (via `nfl_data_py.import_schedules`) | Free | High. Static per-game facts; roof/surface known well before kickoff so it's leakage-safe. |
| Historical game odds (moneyline / spread / total, opening + closing, multiple books) | Market context: implied team totals, closing spread movement | 2006–present | Static historical file, not live | `raw.githubusercontent.com/mrcaseb/nfl-data/master/data/nfl_lines_odds.csv.gz` | Free | Medium — game-level only, **not player props**. Useful for implied team total / game script context features, not a props edge on its own. |
| Officials (`officials`) | Referee crew assignments per game | ~2015–present | Weekly | `raw.githubusercontent.com/nflverse/nfldata/master/data/officials.csv` | Free | Collected but not used in v1 feature set — weak, indirect signal (some referees call more/fewer penalties, which is a 2nd-order effect on plays run). Logged as a future exploration, not part of the core dataset. |
| Draft picks, combine, contracts (OverTheCap mirror) | Draft capital, combine testing, contract value/guarantees | Draft/combine 1999–present; contracts (historical) | Static/annual | `.../draft_picks/draft_picks.parquet`, `.../combine/combine.parquet`, `.../contracts/historical_contracts.parquet` | Free | High for draft/combine (official). Contracts are OverTheCap's own estimates for older deals. Used only as slow-moving context (opportunity signal, e.g. rookie draft capital), not week-to-week. |

## 2. Paid — **not pulled**, listed for approval only

None of these were subscribed to or scraped. Per project rules, no paid
source is accessed without explicit approval. This session's egress policy
also does not allow outbound requests to most of these hosts even if a key
were supplied (flagged below), so approval would need to come with a
decision on how the pull actually happens (e.g., run in an environment
with broader network access).

| Source | What it would add beyond the free list | Approx. cost | Reachable from this environment? |
|---|---|---|---|
| PFF (grades, route participation, alignment, coverage scheme) | Play-by-play grades, true route participation independent of FTN's charting, coverage shell tags | Subscription, $39.99/mo (Edge) up to $199.99/mo+ (Elite) at time of writing, prices change | Not tested — pff.com not in the free-tier plan; would need explicit approval before attempting |
| FTN / Fantasy Points Data (premium tier) | Their own built efficiency metrics/API beyond the raw charting file nflverse already mirrors for free | Subscription, ~$30–50/mo | Not tested |
| Sports Info Solutions | Additional charting (pressure, coverage) with different methodology than PFF/FTN, useful for disagreement analysis | License/subscription, contact for pricing | Not tested |
| SumerSports | EPA-style proprietary grades, transparent methodology write-ups | Free tier for articles; API/bulk data is paid | Not tested |
| PlayerProfiler | Athleticism scores (Speed Score, Burst, Agility), opportunity metrics | Subscription, ~$36/yr–$10/mo tiers | Not tested |
| Player-prop odds history (e.g. the-odds-api.com paid tier, or a props archive vendor) | Actual player-prop lines (not just game lines) needed to backtest CLV on props specifically | Free tier is rate-limited/thin; paid tiers ~$30–100+/mo depending on volume | **No** — `api.the-odds-api.com` returned a proxy `403` (org egress policy), independent of payment |
| ESPN pass rush/run stop win rate | Pressure/win-rate stats not covered by the free sources above | Free (public site), but pull path is blocked here | **No** — `site.api.espn.com` returned a proxy `403` |
| Weather at kickoff (temperature, wind, precipitation) | Point-in-time weather instead of just roof/surface | Free (open-meteo, NOAA) | **No** — `archive-api.open-meteo.com` returned a proxy `403` |

**Recommendation:** don't pay for anything yet. The free list already covers
usage (targets, routes, snaps, air yards), efficiency (EPA, separation, YAC,
RYOE), and most context (rest, roof/surface, injury/depth chart status,
implied team total via game odds). The two real gaps are (a) point-in-time
weather and (b) player-prop market lines for CLV backtesting — both are
network-access problems in this environment, not really "need to pay"
problems, so the next step should be re-running this pipeline from an
environment with open egress before reaching for a paid vendor.
