"""Tests: API-Football client — zero requests, zero credits spent.

Everything is exercised against synthetic payloads or a warm cache, so the
suite never touches the provider or the daily quota.
"""

from __future__ import annotations

import json

import pytest

from src.data.api_football import (
    LEAGUE_IDS,
    APIFootballClient,
    APIFootballUnavailable,
)


def test_missing_key_raises_actionable_error(monkeypatch) -> None:
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    with pytest.raises(APIFootballUnavailable, match="api-football.com"):
        APIFootballClient().squad_shares("liga_mx", 2026)


def test_unmapped_league_raises(monkeypatch) -> None:
    monkeypatch.setenv("API_FOOTBALL_KEY", "test-key")
    with pytest.raises(KeyError, match="no API-Football league id"):
        APIFootballClient().resolve_league_id("league_of_nowhere")


def test_league_ids_cover_the_catalog() -> None:
    from src.data.leagues import CATALOG

    for lg in CATALOG:
        assert lg.id in LEAGUE_IDS, f"{lg.id} has no API-Football league id"


def test_fixture_normalization() -> None:
    row = APIFootballClient._normalize_fixture({
        "fixture": {"id": 42, "date": "2026-08-01T02:05:00+00:00",
                    "venue": {"name": "Estadio BBVA"}},
        "teams": {"home": {"name": "Monterrey"}, "away": {"name": "Toluca"}},
    })
    assert row["fixture_id"] == 42
    assert row["date"] == "2026-08-01" and row["time"] == "02:05"
    assert row["home_team"] == "Monterrey" and row["away_team"] == "Toluca"
    assert row["venue"] == "Estadio BBVA" and row["source"] == "api-football"


def _warm(tmp_path, monkeypatch, name: str, payload) -> APIFootballClient:
    """Client whose cache already holds `payload`, so no request is made."""
    import src.data.api_football as mod

    monkeypatch.setattr(mod, "CACHE", tmp_path)
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    (tmp_path / name).write_text(json.dumps(payload))
    return mod.APIFootballClient()


def test_squad_shares_from_cached_stats(tmp_path, monkeypatch) -> None:
    """Goals/assists become normalized per-team shares."""
    scorers = [{
        "player": {"name": "Striker One"},
        "statistics": [{"team": {"name": "Monterrey"},
                        "goals": {"total": 12}, "games": {"minutes": 900}}],
    }, {
        "player": {"name": "Striker Two"},
        "statistics": [{"team": {"name": "Monterrey"},
                        "goals": {"total": 4}, "games": {"minutes": 700}}],
    }]
    assisters = [{
        "player": {"name": "Playmaker"},
        "statistics": [{"team": {"name": "Monterrey"},
                        "goals": {"assists": 8}, "games": {"minutes": 850}}],
    }]
    client = _warm(tmp_path, monkeypatch, "topscorers_262_2026.json", scorers)
    (tmp_path / "topassists_262_2026.json").write_text(json.dumps(assisters))

    shares = client.squad_shares("liga_mx", 2026)
    assert set(shares) == {"Monterrey"}
    players = {p["player"]: p for p in shares["Monterrey"]}
    assert set(players) == {"Striker One", "Striker Two", "Playmaker"}
    # 12 of 16 goals among the listed players
    assert players["Striker One"]["xg_share"] == pytest.approx(0.75)
    assert players["Striker Two"]["xg_share"] == pytest.approx(0.25)
    assert players["Playmaker"]["xa_share"] == pytest.approx(1.0)
    assert sum(p["xg_share"] for p in shares["Monterrey"]) == pytest.approx(1.0)
    # provenance must disclose that these are goals, not true xG
    assert "not xG" in players["Striker One"]["source"]


def test_lineups_normalization(tmp_path, monkeypatch) -> None:
    payload = [{
        "team": {"name": "Monterrey"},
        "startXI": [{"player": {"name": "Keeper"}},
                    {"player": {"name": "Striker One"}}],
    }]
    client = _warm(tmp_path, monkeypatch, "lineups_99.json", payload)
    assert client.lineups(99) == {"Monterrey": ["Keeper", "Striker One"]}


def test_injuries_normalization(tmp_path, monkeypatch) -> None:
    payload = [{
        "player": {"name": "Striker One", "type": "Missing Fixture",
                   "reason": "Knee Injury"},
        "team": {"name": "Monterrey"},
    }]
    client = _warm(tmp_path, monkeypatch, "injuries_262_2026.json", payload)
    out = client.injuries("liga_mx", 2026)
    assert out == [{"player": "Striker One", "team": "Monterrey",
                    "type": "Missing Fixture", "reason": "Knee Injury"}]


def test_shares_shape_matches_allocator_contract(tmp_path, monkeypatch) -> None:
    """Club shares must drop into the same allocator StatsBomb shares feed."""
    import pandas as pd

    from src.models.player_props import allocate_player_props

    scorers = [{"player": {"name": "A"},
                "statistics": [{"team": {"name": "T"}, "goals": {"total": 6}}]}]
    client = _warm(tmp_path, monkeypatch, "topscorers_262_2026.json", scorers)
    (tmp_path / "topassists_262_2026.json").write_text(json.dumps([]))
    shares = client.squad_shares("liga_mx", 2026)

    frame = pd.DataFrame([{**p, "availability": 1.0} for p in shares["T"]])
    out = allocate_player_props(frame, team_mu=1.5)
    assert out["p_anytime_scorer"].between(0, 1).all()
