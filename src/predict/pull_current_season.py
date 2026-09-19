"""Pull fresh raw data for a single in-progress season into data/raw/.

Mirrors src/ingest/pull_all.py's sources but for one season, re-run any
time to refresh before predicting (schedules/injuries/snap counts/rosters
all update during the week; re-running this is cheap and safe -- it just
overwrites that season's cached files).

Run: python -m src.predict.pull_current_season 2026
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import NFLVERSE_RELEASES, RAW_DIR  # noqa: E402


def _pull(url: str, out_path: Path, reader=pd.read_parquet, **kwargs) -> bool:
    try:
        df = reader(url, **kwargs)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_path, index=False)
        print(f"[OK] {out_path.name}  rows={len(df)}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[SKIP] {out_path.name}: {exc.__class__.__name__}: {exc}")
        return False


def pull_season(season: int) -> None:
    _pull(NFLVERSE_RELEASES + f"/pbp/play_by_play_{season}.parquet", RAW_DIR / f"pbp_{season}.parquet")
    time.sleep(0.2)
    _pull(NFLVERSE_RELEASES + f"/snap_counts/snap_counts_{season}.parquet", RAW_DIR / f"snap_counts_{season}.parquet")
    time.sleep(0.2)
    _pull(NFLVERSE_RELEASES + f"/injuries/injuries_{season}.parquet", RAW_DIR / f"injuries_{season}.parquet")
    time.sleep(0.2)
    _pull(NFLVERSE_RELEASES + f"/depth_charts/depth_charts_{season}.parquet", RAW_DIR / f"depth_charts_{season}.parquet")
    time.sleep(0.2)
    _pull(NFLVERSE_RELEASES + f"/weekly_rosters/roster_weekly_{season}.csv", RAW_DIR / f"weekly_rosters_{season}.parquet",
          reader=pd.read_csv)
    time.sleep(0.2)
    for stat_type in ["pass", "rec", "rush"]:
        _pull(NFLVERSE_RELEASES + f"/pfr_advstats/advstats_week_{stat_type}_{season}.parquet",
              RAW_DIR / f"pfr_advstats_week_{stat_type}_{season}.parquet")
        time.sleep(0.2)
    _pull(NFLVERSE_RELEASES + "/schedules/games.csv", RAW_DIR / "schedules.parquet", reader=pd.read_csv)
    for stat_type in ["passing", "rushing", "receiving"]:
        _pull(NFLVERSE_RELEASES + f"/nextgen_stats/ngs_{stat_type}.parquet", RAW_DIR / f"ngs_{stat_type}.parquet")
        time.sleep(0.2)
    _pull(NFLVERSE_RELEASES + "/draft_picks/draft_picks.parquet", RAW_DIR / "draft_picks.parquet")
    part_ok = _pull(NFLVERSE_RELEASES + f"/pbp_participation/pbp_participation_{season}.parquet",
                     RAW_DIR / f"pbp_participation_{season}.parquet")
    if not part_ok:
        print("  (routes_run_proxy will be null for this season -- pbp_participation not "
              "published yet, which is normal early in a season)")


if __name__ == "__main__":
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    pull_season(season)
