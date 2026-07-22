"""Project the next Women's World Cup bracket from current data.

Seeds the strongest current women's national teams (recency-decayed form on
real results) and simulates the knockout bracket with the model, printing a
readable report and writing a JSON artifact the gateway/UI can serve.

Honest framing: the 2027 draw does not exist yet, so this is a data-driven
projection over a seeded field, not a real fixture list.

Usage: .venv/bin/python -m scripts.wwc_bracket [--json data/artifacts/wwc_bracket.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.data.womens_international import fetch_results
from src.models.bracket import simulate_bracket


def _fmt_match(m: dict) -> list[str]:
    adv = m["advance"]
    sc = m["headline_scenario"]
    lines = [
        f"  ({m['seeds']['home']}) {m['home']}  vs  "
        f"{m['away']} ({m['seeds']['away']})",
        f"    xG {m['expected_goals']['home']}–{m['expected_goals']['away']} · "
        f"advance: {m['home']} {adv[m['home']]:.0%} / {m['away']} {adv[m['away']]:.0%}"
        f"  →  {m['projected_winner']}",
        f"    likely score {sc['scoreline']} ({sc['probability']:.0%})",
    ]
    for g in sc["goals"]:
        team = m["home"] if g["team"] == "home" else m["away"]
        assist = f", assist {g['assist_role']}" if g["assist_role"] else ""
        lines.append(f"      {g['minute']}' {g['scorer_role']} ({team}){assist}")
    if sc["penalties"]:
        lines.append(f"    level → {sc['penalties']['winner']} on penalties "
                     f"({sc['penalties']['p_advance']:.0%})")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path,
                        default=Path("data/artifacts/wwc_bracket.json"))
    args = parser.parse_args()

    bracket = simulate_bracket(fetch_results())

    print("=" * 68)
    print("WOMEN'S WORLD CUP — DATA-DRIVEN BRACKET PROJECTION")
    print("=" * 68)
    print(bracket["disclaimer"])
    print("\nSeeded field (strongest by opponent-adjusted Elo):")
    for s in bracket["seeding"]:
        print(f"  {s['rank']:>2}. {s['team']:<22} "
              f"Elo {s['elo']:.0f}  ({s['matches']} matches)")

    for rnd in bracket["rounds"]:
        print(f"\n--- {rnd['round']} ---")
        for m in rnd["matches"]:
            print("\n".join(_fmt_match(m)))
            print()

    print(f"PROJECTED CHAMPION: {bracket['champion']}")
    print(f"(Dixon-Coles rho={bracket['model']['dixon_coles_rho']})")

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(bracket, indent=2))
    print(f"\nJSON written to {args.json}")


if __name__ == "__main__":
    main()
