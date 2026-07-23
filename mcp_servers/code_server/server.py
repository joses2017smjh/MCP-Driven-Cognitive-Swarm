"""MCP Server 4 — Stateful Code Environment (the compute sandbox).

Gives the swarm the ability the architecture review flagged as missing: to
answer a question nobody hard-coded an endpoint for, by *writing analysis
code* against the project's real datasets and running it under a strict
sandbox.

Tools:
  run_python(code, session_id)  execute a cell; state persists per session
  list_datasets()               what `load(name)` can open, and their columns
  reset_session(session_id)     drop a session's accumulated state

Zero-hallucination math is preserved, not weakened: the LLM still never
computes: it *writes* code, and the deterministic interpreter produces every
number. The Critic can then re-verify those numbers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_servers.common import run_server, with_as_of
from mcp_servers.code_server.sandbox import (
    Session,
    UnsafeCode,
    run_code,
)

server = FastMCP("code-env")

_ROOT = Path(__file__).resolve().parents[2]
_sessions: dict[str, Session] = {}


def available_datasets() -> dict[str, str]:
    """Whitelisted on-disk datasets, only those actually cached locally."""
    candidates = {
        "womens_internationals": _ROOT / "data/raw/womens_international/results.csv",
        "liga_mx": _ROOT / "data/raw/leagues/new_MEX.csv",
        "mls": _ROOT / "data/raw/leagues/new_USA.csv",
        "argentina": _ROOT / "data/raw/leagues/new_ARG.csv",
        "brazil": _ROOT / "data/raw/leagues/new_BRA.csv",
        "epl": _ROOT / "data/raw/leagues/main_E0_2526.csv",
    }
    return {name: str(path) for name, path in candidates.items() if path.exists()}


def do_run(code: str, session_id: str = "default") -> dict[str, Any]:
    session = _sessions.setdefault(session_id, Session(id=session_id))
    try:
        outcome = run_code(code, session=session, datasets=available_datasets())
    except UnsafeCode as exc:
        return with_as_of({
            "ok": False, "error": f"refused by static validation: {exc}",
            "stdout": "", "result": None, "session_id": session_id,
            "cells_in_session": len(session.cells),
        })
    return with_as_of({
        "ok": outcome.ok, "error": outcome.error, "stdout": outcome.stdout,
        "result": outcome.result, "elapsed_ms": round(outcome.elapsed_ms, 1),
        "session_id": session_id, "cells_in_session": len(session.cells),
    })


@server.tool()
def run_python(code: str, session_id: str = "default") -> dict[str, Any]:
    """Run Python for data analysis and return its output.

    Use this for any question the prediction endpoints do not already answer
    (custom aggregations, correlations, filtered splits). Available in the
    namespace: `pd`/`pandas`, `np`/`numpy`, `math`, `statistics`, `json`,
    `datetime`, and `load(name)` to open a dataset from list_datasets().
    Assign your answer to a variable named `result` — it is returned as JSON;
    anything printed is returned as `stdout`.

    State persists per `session_id`, so a later cell sees earlier variables.
    Sandbox rules: no network, no filesystem access, no imports beyond the
    scientific-Python allow-list, and CPU/memory/wall-clock limits. Code that
    breaks these is refused before it runs, with the reason in `error`."""
    return do_run(code, session_id)


@server.tool()
def list_datasets() -> dict[str, Any]:
    """Datasets `load(name)` can open inside run_python, with their columns —
    real match results for the women's internationals and the club leagues."""
    import pandas as pd

    out = []
    for name, path in available_datasets().items():
        try:
            head = pd.read_csv(path, nrows=1)
            out.append({"name": name, "columns": list(head.columns)[:14]})
        except Exception:  # noqa: BLE001
            out.append({"name": name, "columns": []})
    return with_as_of({"datasets": out})


@server.tool()
def reset_session(session_id: str = "default") -> dict[str, Any]:
    """Discard a session's accumulated cells and start clean."""
    _sessions.pop(session_id, None)
    return with_as_of({"ok": True, "session_id": session_id})


if __name__ == "__main__":
    run_server(server)
