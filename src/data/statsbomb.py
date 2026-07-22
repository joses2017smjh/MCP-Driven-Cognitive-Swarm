"""StatsBomb open data — free, licensed player-event data (no scraping).

Plain JSON downloads from github.com/statsbomb/open-data. This is the source
that replaces role-level scorer/assist placeholders with **real named
players**, because it carries every shot's xG and the key pass that created
it. Covered competitions include the Women's World Cup 2019 & 2023, Women's
Euro 2022 & 2025, FA WSL, NWSL, Liga F, Frauen Bundesliga, plus MLS and the
major men's competitions.

Attribution: data provided by StatsBomb under their open-data licence; see
https://github.com/statsbomb/open-data for the user agreement.

Pipeline:
    competitions.json -> matches/{comp}/{season}.json -> events/{match}.json

Per player we derive, from real events:
    xg  = sum of that player's shot xG
    xa  = sum of the xG of shots their key pass created
then normalize within a team to the shares the Poisson allocator expects.
Event files are ~3 MB each, so everything is disk-cached and the derived
shares are written to a small artifact that is cheap to ship and reload.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import requests

RAW = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
CACHE = Path("data/raw/statsbomb")
SHARES_ARTIFACT = Path("data/artifacts/player_shares.json")
TOP_N_PLAYERS = 8


def _get_json(url: str, cache_name: str, refresh: bool = False) -> Any:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / cache_name
    if refresh or not path.exists():
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        path.write_bytes(resp.content)
    return json.loads(path.read_text())


def normalize_team(name: str) -> str:
    """'Spain Women's' -> 'Spain' so StatsBomb names join our team names."""
    return name.replace(" Women's", "").replace(" WFC", "").strip()


def fetch_competitions(refresh: bool = False) -> list[dict]:
    return _get_json(f"{RAW}/competitions.json", "competitions.json", refresh)


def resolve_competition(competition_name: str, season_name: str) -> tuple[int, int]:
    for c in fetch_competitions():
        if (c["competition_name"] == competition_name
                and c["season_name"] == season_name):
            return c["competition_id"], c["season_id"]
    raise KeyError(f"no StatsBomb open data for {competition_name} {season_name}")


def fetch_matches(competition_id: int, season_id: int,
                  refresh: bool = False) -> list[dict]:
    return _get_json(f"{RAW}/matches/{competition_id}/{season_id}.json",
                     f"matches_{competition_id}_{season_id}.json", refresh)


def fetch_events(match_id: int, refresh: bool = False) -> list[dict]:
    return _get_json(f"{RAW}/events/{match_id}.json",
                     f"events_{match_id}.json", refresh)


def _accumulate(events: list[dict], xg: dict, xa: dict, apps: dict) -> None:
    """Add one match's player xG / xA (by key pass) to the running totals."""
    by_id = {e["id"]: e for e in events}
    for e in events:
        if e.get("player") and e.get("team"):
            apps[(normalize_team(e["team"]["name"]), e["player"]["name"])] = True
        if e["type"]["name"] != "Shot":
            continue
        shot = e.get("shot", {})
        value = float(shot.get("statsbomb_xg") or 0.0)
        if not value or not e.get("player"):
            continue
        team = normalize_team(e["team"]["name"])
        xg[(team, e["player"]["name"])] += value
        key_pass = by_id.get(shot.get("key_pass_id"))
        if key_pass and key_pass.get("player"):
            xa[(normalize_team(key_pass["team"]["name"]),
                key_pass["player"]["name"])] += value


def build_player_shares(
    competition_name: str, season_name: str, *,
    teams: list[str] | None = None, refresh: bool = False,
) -> dict[str, list[dict]]:
    """Per-team, per-player xG/xA shares derived from real event data.

    ``teams`` (normalized names) limits the download to those teams' matches —
    each event file is ~3 MB, so restricting matters.
    """
    comp_id, season_id = resolve_competition(competition_name, season_name)
    matches = fetch_matches(comp_id, season_id, refresh)
    wanted = set(teams) if teams else None

    xg: dict[tuple[str, str], float] = defaultdict(float)
    xa: dict[tuple[str, str], float] = defaultdict(float)
    apps: dict[tuple[str, str], bool] = {}
    team_matches: dict[str, int] = defaultdict(int)

    for m in matches:
        home = normalize_team(m["home_team"]["home_team_name"])
        away = normalize_team(m["away_team"]["away_team_name"])
        if wanted and not ({home, away} & wanted):
            continue
        try:
            events = fetch_events(m["match_id"], refresh)
        except Exception:  # noqa: BLE001 — a missing event file must not abort
            continue
        team_matches[home] += 1
        team_matches[away] += 1
        _accumulate(events, xg, xa, apps)

    by_team: dict[str, list[dict]] = defaultdict(list)
    for (team, player), value in xg.items():
        by_team[team].append({"player": player, "xg": value,
                              "xa": xa.get((team, player), 0.0)})
    # players who only created chances still deserve an assist share
    for (team, player), value in xa.items():
        if not any(p["player"] == player for p in by_team[team]):
            by_team[team].append({"player": player, "xg": 0.0, "xa": value})

    out: dict[str, list[dict]] = {}
    for team, players in by_team.items():
        if wanted and team not in wanted:
            continue
        players.sort(key=lambda p: -(p["xg"] + p["xa"]))
        top = players[:TOP_N_PLAYERS]
        xg_total = sum(p["xg"] for p in top) or 1.0
        xa_total = sum(p["xa"] for p in top) or 1.0
        out[team] = [{
            "player": p["player"],
            "xg_share": round(p["xg"] / xg_total, 4),
            "xa_share": round(p["xa"] / xa_total, 4),
            "exp_minutes": 90,
            "source": f"statsbomb:{competition_name} {season_name}",
        } for p in top]
    return out


# ------------------------------------------------------------- artifact

def save_shares(shares: dict[str, list[dict]],
                path: Path = SHARES_ARTIFACT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_shares(path)
    existing.update(shares)
    path.write_text(json.dumps(existing, indent=1, sort_keys=True))
    return path


def load_shares(path: Path = SHARES_ARTIFACT) -> dict[str, list[dict]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())
