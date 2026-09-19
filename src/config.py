"""Shared paths and scope constants for the NFL player analytics pipeline."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DOCS_DIR = REPO_ROOT / "docs"
REPORTS_DIR = REPO_ROOT / "reports"

# Seasons where the official weekly `player_stats` target table (the thing we
# are trying to predict) was confirmed available at pull time. Play-by-play,
# NGS, snap counts, injuries, and depth charts are all live through the
# current season, but the target table lags behind them in this mirror as of
# the pull date below, so the modeling dataset is scoped to complete seasons
# only. See docs/source_inventory.md for the full explanation.
PULL_DATE = "2026-09-19"
SEASONS = [2021, 2022, 2023, 2024]
HOLDOUT_SEASON = 2024  # out-of-sample season for signal testing
TRAIN_SEASONS = [s for s in SEASONS if s != HOLDOUT_SEASON]

# FTN Data charting (routes run, screen/motion tags) is only mirrored from
# 2022 onward.
FTN_MIN_SEASON = 2022

SKILL_POSITIONS = ["QB", "RB", "WR", "TE"]

NFLVERSE_RELEASES = "https://github.com/nflverse/nflverse-data/releases/download"
