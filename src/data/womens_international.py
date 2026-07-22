"""Women's international results provider — martj42/womens-international-results.

Free, no key, same schema as the men's set (src/data/international_results.py):
~11.6k women's internationals, current through the latest window. This is the
strength + projection source for the Women's World Cup bracket.

The next Women's World Cup (2027, Brazil) has no draw yet, so the bracket is a
**data-driven projection over a seeded field**, not a real fixture list — the
report and JSON say so explicitly.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from src.data.international_results import team_match_frame  # shared parser

BASE_URL = "https://raw.githubusercontent.com/martj42/womens-international-results/master"
DEFAULT_CACHE = Path("data/raw/womens_international")


def fetch_results(cache_dir: Path = DEFAULT_CACHE, refresh: bool = False) -> pd.DataFrame:
    """results.csv: date, home_team, away_team, home_score, away_score,
    tournament, city, country, neutral."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "results.csv"
    if refresh or not path.exists():
        resp = requests.get(f"{BASE_URL}/results.csv", timeout=60)
        resp.raise_for_status()
        path.write_bytes(resp.content)
    return pd.read_csv(path)


def womens_team_matches(since: str = "2019-01-01") -> pd.DataFrame:
    """Canonical TEAM_MATCH long frame from women's results (goals-proxy xG,
    same as the men's international source)."""
    return team_match_frame(fetch_results(), since=since)
