"""League & tournament catalog + normalized loaders (free football-data.co.uk).

Two free source formats, one normalized results frame:

- **main section** (`mmz4281/<season>/<div>.csv`) — the European leagues, one
  file per season, columns Div/Date/HomeTeam/AwayTeam/FTHG/FTAG/... Reused via
  src/data/football_data_uk.py.
- **new section** (`new/<country>.csv`) — Liga MX, MLS, Argentina, Brazil, …,
  one file across seasons, columns Country/League/Season/Date/Time/Home/Away/
  HG/AG/Res/<closing odds>. These are the currently-live seasons.

Everything downstream (standings, Elo, recent results, per-matchup prediction)
consumes the normalized frame, so a new league is one catalog entry.

Honest scope: these are historical *results* (very current — days old for
live seasons), not a forward schedule. Genuine upcoming fixtures come from the
main-section `fixtures.csv` where present (European; sparse off-season). Live
scheduled fixtures for every league need a keyed provider (The Odds API /
API-Football), which slots behind the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from src.models.ratings import compute_elo

CACHE = Path("data/raw/leagues")
BASE = "https://www.football-data.co.uk"


@dataclass(frozen=True)
class League:
    id: str
    name: str
    region: str
    country: str
    source: str              # "new" or "main"
    code: str                # country file (new) or division code (main)
    main_season: int = 2025  # main-section start year (2025 = 2025/26)


CATALOG: list[League] = [
    # North America (live seasons)
    League("liga_mx", "Liga MX", "North America", "Mexico", "new", "MEX"),
    League("mls", "MLS", "North America", "USA", "new", "USA"),
    # Top-5 Europe (main section; 2025/26 most recent complete season)
    League("epl", "Premier League", "Europe", "England", "main", "E0"),
    League("laliga", "La Liga", "Europe", "Spain", "main", "SP1"),
    League("seriea", "Serie A", "Europe", "Italy", "main", "I1"),
    League("bundesliga", "Bundesliga", "Europe", "Germany", "main", "D1"),
    League("ligue1", "Ligue 1", "Europe", "France", "main", "F1"),
    # More Europe
    League("eredivisie", "Eredivisie", "Europe", "Netherlands", "main", "N1"),
    League("primeira", "Primeira Liga", "Europe", "Portugal", "main", "P1"),
    # South America (live seasons)
    League("argentina", "Liga Profesional", "South America", "Argentina", "new", "ARG"),
    League("brazil", "Brasileirão", "South America", "Brazil", "new", "BRA"),
]

BY_ID = {lg.id: lg for lg in CATALOG}


def get_league(league_id: str) -> League:
    if league_id not in BY_ID:
        raise KeyError(f"unknown league {league_id!r}; known: {sorted(BY_ID)}")
    return BY_ID[league_id]


# --------------------------------------------------------------- loading

def _cache_get(url: str, name: str, refresh: bool = False) -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if refresh or not path.exists():
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        path.write_bytes(resp.content)
    return pd.read_csv(path, encoding="utf-8-sig", on_bad_lines="skip")


def _normalize_new(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.dropna(subset=["Home", "Away", "HG", "AG"]).copy()
    date = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
    return pd.DataFrame({
        "date": date.dt.strftime("%Y-%m-%d"),
        "season": df["Season"].astype(str),
        "home_team": df["Home"].str.strip(),
        "away_team": df["Away"].str.strip(),
        "home_score": df["HG"].astype(float),
        "away_score": df["AG"].astype(float),
        "neutral": False,
    }).dropna(subset=["date"]).sort_values("date")


def _normalize_main(raw: pd.DataFrame, season: str) -> pd.DataFrame:
    df = raw.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"]).copy()
    date = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
    two = date.isna()
    if two.any():
        date.loc[two] = pd.to_datetime(df.loc[two, "Date"], format="%d/%m/%y",
                                       errors="coerce")
    return pd.DataFrame({
        "date": date.dt.strftime("%Y-%m-%d"),
        "season": season,
        "home_team": df["HomeTeam"].str.strip(),
        "away_team": df["AwayTeam"].str.strip(),
        "home_score": df["FTHG"].astype(float),
        "away_score": df["FTAG"].astype(float),
        "neutral": False,
    }).dropna(subset=["date"]).sort_values("date")


def load_results(league: League, refresh: bool = False) -> pd.DataFrame:
    """Normalized results frame for a league (all seasons available)."""
    if league.source == "new":
        raw = _cache_get(f"{BASE}/new/{league.code}.csv",
                         f"new_{league.code}.csv", refresh)
        return _normalize_new(raw)
    code = f"{league.main_season % 100:02d}{(league.main_season + 1) % 100:02d}"
    raw = _cache_get(f"{BASE}/mmz4281/{code}/{league.code}.csv",
                     f"main_{league.code}_{code}.csv", refresh)
    return _normalize_main(raw, f"{league.main_season}/{league.main_season + 1}")


def latest_season(results: pd.DataFrame) -> str:
    return results.sort_values("date")["season"].iloc[-1]


# --------------------------------------------------------------- stats

def standings(results: pd.DataFrame, season: str | None = None) -> list[dict]:
    """League table for a season (points, W-D-L, GF/GA/GD, played)."""
    season = season or latest_season(results)
    s = results[results["season"] == season]
    teams: dict[str, dict] = {}

    def _row(t: str) -> dict:
        return teams.setdefault(t, {"team": t, "played": 0, "won": 0, "drawn": 0,
                                    "lost": 0, "gf": 0, "ga": 0, "points": 0})

    for r in s.itertuples(index=False):
        h, a = _row(r.home_team), _row(r.away_team)
        hg, ag = int(r.home_score), int(r.away_score)
        h["played"] += 1; a["played"] += 1
        h["gf"] += hg; h["ga"] += ag; a["gf"] += ag; a["ga"] += hg
        if hg > ag:
            h["won"] += 1; a["lost"] += 1; h["points"] += 3
        elif hg < ag:
            a["won"] += 1; h["lost"] += 1; a["points"] += 3
        else:
            h["drawn"] += 1; a["drawn"] += 1; h["points"] += 1; a["points"] += 1

    table = list(teams.values())
    for t in table:
        t["gd"] = t["gf"] - t["ga"]
    table.sort(key=lambda t: (-t["points"], -t["gd"], -t["gf"]))
    for i, t in enumerate(table, 1):
        t["rank"] = i
    return table


def recent_results(results: pd.DataFrame, n: int = 10) -> list[dict]:
    tail = results.sort_values("date").tail(n).iloc[::-1]
    return [{
        "date": r.date, "home_team": r.home_team, "away_team": r.away_team,
        "home_score": int(r.home_score), "away_score": int(r.away_score),
    } for r in tail.itertuples(index=False)]


def team_elos(results: pd.DataFrame) -> dict[str, float]:
    """Elo within this league's results (relative strength inside the league)."""
    elo = compute_elo(results)
    latest = latest_season(results)
    teams = set(results[results["season"] == latest]["home_team"]) | \
        set(results[results["season"] == latest]["away_team"])
    return {t: round(elo.ratings.get(t, 1500.0), 1) for t in teams}


def build_ratings(results: pd.DataFrame):
    """Elo + Dixon-Coles rho for a league, computed once and cached by callers."""
    from src.models.bracket import _fit_rho

    elo = compute_elo(results)
    return elo, _fit_rho(results, elo)


def predict_matchup(elo, rho: float, home_team: str, away_team: str,
                    *, neutral: bool = False) -> dict:
    """Model prediction for any two teams in a league (home advantage on by
    default). Reuses the Elo bracket engine — outcome, scoreline grid,
    advancement, goal timing, role-level scorers/assists, and the evidence
    drill-down."""
    from src.models.bracket import TeamStrength, predict_tie
    from src.models.sequence import GoalTimingModel

    for t in (home_team, away_team):
        if t not in elo.ratings:
            raise KeyError(f"unknown team {t!r} for this league")

    def _ts(t: str) -> TeamStrength:
        return TeamStrength(team=t, rank=0, elo=round(elo.ratings[t], 1),
                            n_matches=elo.n_played.get(t, 0),
                            last_played=elo.last_played.get(t, ""))

    tie = predict_tie(elo, rho, GoalTimingModel(), _ts(home_team), _ts(away_team),
                      neutral=neutral)
    tie.pop("winner", None)
    return tie


def upcoming_fixtures(division_code: str, refresh: bool = False) -> list[dict]:
    """Upcoming fixtures for a MAIN-section league from fixtures.csv (with
    odds where present). Empty for new-section leagues and off-season."""
    try:
        fx = _cache_get(f"{BASE}/fixtures.csv", "fixtures.csv", refresh)
    except Exception:  # noqa: BLE001
        return []
    fx = fx[fx["Div"] == division_code]
    out = []
    for r in fx.itertuples(index=False):
        row = {"date": getattr(r, "Date", ""), "time": getattr(r, "Time", ""),
               "home_team": getattr(r, "HomeTeam", ""),
               "away_team": getattr(r, "AwayTeam", "")}
        for k, col in (("odds_home", "PSH"), ("odds_draw", "PSD"),
                       ("odds_away", "PSA")):
            v = getattr(r, col, None)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                row[k] = float(v)
        out.append(row)
    return out
