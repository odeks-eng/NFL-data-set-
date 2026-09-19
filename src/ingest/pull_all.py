"""Pull every free/open source into data/raw/ and write a provenance manifest.

Run: python -m src.ingest.pull_all

Every source is pulled straight from its official distribution (nflverse's
GitHub Releases, or the specific upstream repos nflverse itself points at —
see docs/source_inventory.md). Nothing here scrapes a website; everything is
a direct HTTPS GET of a versioned CSV/Parquet file, which is the intended,
documented way to consume this data (it's exactly what the `nfl_data_py`
and `nflreadr` packages do under the hood).
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import (  # noqa: E402
    FTN_MIN_SEASON,
    NFLVERSE_RELEASES,
    PULL_DATE,
    RAW_DIR,
    SEASONS,
)

manifest: list[dict] = []


def _record(name: str, url: str, df: pd.DataFrame | None, error: str | None = None) -> None:
    entry = {
        "source": name,
        "url": url,
        "pull_date": PULL_DATE,
        "rows": None if df is None else len(df),
        "columns": None if df is None else list(df.columns),
        "error": error,
    }
    manifest.append(entry)
    status = "OK" if error is None else "FAILED"
    rows = entry["rows"]
    print(f"[{status}] {name}  rows={rows}  url={url}")


def _save(df: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)


def pull(name: str, url: str, out_path: Path, reader=pd.read_parquet, **kwargs) -> pd.DataFrame | None:
    try:
        df = reader(url, **kwargs)
        _save(df, out_path)
        _record(name, url, df)
        return df
    except Exception as exc:  # noqa: BLE001 - we want to log and continue
        _record(name, url, None, error=f"{exc.__class__.__name__}: {exc}")
        return None


def pull_per_season(name_fmt: str, url_fmt: str, out_fmt: str, seasons=SEASONS, reader=pd.read_parquet, **kwargs):
    for season in seasons:
        pull(
            name_fmt.format(season=season),
            url_fmt.format(season=season),
            RAW_DIR / out_fmt.format(season=season),
            reader=reader,
            **kwargs,
        )
        time.sleep(0.2)  # be polite to GitHub's CDN


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Play-by-play (source of truth for EPA/CPOE and a fallback target table)
    pull_per_season(
        "pbp_{season}",
        NFLVERSE_RELEASES + "/pbp/play_by_play_{season}.parquet",
        "pbp_{season}.parquet",
    )

    # 1b. Play participation (personnel on field per play) -- used to build a
    # free-data proxy for routes run, since true route charting is paywalled.
    pull_per_season(
        "pbp_participation_{season}",
        NFLVERSE_RELEASES + "/pbp_participation/pbp_participation_{season}.parquet",
        "pbp_participation_{season}.parquet",
    )

    # 2. Weekly player stats (the target outcome table)
    pull_per_season(
        "player_stats_{season}",
        NFLVERSE_RELEASES + "/player_stats/player_stats_{season}.parquet",
        "player_stats_{season}.parquet",
    )

    # 3. Next Gen Stats (combined multi-year files, filtered later)
    for stat_type in ["passing", "rushing", "receiving"]:
        pull(
            f"ngs_{stat_type}",
            NFLVERSE_RELEASES + f"/nextgen_stats/ngs_{stat_type}.parquet",
            RAW_DIR / f"ngs_{stat_type}.parquet",
        )

    # 4. Snap counts
    pull_per_season(
        "snap_counts_{season}",
        NFLVERSE_RELEASES + "/snap_counts/snap_counts_{season}.parquet",
        "snap_counts_{season}.parquet",
    )

    # 5. Injuries
    pull_per_season(
        "injuries_{season}",
        NFLVERSE_RELEASES + "/injuries/injuries_{season}.parquet",
        "injuries_{season}.parquet",
    )

    # 6. Depth charts
    pull_per_season(
        "depth_charts_{season}",
        NFLVERSE_RELEASES + "/depth_charts/depth_charts_{season}.parquet",
        "depth_charts_{season}.parquet",
    )

    # 7. Weekly rosters (ID crosswalk)
    pull_per_season(
        "weekly_rosters_{season}",
        NFLVERSE_RELEASES + "/weekly_rosters/roster_weekly_{season}.csv",
        "weekly_rosters_{season}.parquet",
        reader=pd.read_csv,
    )

    # 8. FTN charting (2022+)
    pull_per_season(
        "ftn_charting_{season}",
        NFLVERSE_RELEASES + "/ftn_charting/ftn_charting_{season}.parquet",
        "ftn_charting_{season}.parquet",
        seasons=[s for s in SEASONS if s >= FTN_MIN_SEASON],
    )

    # 9. PFR advanced stats, week-level, per stat type
    for stat_type in ["pass", "rec", "rush", "def"]:
        pull_per_season(
            f"pfr_advstats_week_{stat_type}_{{season}}",
            NFLVERSE_RELEASES + f"/pfr_advstats/advstats_week_{stat_type}_{{season}}.parquet",
            f"pfr_advstats_week_{stat_type}_{{season}}.parquet",
        )

    # 10. Schedules (rest days, roof, surface, divisional game)
    pull(
        "schedules",
        NFLVERSE_RELEASES + "/schedules/games.csv",
        RAW_DIR / "schedules.parquet",
        reader=pd.read_csv,
    )

    # 11. Historical game odds/lines (game-level market context)
    pull(
        "game_odds_lines",
        "https://raw.githubusercontent.com/mrcaseb/nfl-data/master/data/nfl_lines_odds.csv.gz",
        RAW_DIR / "game_odds_lines.parquet",
        reader=pd.read_csv,
        compression="gzip",
    )

    # 12. Draft picks / combine (slow-moving opportunity context)
    pull(
        "draft_picks",
        NFLVERSE_RELEASES + "/draft_picks/draft_picks.parquet",
        RAW_DIR / "draft_picks.parquet",
    )
    pull(
        "combine",
        NFLVERSE_RELEASES + "/combine/combine.parquet",
        RAW_DIR / "combine.parquet",
    )

    manifest_path = RAW_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nWrote manifest with {len(manifest)} entries to {manifest_path}")

    failures = [m for m in manifest if m["error"]]
    if failures:
        print(f"\n{len(failures)} pulls FAILED:")
        for f in failures:
            print(f"  - {f['source']}: {f['error']}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
