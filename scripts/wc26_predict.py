"""World Cup 2026: predict the real tournament, score against ground truth,
and run feature-source ablations.

Protocol (leakage-guarded):
- models train ONLY on internationals played before TRAIN_CUTOFF
  (2026-06-01) — strictly pre-tournament;
- each WC26 match is then predicted from form *as of its kickoff* (which
  legitimately includes earlier WC26 games — that information existed at
  prediction time);
- played matches (through the 2026-07-15 semifinal) are the ground truth;
  the unplayed final and third-place match get full forward forecasts.

Honesty notes baked into the report: internationals here have no odds (so
no market anchor — its absence is an ablation finding in itself), no shot
data (goals stand in for xG), and no player/news feeds (no props layer).

Usage:
  .venv/bin/python -m scripts.wc26_predict            # predict + score + forecast
  .venv/bin/python -m scripts.wc26_predict --ablate   # + ablation table
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.international_results import (
    fetch_results,
    team_match_frame,
    wc_matches,
)
from src.eval.metrics import brier, log_loss, rps
from src.features.team_form import match_level_form, team_form_features
from src.models.calibration import ConformalWrapper, IsotonicCalibrator
from src.models.gbm import OUTCOME_CLASSES, OutcomeGBM, TeamXGGBM
from src.models.score_grid import (
    fit_rho,
    knockout_advance,
    outcome_probs,
    score_grid,
    top_scorelines,
)
from src.models.sequence import GoalTimingModel

TRAIN_CUTOFF = pd.Timestamp("2026-06-01", tz="UTC")
FORM_SINCE = "2016-01-01"
MIN_FORM_MATCHES = 5
SEED = 42
ALPHA = 0.10

BASE_FEATURES = [
    "form_goals_for_home", "form_goals_against_home",
    "form_goals_for_away", "form_goals_against_away",
    "form_n_matches_home", "form_n_matches_away",
    "rest_days_home", "rest_days_away",
    "neutral_venue",
]

ABLATIONS: dict[str, dict] = {
    "full (w10, hl5)": {},
    "no team form": {"drop": [c for c in BASE_FEATURES if c.startswith("form_goals")]},
    "no neutral-venue flag": {"drop": ["neutral_venue"]},
    "no rest days": {"drop": ["rest_days_home", "rest_days_away"]},
    "short window (w5, hl3)": {"window": 5, "half_life": 3.0},
    "no recency decay": {"half_life": 1e6},
}


def build_matches(window: int = 10, half_life: float = 5.0) -> tuple[pd.DataFrame, pd.Series]:
    raw = fetch_results()
    team_matches = team_match_frame(raw, since=FORM_SINCE)
    form = team_form_features(team_matches, window=window, half_life=half_life)
    matches = match_level_form(form)
    matches["neutral_venue"] = matches["neutral_venue"].astype(float)

    home = (
        team_matches[team_matches["is_home"]]
        .set_index("match_id")[["goals_for", "goals_against"]]
        .rename(columns={"goals_for": "goals_home", "goals_against": "goals_away"})
    )
    matches = matches.merge(home, left_on="match_id", right_index=True, how="inner")
    y = pd.Series(
        np.where(matches["goals_home"] > matches["goals_away"], "home",
                 np.where(matches["goals_home"] < matches["goals_away"],
                          "away", "draw")),
        index=matches.index,
    )
    return matches, y


def split_train_wc(matches: pd.DataFrame, y: pd.Series):
    formed = (
        (matches["form_n_matches_home"] >= MIN_FORM_MATCHES)
        & (matches["form_n_matches_away"] >= MIN_FORM_MATCHES)
    )
    train_mask = (matches["kickoff_utc"] < TRAIN_CUTOFF) & formed
    raw = fetch_results()
    played, upcoming = wc_matches(raw, year=2026)
    wc_ids = set(
        played["home_team"].str.replace(r"\W", "", regex=True)
        + "-" + played["away_team"].str.replace(r"\W", "", regex=True)
        + "-" + played["date"]
    )
    wc_mask = matches["match_id"].isin(wc_ids)
    return matches[train_mask], y[train_mask], matches[wc_mask], y[wc_mask], played, upcoming


def fit_outcome(train_x, train_y, features):
    """Pre-tournament model: GBM → isotonic → conformal on a temporal tail."""
    train_x = train_x.sort_values("kickoff_utc")
    cut = int(len(train_x) * 0.85)
    fit_idx, cal_idx = train_x.index[:cut], train_x.index[cut:]
    gbm = OutcomeGBM(seed=SEED, params={
        "n_estimators": 250, "max_depth": 3, "min_child_weight": 8,
    }).fit(train_x.loc[fit_idx, features], train_y.loc[fit_idx])
    codes = pd.Categorical(train_y, categories=list(OUTCOME_CLASSES)).codes
    cal_raw = gbm.predict_proba(train_x.loc[cal_idx, features])
    cal_codes = codes[train_y.index.get_indexer(cal_idx)]
    calibrator = IsotonicCalibrator().fit(cal_raw, cal_codes)
    conformal = ConformalWrapper(alpha=ALPHA).fit(
        calibrator.transform(cal_raw), cal_codes
    )
    return gbm, calibrator, conformal


def score_variant(name, cfg, cache) -> dict:
    window, hl = cfg.get("window", 10), cfg.get("half_life", 5.0)
    key = (window, hl)
    if key not in cache:
        cache[key] = build_matches(window, hl)
    matches, y = cache[key]
    features = [c for c in BASE_FEATURES if c not in set(cfg.get("drop", []))]
    train_x, train_y, wc_x, wc_y, *_ = split_train_wc(matches, y)
    gbm, calibrator, _ = fit_outcome(train_x, train_y, features)
    probs = calibrator.transform(gbm.predict_proba(wc_x[features]))
    y_idx = pd.Categorical(wc_y, categories=list(OUTCOME_CLASSES)).codes
    return {
        "variant": name, "n_features": len(features),
        "logloss": log_loss(probs, y_idx), "brier": brier(probs, y_idx),
        "accuracy": float((probs.argmax(1) == y_idx).mean()),
    }


def forecast_match(home, away, matches, xg_model, rho, timing, when) -> dict:
    """Forward forecast from each side's latest form row before `when`."""
    def latest(team: str, side: str) -> dict:
        rows = matches[
            ((matches["home_team"] == team) | (matches["away_team"] == team))
            & (matches["kickoff_utc"] < when)
        ].sort_values("kickoff_utc")
        row = rows.iloc[-1]
        src = "home" if row["home_team"] == team else "away"
        return {
            f"form_goals_for_{side}": row[f"form_goals_for_{src}"],
            f"form_goals_against_{side}": row[f"form_goals_against_{src}"],
            f"form_n_matches_{side}": row[f"form_n_matches_{src}"],
            f"rest_days_{side}": 4.0,
        }

    feats = {**latest(home, "home"), **latest(away, "away"), "neutral_venue": 1.0}
    row = pd.DataFrame([feats])
    mu_h, mu_a = xg_model.predict(row)
    mu_h, mu_a = float(mu_h[0]), float(mu_a[0])
    grid = score_grid(mu_h, mu_a, rho)
    fs = timing.first_scorer(mu_h, mu_a, p_zero_zero=float(grid[0, 0]))
    return {
        "match": f"{home} vs {away}",
        "mus": (round(mu_h, 2), round(mu_a, 2)),
        "outcome_90": {k: round(v, 3) for k, v in outcome_probs(grid).items()},
        "advance_incl_pens": {
            k: round(v, 3) for k, v in knockout_advance(mu_h, mu_a, rho).items()
        },
        "top_scores": [
            f"{s['score']} ({s['prob']:.0%})" for s in top_scorelines(grid, 4)
        ],
        "first_goal": {k: round(v, 3) for k, v in fs.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ablate", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("docs/wc26_report.md"))
    args = parser.parse_args()

    cache: dict = {}
    cache[(10, 5.0)] = build_matches(10, 5.0)
    matches, y = cache[(10, 5.0)]
    train_x, train_y, wc_x, wc_y, played, upcoming = split_train_wc(matches, y)

    features = BASE_FEATURES
    gbm, calibrator, conformal = fit_outcome(train_x, train_y, features)
    probs = calibrator.transform(gbm.predict_proba(wc_x[features]))
    y_idx = pd.Categorical(wc_y, categories=list(OUTCOME_CLASSES)).codes

    prior = train_y.value_counts(normalize=True).reindex(list(OUTCOME_CLASSES)).to_numpy()
    baseline = np.tile(prior, (len(wc_x), 1))
    uniform = np.full_like(baseline, 1 / 3)

    rows = {
        "model (pre-tournament train)": probs,
        "train-frequency prior": baseline,
        "uniform": uniform,
    }
    comparison = pd.DataFrame({
        name: {
            "logloss": log_loss(p, y_idx), "brier": brier(p, y_idx),
            "rps": rps(p, y_idx),
            "accuracy": float((p.argmax(1) == y_idx).mean()),
        } for name, p in rows.items()
    }).T.round(4)

    sets = conformal.prediction_set(probs)
    coverage = float(np.mean([t in s for t, s in zip(y_idx, sets)]))
    set_size = float(np.mean([len(s) for s in sets]))

    ko_mask = wc_x["match_id"].map(
        dict(zip(
            played["home_team"].str.replace(r"\W", "", regex=True)
            + "-" + played["away_team"].str.replace(r"\W", "", regex=True)
            + "-" + played["date"], played["knockout"],
        ))
    ).astype(bool).to_numpy()
    split_tbl = pd.DataFrame({
        stage: {
            "n": int(mask.sum()),
            "logloss": log_loss(probs[mask], y_idx[mask]),
            "accuracy": float((probs[mask].argmax(1) == y_idx[mask]).mean()),
        }
        for stage, mask in [("group", ~ko_mask), ("knockout", ko_mask)]
    }).T.round(4)

    # ------------------------------------------------------------- forecasts
    xg_model = TeamXGGBM(seed=SEED, params={
        "n_estimators": 250, "max_depth": 3, "min_child_weight": 8,
    }).fit(train_x[features], train_x["goals_home"], train_x["goals_away"])
    sample = train_x.tail(2000)
    ph, pa = xg_model.predict(sample[features])
    rho = fit_rho(sample["goals_home"].to_numpy(), sample["goals_away"].to_numpy(), ph, pa)
    timing = GoalTimingModel()  # uniform profile: no event minutes in this source

    now = pd.Timestamp.now(tz="UTC")
    forecasts = [
        forecast_match(r["home_team"], r["away_team"], matches, xg_model,
                       rho, timing, when=now)
        for _, r in upcoming.iterrows()
    ]

    ablation_tbl = None
    if args.ablate:
        ablation_tbl = pd.DataFrame(
            [score_variant(n, c, cache) for n, c in ABLATIONS.items()]
        ).set_index("variant").round(4)

    # --------------------------------------------------------------- report
    lines = [
        "# World Cup 2026 — real-tournament evaluation",
        "",
        f"Training: {len(train_x)} internationals ({FORM_SINCE[:4]}–May 2026), "
        f"strictly before {TRAIN_CUTOFF.date()} — zero tournament leakage. "
        f"Scored: {len(wc_x)} played WC26 matches through the semifinals. "
        "Source: martj42/international_results (free). No odds exist for "
        "internationals here, so the model runs WITHOUT its market anchor; "
        "goals stand in for xG; no player/news layers.",
        "",
        "## Model vs baselines on the real bracket",
        "",
        comparison.to_markdown(),
        "",
        f"Conformal: empirical coverage {coverage:.3f} vs target "
        f"{1 - ALPHA:.2f}, mean set size {set_size:.2f}.",
        "",
        "## Group stage vs knockout",
        "",
        split_tbl.to_markdown(),
        "",
        "## Forward forecasts (unplayed at report time)",
        "",
    ]
    for fc in forecasts:
        lines += [
            f"### {fc['match']}",
            f"- expected goals: {fc['mus'][0]} – {fc['mus'][1]}",
            f"- 90-minute outcome: {fc['outcome_90']}",
            f"- to lift/advance (incl. extra time & penalties): "
            f"{fc['advance_incl_pens']}",
            f"- most likely scores: {', '.join(fc['top_scores'])}",
            f"- first goal: {fc['first_goal']}",
            "",
        ]
    if ablation_tbl is not None:
        lines += [
            "## Ablations (same protocol per variant)",
            "",
            ablation_tbl.to_markdown(),
            "",
            "Sources not ablatable here because they do not exist for free "
            "international data: betting-odds anchor (largest gap — see the "
            "EPL backtest where the market-anchored model gains ~0.03 log "
            "loss), news/availability, and true xG. The agent-level source "
            "ablation (kill a server, re-run) is exercised in evals/ via "
            "InProcessRunner(disabled=...).",
        ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
