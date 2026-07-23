"""Tests for the code-execution sandbox.

The security cases are the point of this file: every one of them is an
attempted escape that must be refused. They run the real sandbox, not a mock
— a regression here is a genuine vulnerability, so it must fail loudly.
"""

from __future__ import annotations

import pytest

from mcp_servers.code_server.sandbox import (
    MAX_CELLS_PER_SESSION,
    Session,
    UnsafeCode,
    run_code,
    validate_code,
)

ESCAPES = [
    ("os import", "import os\nresult = os.listdir('/')"),
    ("os from-import", "from os import getcwd\nresult = getcwd()"),
    ("subprocess", "import subprocess\nresult = subprocess.run(['ls'])"),
    ("socket", "import socket\nresult = socket.socket()"),
    ("urllib exfiltration", "import urllib.request\nresult = urllib.request.urlopen('http://x')"),
    ("requests exfiltration", "import requests\nresult = requests.get('http://x')"),
    ("pickle", "import pickle\nresult = pickle.loads(b'')"),
    ("ctypes", "import ctypes\nresult = 1"),
    ("file read", "result = open('/etc/passwd').read()"),
    ("eval", "result = eval('1+1')"),
    ("exec", "exec('import os')"),
    ("compile", "result = compile('1', '<s>', 'eval')"),
    ("dunder mro escape", "result = ().__class__.__mro__[1].__subclasses__()"),
    ("dunder globals", "def f(): pass\nresult = f.__globals__"),
    ("builtins reach", "result = [].__class__.__base__"),
    ("__import__", "result = __import__('os').getcwd()"),
    ("globals()", "result = globals()"),
    ("locals()", "result = locals()"),
]


@pytest.mark.parametrize("name,code", ESCAPES, ids=[n for n, _ in ESCAPES])
def test_escape_attempts_are_refused(name: str, code: str) -> None:
    """Static validation must reject every known breakout before execution."""
    with pytest.raises(UnsafeCode):
        validate_code(code)


def test_oversized_code_refused() -> None:
    with pytest.raises(UnsafeCode, match="exceeds"):
        validate_code("x = 1\n" * 20000)


def test_syntax_error_is_reported_as_unsafe() -> None:
    with pytest.raises(UnsafeCode, match="SyntaxError"):
        validate_code("def (:")


def test_allowed_scientific_imports_pass() -> None:
    validate_code("import pandas as pd\nimport numpy as np\nimport math\n"
                  "from statistics import mean\nresult = mean([1, 2])")


# --------------------------------------------------------------- execution

def test_runs_real_computation() -> None:
    out = run_code("result = sum(range(101))")
    assert out.ok, out.error
    assert out.result == 5050


def test_stdout_is_captured() -> None:
    out = run_code("print('hello from the sandbox')\nresult = 1")
    assert out.ok and "hello from the sandbox" in out.stdout


def test_pandas_and_numpy_available() -> None:
    out = run_code(
        "import pandas as pd\nimport numpy as np\n"
        "df = pd.DataFrame({'x': [1, 2, 3]})\n"
        "result = {'sum': int(df.x.sum()), 'mean': float(np.mean(df.x))}"
    )
    assert out.ok, out.error
    assert out.result == {"sum": 6, "mean": 2.0}


def test_runtime_import_guard_holds_independently_of_ast() -> None:
    """Defence in depth: even if the AST layer were bypassed, the child's
    guarded __import__ must still refuse a non-allow-listed module."""
    from mcp_servers.code_server import sandbox as sb

    # bypass the static layer deliberately to exercise the runtime guard
    original = sb.validate_code
    sb.validate_code = lambda _code: None
    try:
        out = sb.run_code("import os\nresult = 1")
    finally:
        sb.validate_code = original
    assert not out.ok
    assert "not allowed in the sandbox" in out.error


def test_runtime_error_is_reported_not_raised() -> None:
    out = run_code("result = 1 / 0")
    assert not out.ok
    assert "ZeroDivisionError" in out.error


def test_infinite_loop_is_killed() -> None:
    """CPU rlimit / wall clock must stop a runaway cell."""
    out = run_code("while True:\n    pass", timeout_s=15, cpu_seconds=2)
    assert not out.ok
    assert "timeout" in out.error or "aborted" in out.error


def test_memory_bomb_is_contained() -> None:
    out = run_code("x = bytearray(400 * 1024 * 1024)\nresult = len(x)",
                   memory_mb=128, timeout_s=30)
    assert not out.ok


# ----------------------------------------------------------------- sessions

def test_session_state_persists_across_cells() -> None:
    session = Session(id="t")
    assert run_code("base = 20", session=session).ok
    out = run_code("result = base + 22", session=session)
    assert out.ok and out.result == 42
    assert len(session.cells) == 2


def test_failed_cells_are_not_recorded() -> None:
    """A broken cell must not poison the replay for later cells."""
    session = Session(id="t2")
    assert run_code("good = 1", session=session).ok
    assert not run_code("result = undefined_name", session=session).ok
    assert len(session.cells) == 1
    assert run_code("result = good + 1", session=session).ok


def test_session_cell_cap_enforced() -> None:
    session = Session(id="t3", cells=["x = 1"] * MAX_CELLS_PER_SESSION)
    with pytest.raises(UnsafeCode, match="reset it"):
        run_code("result = 1", session=session)


# ------------------------------------------------------------ mcp surface

def test_server_refusal_is_data_not_exception() -> None:
    """The MCP tool must return the refusal, never blow up the caller."""
    from mcp_servers.code_server.server import do_run

    out = do_run("import os")
    assert out["ok"] is False
    assert "static validation" in out["error"]
    assert "as_of" in out


def test_dataset_loading_inside_sandbox() -> None:
    from mcp_servers.code_server.server import available_datasets, do_run

    if not available_datasets():
        pytest.skip("no datasets cached in this environment")
    name = sorted(available_datasets())[0]
    out = do_run(f"df = load({name!r})\nresult = int(len(df))")
    assert out["ok"], out["error"]
    assert isinstance(out["result"], int) and out["result"] > 0


def test_unknown_dataset_reports_available_ones() -> None:
    from mcp_servers.code_server.server import available_datasets, do_run

    if not available_datasets():
        pytest.skip("no datasets cached in this environment")
    out = do_run("result = load('not_a_dataset')")
    assert not out["ok"] and "unknown dataset" in out["error"]


def test_registry_advertises_code_capability() -> None:
    from agent.swarm.registry import ToolRegistry

    spec = ToolRegistry().find_one("custom_query")
    assert spec is not None and spec.server == "code-env"
