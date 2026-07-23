"""Build CURRENT club-squad player shares from API-Football.

Fixes the gap StatsBomb open data cannot: its club coverage is historical
(La Liga ends 2020/21, MLS is 6 matches), so club league pages fall back to
role-level players. This pulls the *current* season's scorers/assisters and
merges them into the same `data/artifacts/player_shares.json` the bracket and
matchup projector already read — so nothing downstream changes.

Cost: 2 API requests per league (top scorers + top assists), well inside the
free tier. Requires API_FOOTBALL_KEY.

Usage:
    python -m scripts.build_club_shares --season 2026 --leagues liga_mx mls
    python -m scripts.build_club_shares --season 2026            # all mapped
"""

from __future__ import annotations

import argparse
import sys

from src.data.api_football import (
    LEAGUE_IDS,
    APIFootballClient,
    APIFootballUnavailable,
)
from src.data.statsbomb import load_shares, save_shares


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True,
                        help="season start year, e.g. 2026")
    parser.add_argument("--leagues", nargs="*", default=sorted(LEAGUE_IDS),
                        help=f"league keys (default: all of {sorted(LEAGUE_IDS)})")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be fetched, spend nothing")
    args = parser.parse_args()

    if args.dry_run:
        print(f"would fetch {len(args.leagues)} leagues x 2 requests = "
              f"{len(args.leagues) * 2} API calls for season {args.season}")
        for key in args.leagues:
            print(f"  {key:<12} -> API-Football league id {LEAGUE_IDS[key]}")
        return 0

    client = APIFootballClient()
    merged: dict[str, list[dict]] = {}
    failures: list[str] = []

    for key in args.leagues:
        try:
            shares = client.squad_shares(key, args.season)
        except APIFootballUnavailable as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2                       # no key / quota: stop, don't loop
        except KeyError as exc:
            failures.append(f"{key}: {exc}")
            continue
        except Exception as exc:           # noqa: BLE001 — one league failing
            failures.append(f"{key}: {type(exc).__name__}: {exc}")
            continue
        if not shares:
            failures.append(f"{key}: no player stats returned (season wrong?)")
            continue
        merged.update(shares)
        print(f"{key:<12} {len(shares):>3} teams  "
              f"(quota left: {client.requests_remaining})")

    if merged:
        before = len(load_shares())
        save_shares(merged)
        print(f"\nmerged {len(merged)} club teams into the shares artifact "
              f"({before} -> {len(load_shares())} teams total)")
    else:
        print("\nnothing merged", file=sys.stderr)

    for line in failures:
        print(f"skipped {line}", file=sys.stderr)
    return 0 if merged else 1


if __name__ == "__main__":
    sys.exit(main())
