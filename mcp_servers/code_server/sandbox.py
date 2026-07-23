"""Sandbox front door: static validation + supervised subprocess execution.

Answers the architecture review's point ②: the swarm can now write *new*
Python to answer an unanticipated question, instead of only calling a
pre-trained inference endpoint.

Two layers:

**Static (this module).** The code is parsed and walked before it ever runs.
Only allow-listed imports survive, and the classic escape routes are refused
outright — ``eval``/``exec``/``open``/``__import__`` and *any* dunder
attribute access, which is how ``().__class__.__mro__`` style breakouts
reach the interpreter.

**Dynamic (runner.py).** A separate process with POSIX rlimits (CPU, memory,
file size), sockets stubbed out, restricted builtins, and a wall-clock kill.

Statefulness is deterministic *cell replay*: a session stores the cells that
succeeded, and each new cell re-runs them first. That buys reproducible
state without pickling a live interpreter across a trust boundary; the cost
is re-execution, so sessions are capped.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ALLOWED_IMPORTS = frozenset({
    "math", "statistics", "json", "datetime", "collections", "itertools",
    "functools", "re", "decimal", "fractions", "random", "numpy", "pandas",
})

BLOCKED_NAMES = frozenset({
    "eval", "exec", "compile", "open", "__import__", "input", "exit", "quit",
    "help", "breakpoint", "globals", "locals", "vars", "getattr", "setattr",
    "delattr", "memoryview", "__builtins__", "__loader__", "__spec__",
})

MAX_CELLS_PER_SESSION = 25
MAX_CODE_CHARS = 20_000


class UnsafeCode(ValueError):
    """Static validation refused the code before execution."""


def validate_code(code: str) -> None:
    """Raise UnsafeCode unless every construct is on the allow-list."""
    if len(code) > MAX_CODE_CHARS:
        raise UnsafeCode(f"code exceeds {MAX_CODE_CHARS} characters")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise UnsafeCode(f"SyntaxError: {exc}") from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    raise UnsafeCode(f"import of {alias.name!r} is not allowed")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in ALLOWED_IMPORTS:
                raise UnsafeCode(f"import from {node.module!r} is not allowed")
        elif isinstance(node, ast.Attribute):
            # blocks ().__class__.__mro__[1].__subclasses__() style escapes
            if node.attr.startswith("__") and node.attr.endswith("__"):
                raise UnsafeCode(f"dunder attribute access {node.attr!r} is not allowed")
        elif isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            raise UnsafeCode(f"use of {node.id!r} is not allowed")


@dataclass
class SandboxResult:
    ok: bool
    stdout: str = ""
    result: object = None
    error: str = ""
    elapsed_ms: float = 0.0


@dataclass
class Session:
    """Successfully-executed cells, replayed to rebuild state."""

    id: str
    cells: list[str] = field(default_factory=list)


def run_code(
    code: str,
    *,
    session: Session | None = None,
    datasets: dict[str, str] | None = None,
    timeout_s: float = 20.0,
    cpu_seconds: int = 10,
    memory_mb: int = 512,
) -> SandboxResult:
    """Validate, then execute in a supervised subprocess.

    On success the cell is appended to ``session`` so later cells see its
    state; failures are never recorded, keeping the replay deterministic.
    """
    validate_code(code)
    prior = list(session.cells) if session else []
    if len(prior) >= MAX_CELLS_PER_SESSION:
        raise UnsafeCode(
            f"session exceeded {MAX_CELLS_PER_SESSION} cells; reset it"
        )

    payload = {
        "cells": [*prior, code],
        "datasets": datasets or {},
        "allowed_imports": sorted(ALLOWED_IMPORTS),
        "limits": {"cpu_seconds": cpu_seconds, "memory_mb": memory_mb},
    }
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "mcp_servers.code_server.runner"],
            input=json.dumps(payload), capture_output=True, text=True,
            timeout=timeout_s, cwd=str(Path(__file__).resolve().parents[2]),
        )
    except subprocess.TimeoutExpired:
        return SandboxResult(
            ok=False, error=f"timeout: exceeded {timeout_s}s wall clock",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )
    elapsed = (time.monotonic() - start) * 1000

    if proc.returncode != 0 or not proc.stdout.strip():
        detail = (proc.stderr or "").strip().splitlines()
        reason = detail[-1] if detail else f"exit code {proc.returncode}"
        return SandboxResult(ok=False, error=f"sandbox aborted: {reason}",
                             elapsed_ms=elapsed)

    verdict = json.loads(proc.stdout.strip().splitlines()[-1])
    if verdict["ok"] and session is not None:
        session.cells.append(code)
    return SandboxResult(
        ok=verdict["ok"], stdout=verdict.get("stdout", ""),
        result=verdict.get("result"), error=verdict.get("error", ""),
        elapsed_ms=elapsed,
    )
