"""Unit tests: minute quantiles and the headline-scenario builder."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from src.models.predict import _headline_scenario
from src.models.sequence import GoalTimingModel

PROPS = {
    "home": [
        {"player": "H-Striker", "p_anytime_scorer": 0.5, "p_assist": 0.1,
         "goal_lambda": 0.8, "assist_lambda": 0.1},
        {"player": "H-Mid", "p_anytime_scorer": 0.3, "p_assist": 0.4,
         "goal_lambda": 0.4, "assist_lambda": 0.5},
    ],
    "away": [
        {"player": "A-Striker", "p_anytime_scorer": 0.4, "p_assist": 0.1,
         "goal_lambda": 0.5, "assist_lambda": 0.1},
        {"player": "A-Wing", "p_anytime_scorer": 0.2, "p_assist": 0.3,
         "goal_lambda": 0.2, "assist_lambda": 0.3},
    ],
}


def _grid_with_top(score: tuple[int, int]) -> np.ndarray:
    grid = np.full((4, 4), 0.01)
    grid[score] = 0.5
    return grid / grid.sum()


def _bundle() -> SimpleNamespace:
    return SimpleNamespace(timing=GoalTimingModel())  # uniform time profile


def test_minute_quantile_uniform_profile() -> None:
    timing = GoalTimingModel()
    assert timing.minute_quantile(0.5) == pytest.approx(45.0)
    assert timing.minute_quantile(0.0) == pytest.approx(0.0)
    assert timing.minute_quantile(1.0) == pytest.approx(90.0)
    qs = [timing.minute_quantile(q) for q in np.linspace(0, 1, 11)]
    assert qs == sorted(qs)  # monotonic


def test_scenario_draw_knockout_goes_to_penalties() -> None:
    scenario = _headline_scenario(
        _bundle(), _grid_with_top((1, 1)), props=PROPS,
        knockout=True, advance={"home": 0.63, "away": 0.37},
    )
    assert scenario["scoreline"] == "1-1"
    assert scenario["penalties"] == {"winner": "home", "p_advance": 0.63}
    assert len(scenario["goals"]) == 2
    minutes = [g["minute"] for g in scenario["goals"]]
    assert minutes == sorted(minutes)
    assert all(0 <= m <= 90 for m in minutes)
    # top scorer of each side scores; assist comes from a different teammate
    by_team = {g["team"]: g for g in scenario["goals"]}
    assert by_team["home"]["scorer"] == "H-Striker"
    assert by_team["home"]["assist"] == "H-Mid"
    assert by_team["away"]["scorer"] == "A-Striker"
    # POTM belongs to the shootout winner's side
    assert scenario["player_of_the_match"] == "H-Striker"


def test_scenario_decisive_score_no_penalties() -> None:
    scenario = _headline_scenario(
        _bundle(), _grid_with_top((2, 0)), props=PROPS,
        knockout=True, advance={"home": 0.8, "away": 0.2},
    )
    assert scenario["scoreline"] == "2-0"
    assert "penalties" not in scenario
    scorers = [g["scorer"] for g in scenario["goals"]]
    assert scorers == ["H-Striker", "H-Mid"]  # 2nd goal → 2nd most likely scorer


def test_scenario_without_props_still_renders_times() -> None:
    scenario = _headline_scenario(
        _bundle(), _grid_with_top((1, 0)), props=None,
        knockout=False, advance=None,
    )
    assert scenario["scoreline"] == "1-0"
    assert scenario["goals"][0]["team"] == "home"
    assert "scorer" not in scenario["goals"][0]
    assert "player_of_the_match" not in scenario


def test_goalless_scenario() -> None:
    scenario = _headline_scenario(
        _bundle(), _grid_with_top((0, 0)), props=PROPS,
        knockout=False, advance=None,
    )
    assert scenario["scoreline"] == "0-0"
    assert scenario["goals"] == []
