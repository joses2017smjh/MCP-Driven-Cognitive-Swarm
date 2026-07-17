"""International results provider — martj42/international_results (free, no key).

~50k men's international matches (1872–present, community-maintained,
updated through the current tournament) plus a shootouts table. This is the
training + ground-truth source for World Cup prediction:

- ``team_match_frame``  → canonical TEAM_MATCH rows (goals only: xg columns
  carry a goals proxy, shots/possession are NaN — disclosed downstream);
- ``wc_matches``        → the target tournament's fixtures, split into
  played (ground truth) and upcoming;
- ``shootout_winners``  → penalty outcomes for drawn knockout ties.

No odds exist in this source, so World Cup predictions run without a market
anchor — that absence is itself one of the ablation axes.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from src.data.interfaces import TEAM_MATCH_COLUMNS, validate_frame

BASE_URL = "https://raw.githubusercontent.com/martj42/international_results/master"
DEFAULT_CACHE = Path("data/raw/international_results")


def _fetch(name: str, cache_dir: Path, refresh: bool = False) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / name
    if refresh or not path.exists():
        resp = requests.get(f"{BASE_URL}/{name}", timeout=60)
        resp.raise_for_status()
        path.write_bytes(resp.content)
    return pd.read_csv(path)


def fetch_results(cache_dir: Path = DEFAULT_CACHE, refresh: bool = False) -> pd.DataFrame:
    """Columns: date, home_team, away_team, home_score, away_score,
    tournament, city, country, neutral."""
    return _fetch("results.csv", cache_dir, refresh)


def fetch_shootouts(cache_dir: Path = DEFAULT_CACHE, refresh: bool = False) -> pd.DataFrame:
    """Columns: date, home_team, away_team, winner (, first_shooter)."""
    return _fetch("shootouts.csv", cache_dir, refresh)


def team_match_frame(
    raw: pd.DataFrame, *, since: str = "2014-01-01"
) -> pd.DataFrame:
    """Canonical long frame from played internationals (NA scores dropped)."""
    df = raw.dropna(subset=["home_score", "away_score"]).copy()
    df = df[df["date"] >= since]
    kickoff = pd.to_datetime(df["date"]).dt.tz_localize("UTC") + pd.Timedelta(hours=18)
    match_id = (
        df["home_team"].str.replace(r"\W", "", regex=True)
        + "-" + df["away_team"].str.replace(r"\W", "", regex=True)
        + "-" + df["date"]
    )
    season = df["date"].str[:4]

    def _side(is_home: bool) -> pd.DataFrame:
        us, them = ("home_team", "away_team") if is_home else ("away_team", "home_team")
        gf, ga = ("home_score", "away_score") if is_home else ("away_score", "home_score")
        return pd.DataFrame({
            "match_id": match_id,
            "kickoff_utc": kickoff,
            "competition": df["tournament"],
            "season": season,
            "stage": "group",
            "team": df[us],
            "opponent": df[them],
            "is_home": is_home,
            "neutral_venue": df["neutral"].astype(bool),
            "goals_for": df[gf].astype(float),
            "goals_against": df[ga].astype(float),
            # goals stand in for xG — this source has no shot data at all
            "xg_for": df[gf].astype(float),
            "xg_against": df[ga].astype(float),
            "shots_for": float("nan"),
            "shots_against": float("nan"),
            "possession": float("nan"),
            "record_time_utc": kickoff + pd.Timedelta(hours=3),
        })

    frame = pd.concat([_side(True), _side(False)], ignore_index=True)
    # the source is date-granular; a team listed twice on one date (rare data
    # quirk) breaks as-of ordering — keep the first entry only, and let
    # match_level_form's inner join drop the orphaned opposite side
    frame = frame.drop_duplicates(subset=["team", "kickoff_utc"], keep="first")
    return validate_frame(frame, TEAM_MATCH_COLUMNS, "TEAM_MATCH")


def wc_matches(
    raw: pd.DataFrame, *, year: int = 2026
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(played, upcoming) World Cup fixtures for the given edition.

    Played rows carry real scores — the ground truth. ``knockout`` is set
    from the calendar (the 48-team 2026 group stage ended June 27)."""
    wc = raw[
        (raw["tournament"] == "FIFA World Cup")
        & (raw["date"].str.startswith(str(year)))
    ].copy()
    ko_start = f"{year}-06-28" if year == 2026 else f"{year}-06-25"
    wc["knockout"] = wc["date"] >= ko_start
    played = wc.dropna(subset=["home_score", "away_score"]).copy()
    upcoming = wc[wc["home_score"].isna()].copy()
    return played, upcoming


def shootout_winners(
    shootouts: pd.DataFrame, *, year: int = 2026
) -> dict[tuple[str, str, str], str]:
    """(date, home, away) → shootout winner, for settling drawn KO ties."""
    rows = shootouts[shootouts["date"].str.startswith(str(year))]
    return {
        (r["date"], r["home_team"], r["away_team"]): r["winner"]
        for _, r in rows.iterrows()
    }
