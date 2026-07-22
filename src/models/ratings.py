"""Opponent-adjusted team ratings (Elo) — strength of schedule, done right.

Ranking national teams by raw goal difference is badly biased: a minnow that
runs up scores on weaker minnows in regional qualifying outranks a strong
team that plays tough opponents. Elo fixes this by construction — you only
gain rating for beating strong opponents, and results propagate through the
whole graph of who-played-whom.

This is the concrete form of the project's cross-league normalization: one
rating scale comparable across confederations. Ratings feed both the bracket
seeding and each tie's expected goals (via a data-calibrated Elo-difference →
goal-supremacy mapping), so strength of schedule flows all the way into the
scoreline grid.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

BASE_ELO = 1500.0
HOME_ADV = 60.0
K = 40.0


@dataclass
class EloModel:
    ratings: dict[str, float]
    last_played: dict[str, str]
    n_played: dict[str, int]
    goal_slope: float      # expected goal supremacy per Elo point
    base_total: float      # league-average combined goals

    def expected_goals(self, home: str, away: str, neutral: bool = True
                       ) -> tuple[float, float]:
        diff = self.ratings.get(home, BASE_ELO) - self.ratings.get(away, BASE_ELO)
        if not neutral:
            diff += HOME_ADV
        supremacy = self.goal_slope * diff
        mu_h = max(0.15, self.base_total / 2 + supremacy / 2)
        mu_a = max(0.15, self.base_total / 2 - supremacy / 2)
        return mu_h, mu_a


def _mov_multiplier(goal_diff: int) -> float:
    """World-Football-Elo margin-of-victory multiplier (dampens blowouts)."""
    return math.log(abs(goal_diff) + 1) + 1.0


def compute_elo(results: pd.DataFrame) -> EloModel:
    """Fit Elo from a results frame (home_team, away_team, home_score,
    away_score, neutral), processed chronologically."""
    df = results.dropna(subset=["home_score", "away_score"]).copy()
    df = df.sort_values("date")
    ratings: dict[str, float] = {}
    last: dict[str, str] = {}
    n: dict[str, int] = {}

    for r in df.itertuples(index=False):
        h, a = r.home_team, r.away_team
        ra = ratings.get(h, BASE_ELO)
        rb = ratings.get(a, BASE_ELO)
        adv = 0.0 if bool(getattr(r, "neutral", False)) else HOME_ADV
        exp_home = 1.0 / (1.0 + 10 ** (-((ra + adv) - rb) / 400))
        gd = int(r.home_score - r.away_score)
        actual = 1.0 if gd > 0 else (0.5 if gd == 0 else 0.0)
        change = K * _mov_multiplier(gd) * (actual - exp_home)
        ratings[h] = ra + change
        ratings[a] = rb - change
        last[h] = last[a] = str(r.date)
        n[h] = n.get(h, 0) + 1
        n[a] = n.get(a, 0) + 1

    # calibrate Elo diff -> goal supremacy on the same matches (final ratings
    # as strength proxy; a projection, not a leakage-controlled backtest)
    diffs, sup = [], []
    for r in df.itertuples(index=False):
        adv = 0.0 if bool(getattr(r, "neutral", False)) else HOME_ADV
        diffs.append(ratings[r.home_team] - ratings[r.away_team] + adv)
        sup.append(r.home_score - r.away_score)
    diffs_a, sup_a = np.array(diffs), np.array(sup)
    slope = float(np.dot(diffs_a, sup_a) / np.dot(diffs_a, diffs_a))  # 0-intercept OLS
    base_total = float((df["home_score"] + df["away_score"]).mean())
    return EloModel(ratings, last, n, goal_slope=slope, base_total=base_total)


def rank_by_elo(
    elo: EloModel, *, top_n: int, active_since: str, min_matches: int = 10,
) -> list[tuple[str, float]]:
    """Strongest teams that are still active (played since ``active_since``)."""
    eligible = [
        (t, r) for t, r in elo.ratings.items()
        if elo.last_played.get(t, "") >= active_since
        and elo.n_played.get(t, 0) >= min_matches
    ]
    eligible.sort(key=lambda x: -x[1])
    return eligible[:top_n]
