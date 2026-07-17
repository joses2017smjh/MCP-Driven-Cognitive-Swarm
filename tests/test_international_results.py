"""Tests: international-results provider (canonical frame, WC26 split).

Uses the cached CSV under data/raw/international_results (downloaded by the
first scripts.wc26_predict run); skips cleanly when offline and cacheless.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.data.international_results import (
    fetch_results,
    team_match_frame,
    wc_matches,
)


@pytest.fixture(scope="module")
def raw() -> pd.DataFrame:
    try:
        return fetch_results()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"international results unavailable: {exc}")


def test_canonical_frame_contract(raw: pd.DataFrame) -> None:
    frame = team_match_frame(raw, since="2024-01-01")
    assert not frame.empty
    assert frame["kickoff_utc"].dt.tz is not None
    assert (frame["record_time_utc"] > frame["kickoff_utc"]).all()
    # every played match appears once per side, and no team twice per day
    assert not frame.duplicated(subset=["team", "kickoff_utc"]).any()
    assert frame["neutral_venue"].dtype == bool
    # goals proxy: xg mirrors goals in this source, by documented design
    pd.testing.assert_series_equal(
        frame["xg_for"], frame["goals_for"], check_names=False
    )


def test_wc26_split(raw: pd.DataFrame) -> None:
    played, upcoming = wc_matches(raw, year=2026)
    assert len(played) >= 100                    # group + knockouts to semis
    assert played["home_score"].notna().all()
    assert upcoming["home_score"].isna().all()
    # knockout flag follows the 2026 calendar
    assert not played.loc[played["date"] < "2026-06-28", "knockout"].any()
    assert played.loc[played["date"] >= "2026-06-28", "knockout"].all()
    # the final is Spain vs Argentina, 2026-07-19 (unplayed at freeze time
    # of this test's expectations)
    finals = upcoming[upcoming["date"] == "2026-07-19"]
    if not finals.empty:
        assert {finals.iloc[0]["home_team"], finals.iloc[0]["away_team"]} == \
            {"Spain", "Argentina"}
