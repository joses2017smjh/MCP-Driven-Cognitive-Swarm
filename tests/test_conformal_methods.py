"""Drift-aware conformal methods (src/models/conformal.py).

Covers: score-function math on hand-computed examples, exchangeable coverage
for every method × score combination, the identity between StaticConformal(LAC)
and the production ConformalWrapper, weighted-quantile behavior under decay,
the ACI update rule, and ACI's coverage advantage under an induced drift that
breaks the static guarantee.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.eval.metrics import conformal_coverage, coverage_by_bin, rolling_coverage
from src.models.calibration import ConformalWrapper
from src.models.conformal import (
    ACIConformal,
    APSScore,
    LACScore,
    RAPSScore,
    StaticConformal,
    WeightedConformal,
)

ALPHA = 0.1
RNG = np.random.default_rng(7)


def _exchangeable(n: int, concentration: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    """Probability vectors with labels drawn FROM those vectors — perfectly
    calibrated by construction, so conformal coverage must hold."""
    probs = RNG.dirichlet(np.full(3, concentration), size=n)
    y = np.array([RNG.choice(3, p=p) for p in probs])
    return probs, y


def test_lac_scores_hand_example():
    probs = np.array([[0.5, 0.3, 0.2]])
    np.testing.assert_allclose(LACScore().per_class(probs), [[0.5, 0.7, 0.8]])


def test_aps_scores_hand_example():
    # sorted desc: 0.5, 0.3, 0.2 → cumulative 0.5, 0.8, 1.0 back in place
    probs = np.array([[0.5, 0.3, 0.2]])
    np.testing.assert_allclose(APSScore().per_class(probs), [[0.5, 0.8, 1.0]])


def test_raps_adds_rank_penalty():
    probs = np.array([[0.5, 0.3, 0.2]])
    # ranks 1,2,3 with k_reg=1, lam=0.1 → penalties 0, 0.1, 0.2 on APS scores
    np.testing.assert_allclose(
        RAPSScore(lam=0.1, k_reg=1).per_class(probs), [[0.5, 0.9, 1.2]]
    )


def test_static_lac_matches_production_wrapper():
    cal_p, cal_y = _exchangeable(500)
    test_p, _ = _exchangeable(200)

    ours = StaticConformal(LACScore(), alpha=ALPHA).fit(cal_p, cal_y)
    theirs = ConformalWrapper(alpha=ALPHA).fit(cal_p, cal_y)

    assert ours.prediction_sets(test_p) == theirs.prediction_set(test_p)


@pytest.mark.parametrize("score_fn", [LACScore(), APSScore(), RAPSScore()])
@pytest.mark.parametrize(
    "method",
    [
        lambda s: StaticConformal(s, alpha=ALPHA),
        lambda s: WeightedConformal(s, alpha=ALPHA, half_life=400.0),
        lambda s: ACIConformal(s, alpha=ALPHA, gamma=0.01),
    ],
    ids=["static", "weighted", "aci"],
)
def test_exchangeable_coverage(method, score_fn):
    cal_p, cal_y = _exchangeable(1000)
    test_p, test_y = _exchangeable(1500)

    conformal = method(score_fn).fit(cal_p, cal_y)
    if isinstance(conformal, ACIConformal):
        sets, _ = conformal.run(test_p, test_y)
    else:
        sets = conformal.prediction_sets(test_p)

    assert conformal_coverage(sets, test_y) >= (1 - ALPHA) - 0.03
    assert all(len(s) >= 1 for s in sets)


def test_weighted_uniform_is_canonical_order_statistic():
    """Uniform weights must recover the textbook ⌈(n+1)(1−α)⌉-th order
    statistic exactly (np.quantile's 'higher' interpolation, used by the
    static wrapper, may sit one order statistic above it)."""
    cal_p, cal_y = _exchangeable(400)

    uniform = WeightedConformal(LACScore(), alpha=ALPHA, half_life=None).fit(cal_p, cal_y)
    scores = np.sort(1.0 - cal_p[np.arange(len(cal_y)), cal_y])
    rank = int(np.ceil((len(scores) + 1) * (1 - ALPHA)))  # 1-based
    assert uniform._quantile(offset=0.0) == pytest.approx(scores[rank - 1])


def test_weighted_threshold_grows_with_offset():
    """As the test point recedes from the calibration window, the +∞ atom
    gains relative mass and the threshold must move conservative."""
    cal_p, cal_y = _exchangeable(400)
    conformal = WeightedConformal(LACScore(), alpha=ALPHA, half_life=50.0).fit(cal_p, cal_y)
    assert conformal._quantile(offset=300.0) >= conformal._quantile(offset=0.0)


def test_aci_update_rule_direction():
    cal_p, cal_y = _exchangeable(300)
    conformal = ACIConformal(LACScore(), alpha=ALPHA, gamma=0.02).fit(cal_p, cal_y)
    row = np.array([0.6, 0.25, 0.15])

    pred = conformal.step(row)
    a_before = conformal.alpha_t
    conformal.update(row, y=next(k for k in range(3) if k not in pred), pred_set=pred)
    assert conformal.alpha_t < a_before  # a miss must widen future sets

    pred = conformal.step(row)
    a_before = conformal.alpha_t
    conformal.update(row, y=pred[0], pred_set=pred)
    assert conformal.alpha_t > a_before  # a hit tightens them


def test_aci_recovers_coverage_under_drift_where_static_fails():
    """Induced drift: at deployment the model's probabilities are sharpened
    (overconfident) relative to calibration — the EPL failure mode. Static
    conformal has no recourse; ACI's feedback loop must land materially
    closer to target on the same stream."""
    cal_p, cal_y = _exchangeable(1000)

    true_p, test_y = _exchangeable(2000)
    sharp = true_p ** 2.5                     # overconfident deployed model
    sharp /= sharp.sum(axis=1, keepdims=True)

    static_sets = StaticConformal(LACScore(), alpha=ALPHA).fit(cal_p, cal_y).prediction_sets(sharp)
    aci_sets, _ = ACIConformal(LACScore(), alpha=ALPHA, gamma=0.02).fit(cal_p, cal_y).run(
        sharp, test_y
    )

    static_cov = conformal_coverage(static_sets, test_y)
    aci_cov = conformal_coverage(aci_sets, test_y)
    assert static_cov < (1 - ALPHA) - 0.02    # drift genuinely breaks static
    assert abs(aci_cov - (1 - ALPHA)) < abs(static_cov - (1 - ALPHA)) - 0.01


def test_aci_alpha_clamp_yields_full_set():
    cal_p, cal_y = _exchangeable(300)
    conformal = ACIConformal(LACScore(), alpha=ALPHA, gamma=0.02).fit(cal_p, cal_y)
    conformal.alpha_t = -0.05
    assert conformal.step(np.array([0.98, 0.01, 0.01])) == [0, 1, 2]


def test_rolling_coverage_windows():
    covered = np.array([1, 1, 0, 1, 1, 1], dtype=float)
    out = rolling_coverage(covered, window=3)
    assert np.isnan(out[:2]).all()
    np.testing.assert_allclose(out[2:], [2 / 3, 2 / 3, 2 / 3, 1.0])


def test_coverage_by_bin_slices():
    covered = np.array([1, 0, 1, 1])
    values = np.array([0.40, 0.42, 0.80, 0.82])
    table = coverage_by_bin(covered, values, [0.0, 0.5, 1.0], labels=["tossup", "fav"])
    assert table.set_index("bin").loc["tossup", "coverage"] == 0.5
    assert table.set_index("bin").loc["fav", "coverage"] == 1.0
