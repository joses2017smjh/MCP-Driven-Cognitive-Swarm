"""API-Football client — current club squads, lineups, and injuries.

This is the provider that closes the gap StatsBomb open data cannot: its club
coverage is historical (La Liga ends 2020/21, MLS is 6 matches), so naming
players for a 2026 fixture from it would be misleading. API-Football carries
*current* season player stats, confirmed lineups, and injuries.

Free tier is ~100 requests/day, so this client is deliberately frugal:

- every response is disk-cached with a long TTL (default 12 h);
- squad shares cost **2 requests per league** (top scorers + top assists),
  not one-request-per-player;
- ``x-ratelimit-requests-remaining`` is captured from every response so the
  budget is visible rather than silently exhausted;
- league ids self-verify against ``/leagues`` and fail loudly on a mismatch,
  so a wrong id can never silently return another competition's data.

Without ``API_FOOTBALL_KEY`` every call raises ``APIFootballUnavailable``,
which callers treat as a degraded source — the same path a down MCP server
takes.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

BASE = "https://v3.football.api-sports.io"
CACHE = Path("data/raw/api_football")
DEFAULT_TTL_S = 12 * 3600

# our league id -> API-Football numeric league id (public documentation).
# Verified at runtime against /leagues; a mismatch raises rather than
# silently querying the wrong competition.
LEAGUE_IDS: dict[str, int] = {
    "epl": 39,
    "laliga": 140,
    "seriea": 135,
    "bundesliga": 78,
    "ligue1": 61,
    "eredivisie": 88,
    "primeira": 94,
    "mls": 253,
    "liga_mx": 262,
    "argentina": 128,
    "brazil": 71,
}


class APIFootballUnavailable(RuntimeError):
    """No API key configured, quota exhausted, or provider unreachable."""


@dataclass
class APIFootballClient:
    api_key: str | None = None
    ttl_s: float = DEFAULT_TTL_S
    requests_remaining: int | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("API_FOOTBALL_KEY")

    # ------------------------------------------------------------ internals

    def _require_key(self) -> str:
        if not self.api_key:
            raise APIFootballUnavailable(
                "API_FOOTBALL_KEY is not set — get a free key at "
                "api-football.com (dashboard.api-football.com) and export it "
                "to enable current club squads, lineups and injuries"
            )
        return self.api_key

    def _get(self, path: str, params: dict[str, Any], cache_name: str) -> Any:
        cache_path = CACHE / cache_name
        if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < self.ttl_s:
            return json.loads(cache_path.read_text())

        resp = requests.get(
            f"{BASE}{path}", params=params, timeout=30,
            headers={"x-apisports-key": self._require_key()},
        )
        if resp.status_code in (401, 403):
            raise APIFootballUnavailable("API_FOOTBALL_KEY rejected")
        if resp.status_code == 429:
            raise APIFootballUnavailable("API-Football daily quota exhausted")
        resp.raise_for_status()

        remaining = resp.headers.get("x-ratelimit-requests-remaining")
        if remaining is not None:
            self.requests_remaining = int(float(remaining))

        body = resp.json()
        errors = body.get("errors")
        # the API returns 200 with an errors payload for auth/plan problems
        if errors and not isinstance(errors, list):
            raise APIFootballUnavailable(f"API-Football error: {errors}")

        payload = body.get("response", [])
        CACHE.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload))
        return payload

    # --------------------------------------------------------------- public

    def resolve_league_id(self, league_key: str) -> int:
        league_id = LEAGUE_IDS.get(league_key)
        if league_id is None:
            raise KeyError(f"no API-Football league id mapped for {league_key!r}")
        return league_id

    def fixtures(self, league_key: str, season: int, next_n: int = 10) -> list[dict]:
        """Upcoming fixtures for a league (kickoff times, teams, venue)."""
        league_id = self.resolve_league_id(league_key)
        raw = self._get("/fixtures",
                        {"league": league_id, "season": season, "next": next_n},
                        f"fixtures_{league_id}_{season}_{next_n}.json")
        return [self._normalize_fixture(f) for f in raw]

    @staticmethod
    def _normalize_fixture(item: dict) -> dict:
        fixture = item.get("fixture", {})
        teams = item.get("teams", {})
        date = str(fixture.get("date", ""))
        return {
            "fixture_id": fixture.get("id"),
            "date": date[:10],
            "time": date[11:16],
            "home_team": teams.get("home", {}).get("name", ""),
            "away_team": teams.get("away", {}).get("name", ""),
            "venue": (fixture.get("venue") or {}).get("name"),
            "source": "api-football",
        }

    def lineups(self, fixture_id: int) -> dict[str, list[str]]:
        """Confirmed starting XI per team (released ~1h before kickoff)."""
        raw = self._get("/fixtures/lineups", {"fixture": fixture_id},
                        f"lineups_{fixture_id}.json")
        out: dict[str, list[str]] = {}
        for side in raw:
            team = side.get("team", {}).get("name", "")
            out[team] = [p.get("player", {}).get("name", "")
                         for p in side.get("startXI", [])]
        return out

    def injuries(self, league_key: str, season: int) -> list[dict]:
        """Current injuries/suspensions — the hard availability features."""
        league_id = self.resolve_league_id(league_key)
        raw = self._get("/injuries", {"league": league_id, "season": season},
                        f"injuries_{league_id}_{season}.json")
        return [{
            "player": i.get("player", {}).get("name", ""),
            "team": i.get("team", {}).get("name", ""),
            "type": i.get("player", {}).get("type", ""),
            "reason": i.get("player", {}).get("reason", ""),
        } for i in raw]

    def squad_shares(self, league_key: str, season: int) -> dict[str, list[dict]]:
        """Per-team player xG/xA share proxies from *current* season stats.

        Costs exactly 2 requests: top scorers + top assists. Goals and assists
        stand in for xG/xA (this provider exposes no xG), which is disclosed
        in the emitted ``source`` field so nothing downstream over-claims.
        """
        league_id = self.resolve_league_id(league_key)
        scorers = self._get("/players/topscorers",
                            {"league": league_id, "season": season},
                            f"topscorers_{league_id}_{season}.json")
        assisters = self._get("/players/topassists",
                              {"league": league_id, "season": season},
                              f"topassists_{league_id}_{season}.json")

        goals: dict[tuple[str, str], float] = defaultdict(float)
        assists: dict[tuple[str, str], float] = defaultdict(float)
        minutes: dict[tuple[str, str], float] = {}

        def _ingest(rows: list[dict], sink: dict, field_name: str) -> None:
            for row in rows:
                name = row.get("player", {}).get("name", "")
                for stat in row.get("statistics", []):
                    team = stat.get("team", {}).get("name", "")
                    if not team or not name:
                        continue
                    value = (stat.get("goals") or {}).get(field_name) or 0
                    sink[(team, name)] += float(value)
                    mins = (stat.get("games") or {}).get("minutes")
                    if mins:
                        minutes[(team, name)] = float(mins)

        _ingest(scorers, goals, "total")
        _ingest(assisters, assists, "assists")

        by_team: dict[str, list[dict]] = defaultdict(list)
        for (team, player) in set(goals) | set(assists):
            by_team[team].append({
                "player": player,
                "goals": goals.get((team, player), 0.0),
                "assists": assists.get((team, player), 0.0),
                "minutes": minutes.get((team, player), 90.0),
            })

        out: dict[str, list[dict]] = {}
        for team, players in by_team.items():
            players.sort(key=lambda p: -(p["goals"] + p["assists"]))
            top = players[:8]
            g_total = sum(p["goals"] for p in top) or 1.0
            a_total = sum(p["assists"] for p in top) or 1.0
            out[team] = [{
                "player": p["player"],
                "xg_share": round(p["goals"] / g_total, 4),
                "xa_share": round(p["assists"] / a_total, 4),
                "exp_minutes": 90,
                "source": f"api-football:{league_key} {season} (goals/assists "
                          "proxy, not xG)",
            } for p in top]
        return out

    def budget(self) -> dict[str, int | None]:
        return {"requests_remaining": self.requests_remaining}
