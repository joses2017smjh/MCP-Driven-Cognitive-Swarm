"""Tests: StatsBomb open data + The Odds API client.

StatsBomb aggregation is tested on synthetic event payloads (no network);
the Odds API client is tested for key handling, caching, normalization, and
graceful degradation — all without spending a single credit.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

from src.data.odds_api import OddsAPIClient, OddsAPIUnavailable
from src.data.statsbomb import _accumulate, load_shares, normalize_team, save_shares


# ------------------------------------------------------------- statsbomb

def _shot(player: str, team: str, xg: float, eid: str, key_pass: str | None = None):
    shot = {"statsbomb_xg": xg}
    if key_pass:
        shot["key_pass_id"] = key_pass
    return {"id": eid, "type": {"name": "Shot"}, "player": {"name": player},
            "team": {"name": team}, "shot": shot}


def _pass(player: str, team: str, eid: str):
    return {"id": eid, "type": {"name": "Pass"}, "player": {"name": player},
            "team": {"name": team}, "pass": {}}


def test_normalize_team_strips_womens_suffix() -> None:
    assert normalize_team("Spain Women's") == "Spain"
    assert normalize_team("United States Women's") == "United States"
    assert normalize_team("Arsenal") == "Arsenal"


def test_accumulate_credits_xg_to_shooter_and_xa_to_key_passer() -> None:
    events = [
        _pass("Putellas", "Spain Women's", "p1"),
        _shot("Gonzalez", "Spain Women's", 0.4, "s1", key_pass="p1"),
        _shot("Gonzalez", "Spain Women's", 0.2, "s2"),          # unassisted
    ]
    xg, xa, apps = defaultdict(float), defaultdict(float), {}
    _accumulate(events, xg, xa, apps)
    assert xg[("Spain", "Gonzalez")] == pytest.approx(0.6)
    # the assist carries the xG of the shot it created, not the whole match
    assert xa[("Spain", "Putellas")] == pytest.approx(0.4)
    assert ("Spain", "Gonzalez") in apps and ("Spain", "Putellas") in apps


def test_accumulate_ignores_shots_without_xg_or_player() -> None:
    events = [
        {"id": "x", "type": {"name": "Shot"}, "team": {"name": "Spain Women's"},
         "shot": {"statsbomb_xg": 0.5}},                        # no player
        _shot("Ghost", "Spain Women's", 0.0, "s0"),             # zero xG
    ]
    xg, xa, apps = defaultdict(float), defaultdict(float), {}
    _accumulate(events, xg, xa, apps)
    assert not xg


def test_shares_artifact_roundtrip_and_merge(tmp_path: Path) -> None:
    path = tmp_path / "shares.json"
    save_shares({"Spain": [{"player": "A", "xg_share": 1.0}]}, path)
    save_shares({"England": [{"player": "B", "xg_share": 1.0}]}, path)
    merged = load_shares(path)
    assert set(merged) == {"Spain", "England"}          # merge, not overwrite
    save_shares({"Spain": [{"player": "C", "xg_share": 1.0}]}, path)
    assert load_shares(path)["Spain"][0]["player"] == "C"  # newer wins
    assert load_shares(tmp_path / "missing.json") == {}


def test_real_shares_artifact_is_named_and_normalized() -> None:
    """The shipped artifact must hold real names with sane share sums."""
    shares = load_shares()
    if not shares:
        pytest.skip("player-shares artifact not built in this environment")
    assert len(shares) >= 10
    for team, players in list(shares.items())[:5]:
        assert players, f"{team} has no players"
        total = sum(p["xg_share"] for p in players)
        assert 0.99 <= total <= 1.01, f"{team} xg shares sum to {total}"
        assert all(p["player"] and not p["player"].startswith("Striker")
                   for p in players)


# -------------------------------------------------------------- odds api

def test_missing_key_raises_actionable_error(monkeypatch) -> None:
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    client = OddsAPIClient()
    with pytest.raises(OddsAPIUnavailable, match="the-odds-api.com"):
        client.upcoming("liga_mx")


def test_unmapped_league_raises_keyerror(monkeypatch) -> None:
    monkeypatch.setenv("ODDS_API_KEY", "test-key")
    with pytest.raises(KeyError, match="no Odds API sport key"):
        OddsAPIClient().resolve_sport_key("league_of_nowhere")


def test_sport_key_mapping_covers_catalog() -> None:
    from src.data.leagues import CATALOG
    from src.data.odds_api import SPORT_KEYS

    for lg in CATALOG:
        assert lg.id in SPORT_KEYS, f"{lg.id} has no Odds API sport key"
    # the two verified against the provider's published coverage list
    assert SPORT_KEYS["liga_mx"] == "soccer_mexico_ligamx"
    assert SPORT_KEYS["mls"] == "soccer_usa_mls"


def test_event_normalization_extracts_odds() -> None:
    event = {
        "commence_time": "2026-08-01T02:05:00Z",
        "home_team": "Monterrey", "away_team": "Toluca",
        "bookmakers": [{
            "title": "DemoBook",
            "markets": [{"key": "h2h", "outcomes": [
                {"name": "Monterrey", "price": 1.95},
                {"name": "Toluca", "price": 3.9},
                {"name": "Draw", "price": 3.5},
            ]}],
        }],
    }
    row = OddsAPIClient._normalize_event(event)
    assert row["date"] == "2026-08-01" and row["time"] == "02:05"
    assert row["odds_home"] == 1.95 and row["odds_away"] == 3.9
    assert row["odds_draw"] == 3.5 and row["bookmaker"] == "DemoBook"
    assert row["source"] == "the-odds-api"


def test_event_without_bookmakers_still_yields_fixture() -> None:
    row = OddsAPIClient._normalize_event({
        "commence_time": "2026-08-01T02:05:00Z",
        "home_team": "A", "away_team": "B", "bookmakers": [],
    })
    assert row["home_team"] == "A" and "odds_home" not in row


def test_cache_is_honoured_without_network(tmp_path, monkeypatch) -> None:
    """A warm cache must serve without a key or a request."""
    import src.data.odds_api as mod

    monkeypatch.setattr(mod, "CACHE", tmp_path)
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    (tmp_path / "sports.json").write_text(json.dumps([{"key": "soccer_epl"}]))
    client = mod.OddsAPIClient()
    assert client.sports() == [{"key": "soccer_epl"}]   # no key needed on hit


def test_fixtures_for_degrades_without_key(monkeypatch) -> None:
    """No key -> fall back to the European feed / empty, never crash."""
    from src.data.leagues import fixtures_for, get_league

    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    fixtures, source = fixtures_for(get_league("liga_mx"))
    assert source in ("none", "football-data.co.uk", "the-odds-api")
    assert isinstance(fixtures, list)
