"""Tests: league catalog, normalized loaders, standings, and matchups.

Parsing/standings are tested on synthetic raw frames (no network); a
network-gated test checks a real live league end-to-end.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.data.leagues import (
    BY_ID,
    CATALOG,
    _normalize_main,
    _normalize_new,
    get_league,
    latest_season,
    recent_results,
    standings,
)


def _new_raw() -> pd.DataFrame:
    """new-section format (Liga MX / MLS / ARG / BRA)."""
    return pd.DataFrame({
        "Country": ["Mexico"] * 4, "League": ["Liga MX"] * 4,
        "Season": ["2025/2026", "2026/2027", "2026/2027", "2026/2027"],
        "Date": ["10/05/2026", "18/07/2026", "19/07/2026", "19/07/2026"],
        "Time": ["02:00"] * 4,
        "Home": ["Toluca", "Pachuca", "Monterrey", "Queretaro"],
        "Away": ["Atlas", "Atlas", "Toluca", "Pachuca"],
        "HG": [1, 3, 2, 0], "AG": [1, 0, 2, 1],
    })


def _main_raw() -> pd.DataFrame:
    """main-section format (European divisions)."""
    return pd.DataFrame({
        "Div": ["E0"] * 3,
        "Date": ["16/08/2025", "17/08/2025", "23/08/2025"],
        "HomeTeam": ["Arsenal", "Liverpool", "Arsenal"],
        "AwayTeam": ["Chelsea", "Everton", "Liverpool"],
        "FTHG": [2, 1, 0], "FTAG": [0, 1, 3],
    })


# ------------------------------------------------------------- catalog

def test_catalog_covers_requested_regions() -> None:
    regions = {lg.region for lg in CATALOG}
    assert {"North America", "Europe", "South America"} <= regions
    assert {"liga_mx", "mls", "epl", "laliga", "seriea", "bundesliga",
            "ligue1", "argentina", "brazil"} <= set(BY_ID)


def test_unknown_league_fails_loudly() -> None:
    with pytest.raises(KeyError, match="unknown league"):
        get_league("premier_league_of_nowhere")


# ------------------------------------------------------------ parsing

def test_normalize_new_format() -> None:
    df = _normalize_new(_new_raw())
    assert list(df.columns) == ["date", "season", "home_team", "away_team",
                                "home_score", "away_score", "neutral"]
    assert df["date"].iloc[0] == "2026-05-10"        # dd/mm/yyyy parsed
    assert df["date"].is_monotonic_increasing        # sorted
    assert latest_season(df) == "2026/2027"


def test_normalize_main_format() -> None:
    df = _normalize_main(_main_raw(), "2025/2026")
    assert len(df) == 3
    assert df["date"].iloc[0] == "2025-08-16"
    assert df["season"].unique().tolist() == ["2025/2026"]
    assert not df["neutral"].any()


# ---------------------------------------------------------- standings

def test_standings_points_and_order() -> None:
    df = _normalize_new(_new_raw())
    table = standings(df, "2026/2027")
    by_team = {r["team"]: r for r in table}
    # Pachuca: beat Atlas 3-0 at home AND won 1-0 away at Queretaro -> 6 pts
    assert by_team["Pachuca"]["points"] == 6
    assert by_team["Pachuca"]["gd"] == 4          # (3-0) + (1-0)
    assert by_team["Pachuca"]["won"] == 2 and by_team["Pachuca"]["lost"] == 0
    # and the away loss is credited to Queretaro
    assert by_team["Queretaro"]["lost"] == 1 and by_team["Queretaro"]["points"] == 0
    # Monterrey 2-2 Toluca -> a point each
    assert by_team["Monterrey"]["points"] == 1
    assert by_team["Toluca"]["drawn"] == 1
    # ranks assigned in table order, sorted by points then GD
    assert [r["rank"] for r in table] == list(range(1, len(table) + 1))
    pts = [r["points"] for r in table]
    assert pts == sorted(pts, reverse=True)


def test_standings_only_counts_requested_season() -> None:
    df = _normalize_new(_new_raw())
    table = standings(df, "2026/2027")
    # the 2025/2026 Toluca-Atlas draw must not be counted
    assert {r["team"] for r in table} == {"Pachuca", "Atlas", "Monterrey",
                                          "Toluca", "Queretaro"}
    assert sum(r["played"] for r in table) == 3 * 2   # 3 matches, 2 teams each


def test_recent_results_newest_first() -> None:
    df = _normalize_new(_new_raw())
    recent = recent_results(df, n=3)
    assert len(recent) == 3
    assert recent[0]["date"] >= recent[-1]["date"]
    assert set(recent[0]) == {"date", "home_team", "away_team",
                              "home_score", "away_score"}


# --------------------------------------------------- real data (gated)

def test_real_live_league_loads() -> None:
    try:
        from src.data.leagues import build_ratings, load_results, predict_matchup

        results = load_results(get_league("liga_mx"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"league data unavailable: {exc}")

    season = latest_season(results)
    table = standings(results, season)
    assert len(table) >= 10                      # a real top-flight field
    elo, rho = build_ratings(results)
    tie = predict_matchup(elo, rho, table[0]["team"], table[1]["team"])
    assert sum(tie["outcome_90"].values()) == pytest.approx(1.0, abs=1e-6)
    assert tie["evidence"]["home_rating"]["elo"] > 0
    assert tie["headline_scenario"]["scoreline"]
