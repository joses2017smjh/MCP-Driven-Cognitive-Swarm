"""The Odds API client — genuine upcoming fixtures + live bookmaker odds.

Free tier is 500 credits/month, so this client is deliberately frugal:

- every response is disk-cached with a TTL (default 6 h), so repeated page
  loads cost nothing;
- credits burn as (markets x regions) per request, so the defaults are
  narrow (h2h, one region);
- ``/v4/sports`` does not count against the quota, so key resolution is free;
- every response's ``x-requests-remaining`` header is captured and exposed,
  so the app can show the remaining budget instead of silently exhausting it.

Without ``ODDS_API_KEY`` the client raises ``OddsAPIUnavailable``, which
callers treat as a degraded source — the same path a down MCP server takes.

Sport keys verified against the provider's coverage list: Liga MX is
``soccer_mexico_ligamx`` and MLS is ``soccer_usa_mls``; the rest follow the
same convention and are re-checked at runtime against the live sports list.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

BASE = "https://api.the-odds-api.com/v4"
CACHE = Path("data/raw/odds_api")
DEFAULT_TTL_S = 6 * 3600

# our league id -> The Odds API sport key
SPORT_KEYS: dict[str, str] = {
    "liga_mx": "soccer_mexico_ligamx",
    "mls": "soccer_usa_mls",
    "epl": "soccer_epl",
    "laliga": "soccer_spain_la_liga",
    "seriea": "soccer_italy_serie_a",
    "bundesliga": "soccer_germany_bundesliga",
    "ligue1": "soccer_france_ligue_one",
    "eredivisie": "soccer_netherlands_eredivisie",
    "primeira": "soccer_portugal_primeira_liga",
    "argentina": "soccer_argentina_primera_division",
    "brazil": "soccer_brazil_campeonato",
}


class OddsAPIUnavailable(RuntimeError):
    """No API key configured, or the provider could not be reached."""


@dataclass
class OddsAPIClient:
    api_key: str | None = None
    ttl_s: float = DEFAULT_TTL_S
    regions: str = "us"          # one region keeps credit burn at 1x
    credits_remaining: int | None = field(default=None, init=False)
    credits_used: int | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("ODDS_API_KEY")

    # ------------------------------------------------------------ internals

    def _require_key(self) -> str:
        if not self.api_key:
            raise OddsAPIUnavailable(
                "ODDS_API_KEY is not set — get a free key at the-odds-api.com "
                "(500 credits/month) and export it to enable live fixtures/odds"
            )
        return self.api_key

    def _cached(self, name: str) -> Any | None:
        path = CACHE / name
        if path.exists() and (time.time() - path.stat().st_mtime) < self.ttl_s:
            return json.loads(path.read_text())
        return None

    def _store(self, name: str, payload: Any) -> None:
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / name).write_text(json.dumps(payload))

    def _get(self, path: str, params: dict[str, str], cache_name: str,
             use_quota: bool = True) -> Any:
        hit = self._cached(cache_name)
        if hit is not None:
            return hit
        params = {**params, "apiKey": self._require_key()}
        resp = requests.get(f"{BASE}{path}", params=params, timeout=30)
        if resp.status_code == 401:
            raise OddsAPIUnavailable("ODDS_API_KEY rejected (401)")
        if resp.status_code == 429:
            raise OddsAPIUnavailable("Odds API quota exhausted (429)")
        resp.raise_for_status()
        if use_quota:
            for attr, header in (("credits_remaining", "x-requests-remaining"),
                                 ("credits_used", "x-requests-used")):
                value = resp.headers.get(header)
                if value is not None:
                    setattr(self, attr, int(float(value)))
        payload = resp.json()
        self._store(cache_name, payload)
        return payload

    # --------------------------------------------------------------- public

    def sports(self) -> list[dict]:
        """Available sports/leagues. Free — does not consume quota."""
        return self._get("/sports", {}, "sports.json", use_quota=False)

    def resolve_sport_key(self, league_id: str) -> str:
        """Our league id -> provider sport key, verified against the live list."""
        key = SPORT_KEYS.get(league_id)
        if key is None:
            raise KeyError(f"no Odds API sport key mapped for {league_id!r}")
        try:
            available = {s["key"] for s in self.sports()}
            if key not in available:
                raise OddsAPIUnavailable(
                    f"sport key {key!r} not currently offered by the provider "
                    "(league may be out of season)"
                )
        except OddsAPIUnavailable:
            raise
        except Exception:  # noqa: BLE001 — verification is best-effort
            pass
        return key

    def upcoming(self, league_id: str, markets: str = "h2h") -> list[dict]:
        """Upcoming fixtures with odds for a league, newest cache honoured.

        Returns rows shaped like the UI's fixture list: date, time, teams and
        best-available decimal odds per outcome.
        """
        sport = self.resolve_sport_key(league_id)
        cache_name = f"odds_{sport}_{markets}_{self.regions}.json"
        events = self._get(f"/sports/{sport}/odds",
                           {"regions": self.regions, "markets": markets,
                            "oddsFormat": "decimal"},
                           cache_name)
        return [self._normalize_event(e) for e in events]

    @staticmethod
    def _normalize_event(event: dict) -> dict:
        commence = str(event.get("commence_time", ""))
        row: dict[str, Any] = {
            "date": commence[:10],
            "time": commence[11:16],
            "home_team": event.get("home_team", ""),
            "away_team": event.get("away_team", ""),
            "commence_time": commence,
            "source": "the-odds-api",
        }
        # take the first bookmaker offering h2h; consensus is computed
        # downstream by the existing de-vig helpers when needed
        for book in event.get("bookmakers", []):
            for market in book.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    name, price = outcome.get("name"), outcome.get("price")
                    if name == row["home_team"]:
                        row["odds_home"] = price
                    elif name == row["away_team"]:
                        row["odds_away"] = price
                    elif name == "Draw":
                        row["odds_draw"] = price
                row["bookmaker"] = book.get("title")
                return row
        return row

    def budget(self) -> dict[str, int | None]:
        return {"credits_remaining": self.credits_remaining,
                "credits_used": self.credits_used}
