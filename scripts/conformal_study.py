"""Conformal-under-drift study on REAL data: EPL via football-data.co.uk.

The EPL backtest measured the static split-conformal wrapper at 0.888
empirical coverage vs its 0.90 target (docs/backtest_epl.md) — temporal drift
bends exchangeability. This study reruns the identical walk-forward protocol
and crosses three conformal score functions (LAC / APS / RAPS) with three
adaptation strategies (static / time-decay weighted / Adaptive Conformal
Inference), reporting per variant:

- marginal coverage and mean set size (the efficiency price of adaptivity);
- worst trailing-100-match coverage (marginal averages hide sagging seasons);
- conditional coverage by market favorite strength (LAC's known weak spot);
- the suggestion layer's conformal risk gate: does the set identify the
  losing bets it caps to "low"?

The verdict is computed from the numbers, not asserted. If adaptivity does
not help, the report says so.

Usage: .venv/bin/python -m scripts.conformal_study [--out docs/conformal_study.md]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.backtest_epl import ALPHA, FEATURES, SEED, build_dataset
from src.eval.backtest import OUTCOME_ORDER
from src.eval.metrics import coverage_by_bin, rolling_coverage
from src.eval.splits import walk_forward_folds
from src.models.calibration import IsotonicCalibrator
from src.models.conformal import (
    ACIConformal,
    APSScore,
    LACScore,
    RAPSScore,
    StaticConformal,
    WeightedConformal,
)
from src.models.gbm import OutcomeGBM
from src.models.suggestions import MarketQuote, make_suggestions

HALF_LIFE = 250.0    # matches (~two-thirds of an EPL season)
GAMMA = 0.01         # ACI learning rate (Gibbs & Candès use 0.005–0.05)
WINDOW = 100         # rolling-coverage window
FAV_BINS = [1 / 3, 0.45, 0.55, 0.70, 1.0]
FAV_LABELS = ["toss-up", "mild fav", "clear fav", "heavy fav"]

SCORES = {"lac": LACScore, "aps": APSScore, "raps": RAPSScore}
METHODS = ("static", "weighted", "aci")

# chart chrome — the skill's validated reference palette, light mode
# (slots 1–3 pass all-pairs CVD + normal-vision floors on this surface)
C_METHOD = {"static": "#2a78d6", "weighted": "#eb6834", "aci": "#1baf7a"}
SURFACE, INK, INK_2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"


@dataclass
class FoldData:
    season: str
    cal_probs: np.ndarray     # calibrated, kickoff-ordered
    cal_y: np.ndarray
    test_probs: np.ndarray    # kickoff-ordered
    test_y: np.ndarray
    test: pd.DataFrame        # kickoff-ordered frame with odds columns


def prepare_folds(matches: pd.DataFrame, y: pd.Series) -> list[FoldData]:
    """Identical recipe to scripts.backtest_epl.make_fit_predict — 70/30
    GBM/calibration split within each fold's train window, isotonic only when
    the calibration slice can support it — computed once and shared by every
    conformal variant so the comparison isolates the conformal layer."""
    y_codes = pd.Categorical(y, categories=list(OUTCOME_ORDER)).codes
    folds: list[FoldData] = []
    for fold in walk_forward_folds(matches, min_train_groups=2):
        train = matches.loc[fold.train_idx].sort_values("kickoff_utc")
        test = matches.loc[fold.test_idx].sort_values("kickoff_utc")
        cut = int(len(train) * 0.70)
        fit_idx, cal_idx = train.index[:cut], train.index[cut:]

        gbm = OutcomeGBM(seed=SEED, params={
            "n_estimators": 200, "max_depth": 3, "min_child_weight": 8,
        }).fit(train.loc[fit_idx, FEATURES], y.loc[fit_idx])
        cal_raw = gbm.predict_proba(train.loc[cal_idx, FEATURES])
        cal_y = y_codes[y.index.get_indexer(cal_idx)]

        if len(cal_idx) >= 300:
            transform = IsotonicCalibrator().fit(cal_raw, cal_y).transform
        else:
            transform = lambda p: p  # noqa: E731

        folds.append(FoldData(
            season=fold.group,
            cal_probs=transform(cal_raw), cal_y=cal_y,
            test_probs=transform(gbm.predict_proba(test[FEATURES])),
            test_y=y_codes[y.index.get_indexer(test.index)],
            test=test,
        ))
    return folds


@dataclass
class VariantResult:
    method: str
    score: str
    covered: np.ndarray       # concatenated, kickoff order
    sizes: np.ndarray
    sets: list[list[int]]
    seasons: np.ndarray       # season label per match
    alpha_traj: np.ndarray | None = None


def run_variant(method: str, score: str, folds: list[FoldData]) -> VariantResult:
    covered, sizes, sets, seasons, traj = [], [], [], [], []
    for fd in folds:
        score_fn = SCORES[score]()
        if method == "static":
            conformal = StaticConformal(score_fn, alpha=ALPHA).fit(fd.cal_probs, fd.cal_y)
            fold_sets = conformal.prediction_sets(fd.test_probs)
        elif method == "weighted":
            conformal = WeightedConformal(score_fn, alpha=ALPHA, half_life=HALF_LIFE).fit(
                fd.cal_probs, fd.cal_y
            )
            fold_sets = conformal.prediction_sets(
                fd.test_probs, offsets=np.arange(len(fd.test_probs), dtype=float)
            )
        else:  # aci — resets each fold because the underlying model refits
            conformal = ACIConformal(score_fn, alpha=ALPHA, gamma=GAMMA).fit(
                fd.cal_probs, fd.cal_y
            )
            fold_sets, fold_traj = conformal.run(fd.test_probs, fd.test_y)
            traj.append(fold_traj)

        sets.extend(fold_sets)
        covered.extend(y in s for y, s in zip(fd.test_y, fold_sets))
        sizes.extend(len(s) for s in fold_sets)
        seasons.extend([fd.season] * len(fold_sets))

    return VariantResult(
        method=method, score=score,
        covered=np.array(covered, dtype=float), sizes=np.array(sizes, dtype=float),
        sets=sets, seasons=np.array(seasons),
        alpha_traj=np.concatenate(traj) if traj else None,
    )


def risk_gate_split(folds: list[FoldData], result: VariantResult) -> dict[str, float]:
    """Settle every EV-flagged h2h bet flat 1u at payable closing odds, split
    by whether this variant's conformal set would have capped it to "low".
    Which bets are flagged never varies across variants (flagging is pure
    EV); only the cap assignment moves — so this isolates the question
    "does the uncertainty set know which flagged bets are bad?"."""
    odds_cols = ["odds_home", "odds_draw", "odds_away"]
    imp_cols = ["odds_imp_home", "odds_imp_draw", "odds_imp_away"]
    i = 0
    stats = {"capped": [0.0, 0.0], "uncapped": [0.0, 0.0]}  # [staked, pnl]
    for fd in folds:
        fold_sets = result.sets[i:i + len(fd.test)]
        i += len(fd.test)
        for pos, (_, row) in enumerate(fd.test.iterrows()):
            if row[odds_cols + imp_cols].isna().any():
                continue
            set_names = [OUTCOME_ORDER[k] for k in fold_sets[pos]]
            quotes = [
                MarketQuote(
                    market="h2h", selection=sel,
                    model_prob=float(fd.test_probs[pos, k]),
                    market_prob=float(row[imp_cols[k]]),
                    decimal_odds=float(row[odds_cols[k]]),
                )
                for k, sel in enumerate(OUTCOME_ORDER)
            ]
            for s in make_suggestions(quotes, ev_threshold=0.03, h2h_conformal_set=set_names):
                if not s.flagged:
                    continue
                bucket = "capped" if s.selection not in set_names else "uncapped"
                won = OUTCOME_ORDER[int(fd.test_y[pos])] == s.selection
                stats[bucket][0] += 1.0
                stats[bucket][1] += (s.decimal_odds - 1.0) if won else -1.0
    out = {}
    for bucket, (staked, pnl) in stats.items():
        out[f"n_{bucket}"] = staked
        out[f"roi_{bucket}"] = pnl / staked if staked else float("nan")
    return out


# ---------------------------------------------------------------- plots ----

def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _season_marks(ax, boundaries: list[int], labels: list[str]) -> None:
    for b in boundaries[1:]:
        ax.axvline(b, color=GRID, linewidth=0.8)
    for b0, b1, lab in zip(boundaries, boundaries[1:] + [None], labels):
        x = (b0 + (b1 if b1 is not None else ax.get_xlim()[1])) / 2
        ax.text(x, ax.get_ylim()[0], lab, ha="center", va="bottom",
                fontsize=8, color=MUTED)


def make_plots(results: dict[tuple[str, str], VariantResult],
               folds: list[FoldData], img_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    img_dir.mkdir(parents=True, exist_ok=True)
    boundaries = list(np.cumsum([0] + [len(f.test) for f in folds])[:-1])
    season_labels = [f.season for f in folds]

    # 1 — rolling coverage timeline, LAC score, all three methods.
    # weighted ≈ static on this data, so draw weighted first and static over
    # it: blue shows the shared path, orange peeks out where decay matters
    fig, ax = plt.subplots(figsize=(9.5, 4.4), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    label_bg = dict(facecolor=SURFACE, edgecolor="none", pad=1.5)
    ends: list[tuple[str, int, float]] = []
    for method in ("weighted", "static", "aci"):
        r = results[(method, "lac")]
        roll = rolling_coverage(r.covered, WINDOW)
        ax.plot(roll, color=C_METHOD[method], linewidth=2, label=method)
        end = int(np.where(~np.isnan(roll))[0][-1])
        ends.append((method, end, float(roll[end])))
    # stagger end labels so coincident lines don't stack their names
    ends.sort(key=lambda e: e[2])
    y_prev = -np.inf
    for method, end, y_end in ends:
        y_lab = max(y_end, y_prev + 0.016)
        y_prev = y_lab
        ax.annotate(method, (end, y_lab), xytext=(8, 0),
                    textcoords="offset points", va="center",
                    fontsize=9, color=INK_2, bbox=label_bg)
    ax.axhline(1 - ALPHA, color=MUTED, linewidth=1.2, linestyle=(0, (4, 3)))
    ax.text(4, 1 - ALPHA + 0.003, f"target {1 - ALPHA:.2f}", ha="left",
            va="bottom", fontsize=8, color=MUTED, bbox=label_bg)
    ax.set_ylim(0.78, 1.0)
    ax.set_xlim(0, len(results[("static", "lac")].covered) * 1.06)
    _season_marks(ax, boundaries, season_labels)
    ax.set_title(f"Trailing {WINDOW}-match conformal coverage — LAC score, EPL walk-forward",
                 fontsize=11, color=INK, loc="left")
    ax.set_xlabel("scored matches (kickoff order)", fontsize=9, color=MUTED)
    ax.legend(loc="lower left", fontsize=8, frameon=False, labelcolor=INK_2)
    fig.tight_layout()
    fig.savefig(img_dir / "conformal_rolling.png", facecolor=SURFACE)
    plt.close(fig)

    # 2 — coverage vs set-size frontier, all nine variants
    fig, ax = plt.subplots(figsize=(6.8, 4.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    markers = {"lac": "o", "aps": "s", "raps": "^"}
    for (method, score), r in results.items():
        ax.scatter(r.sizes.mean(), r.covered.mean(), s=110,
                   color=C_METHOD[method], marker=markers[score],
                   edgecolors=SURFACE, linewidths=2, zorder=3)
    ax.axhline(1 - ALPHA, color=MUTED, linewidth=1.2, linestyle=(0, (4, 3)))
    ax.text(ax.get_xlim()[1], 1 - ALPHA + 0.001, f"target {1 - ALPHA:.2f}",
            ha="right", va="bottom", fontsize=8, color=MUTED,
            bbox=dict(facecolor=SURFACE, edgecolor="none", pad=1.5))
    # coincident stacks get a note instead of a misleading jitter
    ax.annotate("static & weighted coincide\n(APS ≈ RAPS)",
                (results[("static", "aps")].sizes.mean(),
                 results[("static", "aps")].covered.mean()),
                xytext=(-12, -4), textcoords="offset points",
                ha="right", va="top", fontsize=8, color=MUTED)
    ax.annotate("ACI, APS ≈ RAPS",
                (results[("aci", "aps")].sizes.mean(),
                 results[("aci", "aps")].covered.mean()),
                xytext=(0, 12), textcoords="offset points",
                ha="center", fontsize=8, color=MUTED)
    from matplotlib.lines import Line2D
    handles = (
        [Line2D([], [], marker="o", ls="", color=C_METHOD[m], label=m, markersize=8)
         for m in METHODS]
        + [Line2D([], [], marker=markers[s], ls="", color=MUTED, label=s.upper(), markersize=8)
           for s in SCORES]
    )
    ax.legend(handles=handles, loc="upper left", fontsize=8, frameon=False,
              ncols=2, labelcolor=INK_2)
    ax.set_title("Marginal coverage vs mean set size — the efficiency frontier",
                 fontsize=11, color=INK, loc="left")
    ax.set_xlabel("mean prediction-set size (outcomes)", fontsize=9, color=MUTED)
    ax.set_ylabel("empirical coverage", fontsize=9, color=MUTED)
    fig.tight_layout()
    fig.savefig(img_dir / "conformal_frontier.png", facecolor=SURFACE)
    plt.close(fig)

    # 3 — ACI effective level trajectory (single series: title names it)
    r = results[("aci", "lac")]
    fig, ax = plt.subplots(figsize=(9.5, 3.4), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    ax.plot(r.alpha_traj, color=C_METHOD["aci"], linewidth=2)
    ax.axhline(ALPHA, color=MUTED, linewidth=1.2, linestyle=(0, (4, 3)))
    ax.text(len(r.alpha_traj) * 1.01, ALPHA, f"nominal α = {ALPHA:.2f}",
            ha="left", va="center", fontsize=8, color=MUTED,
            bbox=dict(facecolor=SURFACE, edgecolor="none", pad=1.5))
    ax.set_xlim(0, len(r.alpha_traj) * 1.14)
    _season_marks(ax, boundaries, season_labels)
    ax.set_title("ACI effective level α_t — LAC score (resets at each refit)",
                 fontsize=11, color=INK, loc="left")
    ax.set_xlabel("scored matches (kickoff order)", fontsize=9, color=MUTED)
    fig.tight_layout()
    fig.savefig(img_dir / "conformal_alpha.png", facecolor=SURFACE)
    plt.close(fig)


# --------------------------------------------------------------- report ----

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("docs/conformal_study.md"))
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()

    matches, y = build_dataset()
    folds = prepare_folds(matches, y)
    results = {
        (m, s): run_variant(m, s, folds) for m in METHODS for s in SCORES
    }

    grid_rows = []
    for (method, score), r in results.items():
        roll = rolling_coverage(r.covered, WINDOW)
        grid_rows.append({
            "method": method, "score": score,
            "coverage": r.covered.mean(),
            "mean set size": r.sizes.mean(),
            "% singleton": (r.sizes == 1).mean(),
            f"worst {WINDOW}-window": np.nanmin(roll),
        })
    grid = pd.DataFrame(grid_rows).set_index(["method", "score"])

    per_season = pd.DataFrame({
        m: pd.Series(results[(m, "lac")].covered)
             .groupby(results[(m, "lac")].seasons).mean()
        for m in METHODS
    })

    fav = np.concatenate([
        f.test[["odds_imp_home", "odds_imp_draw", "odds_imp_away"]]
         .max(axis=1).to_numpy() for f in folds
    ])
    ok = ~np.isnan(fav)
    conditional = {
        m: coverage_by_bin(results[(m, "lac")].covered[ok], fav[ok],
                           FAV_BINS, labels=FAV_LABELS).set_index("bin")
        for m in METHODS
    }
    cond = pd.DataFrame({m: t["coverage"] for m, t in conditional.items()})
    cond["n"] = conditional["static"]["n"]

    gate_rows = {
        f"{m}/lac": risk_gate_split(folds, results[(m, "lac")]) for m in METHODS
    }
    gate = pd.DataFrame(gate_rows).T

    if not args.no_plots:
        make_plots(results, folds, args.out.parent / "img")

    # verdicts computed, not asserted
    static_cov = grid.loc[("static", "lac"), "coverage"]
    best_m = grid["coverage"].sub(1 - ALPHA).abs().idxmin()
    worst_win = {m: grid.loc[(m, "lac"), f"worst {WINDOW}-window"] for m in METHODS}
    marginal_verdict = (
        f"Static split conformal reproduces the documented undercoverage "
        f"({static_cov:.3f} vs {1 - ALPHA:.2f}). Closest to nominal: "
        f"**{best_m[0]}/{best_m[1].upper()}** at "
        f"{grid.loc[best_m, 'coverage']:.3f} with mean set size "
        f"{grid.loc[best_m, 'mean set size']:.2f}."
        if static_cov < 1 - ALPHA else
        f"Static split conformal covers at {static_cov:.3f} on this run — at "
        f"or above target, so adaptivity is buying insurance, not repair."
    )
    worst_bin, best_bin = cond["static"].idxmin(), cond["static"].idxmax()
    cond_verdict = (
        "Marginal coverage says nothing per-slice. On this data the static "
        f"wrapper's deficit concentrates in **{worst_bin}** matches "
        f"({cond.loc[worst_bin, 'static']:.3f}) while {best_bin} matches "
        f"overcover ({cond.loc[best_bin, 'static']:.3f}) — slice-level "
        "honesty the marginal number hides, and the slice the suggestion "
        "layer's risk gate actually operates on."
    )
    drift_verdict = (
        "ACI's worst trailing window "
        f"({worst_win['aci']:.3f}) beats static's ({worst_win['static']:.3f}) — "
        "the online correction repairs exactly the sagging stretches the "
        "marginal average hides."
        if worst_win["aci"] > worst_win["static"] else
        "ACI does NOT improve the worst trailing window here "
        f"({worst_win['aci']:.3f} vs static {worst_win['static']:.3f}) — at "
        f"γ={GAMMA} the correction is too slow for these sags, or the drift "
        "is within static's noise band. Reported as measured."
    )

    lines = [
        "# Conformal prediction under temporal drift — EPL, real data",
        "",
        f"Same data and walk-forward protocol as docs/backtest_epl.md "
        f"(football-data.co.uk, {len(folds)} expanding-window folds, "
        f"{sum(len(f.test) for f in folds)} scored matches), which measured "
        f"the production static wrapper at 0.888 coverage vs the "
        f"{1 - ALPHA:.2f} target. This study crosses three conformal score "
        "functions with three adaptation strategies to ask: can the "
        "guarantee be restored under drift, and at what set-size price?",
        "",
        "| axis | variants |",
        "|---|---|",
        "| score function | LAC (1−p̂, prod baseline) · APS (Romano et al. 2020) · RAPS (Angelopoulos et al. 2021, λ=0.1, k_reg=1) |",
        f"| adaptation | static split · weighted decay (Barber et al. 2023, half-life {HALF_LIFE:.0f} matches) · ACI (Gibbs & Candès 2021, γ={GAMMA}) |",
        "",
        "ACI consumes settled results after full-time — the same feedback "
        "loop `/reflect` already runs in Phase B — and resets each fold "
        "because the model refits.",
        "",
        "## The grid",
        "",
        grid.round(3).to_markdown(),
        "",
        f"{marginal_verdict}",
        "",
        "![Trailing coverage](img/conformal_rolling.png)",
        "",
        "Weighted decay tracks static almost exactly here (orange is drawn "
        "under blue and peeks out where they differ): the expanding train's "
        "last-30% calibration slice is already recent, so a 250-match "
        "half-life barely reweights it — the interesting failure is "
        "*between* refits, which is exactly where ACI acts.",
        "",
        f"{drift_verdict}",
        "",
        "![Coverage vs set size](img/conformal_frontier.png)",
        "",
        "![ACI effective level](img/conformal_alpha.png)",
        "",
        "## Coverage by season (LAC score)",
        "",
        per_season.round(3).to_markdown(),
        "",
        "## Conditional coverage by market favorite strength (LAC score)",
        "",
        cond.round(3).to_markdown(),
        "",
        cond_verdict,
        "",
        "## The conformal risk gate on flagged bets",
        "",
        gate.round(3).to_markdown(),
        "",
        "Flagging is pure EV, so the bet list is identical across variants — "
        "only which flagged bets the set caps to tier \"low\" changes. A "
        "useful uncertainty set concentrates the losses in the capped "
        "bucket (capped ROI below uncapped).",
        "",
        "## Honest notes",
        "",
        "- APS/RAPS are the deterministic (non-randomized) variants — "
        "mildly conservative by construction.",
        f"- Knobs not tuned: half-life ({HALF_LIFE:.0f}) and γ ({GAMMA}) are "
        "literature-typical defaults, not swept; a sweep belongs in a "
        "follow-up, on a split that never touches these test seasons.",
        "- ACI's guarantee is asymptotic long-run coverage; within one fold "
        "it can transiently over/under-cover while α_t settles.",
        "",
        "## References",
        "",
        "- Gibbs & Candès 2021 — *Adaptive Conformal Inference Under "
        "Distribution Shift* (NeurIPS).",
        "- Barber, Candès, Ramdas & Tibshirani 2023 — *Conformal prediction "
        "beyond exchangeability* (Ann. Statist.).",
        "- Romano, Sesia & Candès 2020 — *Classification with Valid and "
        "Adaptive Coverage* (NeurIPS).",
        "- Angelopoulos, Bates, Malik & Jordan 2021 — *Uncertainty Sets for "
        "Image Classifiers using Conformal Prediction* (ICLR).",
        "- Angelopoulos & Bates 2023 — *Conformal Prediction: A Gentle "
        "Introduction* (FnTML).",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
