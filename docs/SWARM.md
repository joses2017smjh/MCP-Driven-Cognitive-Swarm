# Cognitive-Swarm Mode

A second orchestration architecture, selectable at request time, so it can be
compared head-to-head against the fixed workflow on the same MCP tools and the
same golden set. Toggle it with `AGENT_MODE=swarm` (global) or `{"mode":
"swarm"}` per request; everything else in the stack is unchanged.

## Why it exists

The fixed workflow (`agent/graph.py`) is a straight line: gather → news →
infer → synthesize. The swarm replaces that with a **supervisor that plans,
delegates, and adversarially verifies** — the topology from the "Advanced
MCP-Driven Cognitive Swarm" brief. Whether that extra machinery pays for
itself is exactly what the A/B report measures (`evals/ab_report.py`).

## The topology (`agent/swarm/`)

| Role in the brief | Implementation | File |
|---|---|---|
| **Global Supervisor** | LangGraph state machine: parse → align → plan → execute → verify → (replan ⟲ \| synthesize) → commit | `supervisor.py` |
| **Strategic Planner (System-2)** | Decomposes the request into a task **DAG**; `topological_layers` groups independent tasks for parallel run | `planner.py` |
| **Knowledge / Memory Agent** | Context alignment (recall insights + rolling calibration) before planning; memory commit after | `memory.py` |
| **Executor Swarm** | Worker functions bind DAG nodes to MCP tools and run a layer **concurrently** in a thread pool | `executor.py` |
| **Critic / Red-Team** | Deterministic adversarial verification; failure triggers a bounded feedback loop back to the planner | `critic.py` |
| **MCP Registry & Discovery** | Capability directory; agents ask for a *capability* ("odds") and get the tool, adapting when a server is down | `registry.py` |

## The execution path

```
parse → align(memory) → plan(DAG)
                              │
        ┌─────────────────────┴─────────────────────┐   ← parallel layer
   gather_stats (data MCP)                    gather_news (news MCP)
        └─────────────────────┬─────────────────────┘
                          infer (ML MCP = compute sandbox)
                              │
                          verify (Critic)
                    ┌─────────┴─────────┐
              issues found          clean / budget spent
              (iteration++,              │
               reset infer) ⟲       synthesize → commit(memory)
```

## The two constraint directives, enforced

- **Zero-hallucination math.** No LLM performs arithmetic anywhere in this
  mode — the deterministic core has no LLM at all, and even with the optional
  LLM planner/critic enabled, all math is delegated to the ML-inference tool
  (the project's stand-in for the "Code Env MCP" compute sandbox: a locked-down
  process that owns every calculation). The **Critic recomputes** the tool's
  arithmetic (outcome sums, EV per market, grid mass, first-scorer
  reconciliation) and flags any drift — verification, not trust.
- **Fail-fast iteration.** `executor._call_with_retry` retries a failing tool
  up to **3 times**, reading the captured error each attempt, before degrading
  the node. The Critic's feedback loop is separately bounded by
  `max_iterations`.

## Red-team checks the Critic runs

Deterministic, cheap, and each one testable (`tests/test_swarm.py`):

- outcome probabilities sum to 1 and lie in [0, 1];
- conformal prediction set present and well-formed;
- expected goals in a plausible range;
- **leakage anomaly** — a 98%+ favourite with a near-level xG gap is flagged as
  probable data leakage (the brief's "99% win rate → check for leakage");
- scoreline grid is a normalized distribution;
- **EV arithmetic recomputed** per market — catches a hallucinated expected
  value;
- first-scorer probabilities reconcile with the grid's P(0-0).

## Honest limitations (what is real vs simplified)

- **Deterministic core, LLM-optional.** Like the workflow-vs-ReAct split, the
  swarm's *structure* runs keyless and is fully tested; the LLM upgrade to the
  Planner and Critic reasoning activates with `ANTHROPIC_API_KEY`. The numeric
  guarantees never depend on the LLM.
- **Memory is a file-backed insight store**, a deliberate simplification of the
  brief's "Semantic Memory Graph (Knowledge Graph + Vector hybrid)". The
  recall/commit interface is what would carry over to a real KG+vector backend
  — the documented next step.
- **The compute sandbox is the existing ML-inference MCP server**, not a fresh
  stateful Jupyter/Docker kernel. It already owns all math deterministically,
  which satisfies the zero-hallucination directive; a true stateful code
  sandbox for open-ended analysis is a future extension.
- **No HITL in swarm mode.** The workflow's human-approval interrupt on staking
  suggestions is not part of the swarm brief; swarm answers therefore never
  emit stakes (the shared renderer withholds them without approval).

## Fidelity — answers to the architecture review

Straight answers to the four questions a sharp reviewer raised, because they
are exactly right to ask them:

**1. Does the ~45 ms swarm latency include LLM inference?** No — and that is
the point, not a trick. The swarm's deterministic core has **no LLM in it at
all**; 45 ms is orchestration plus the deterministic MCP tool calls (XGBoost,
Dixon-Coles, Elo). A single Anthropic/OpenAI call is ~0.5–2 s, so any
LLM-in-the-loop mode is necessarily far slower — that is what the react arm
measures. The A/B report now states this in a banner so "swarm is fast" can
never be misread as "multi-agent-with-LLMs is fast."

**2. The compute sandbox is the ML-inference server, not a stateful code
env.** Correct, and it is a real limitation: the executor passes data to a
pre-trained endpoint, so it cannot write *novel* Python to answer an
unanticipated statistical query ("win rate in heavy rain by formation"). For
the fixed prediction task this is the right, safe trade; for open-ended
analysis it is not. The honest upgrade is a locked-down, ephemeral
code-execution MCP server (sandboxed subprocess: no network/filesystem,
resource + time limits, AST allow-list) that the executor drives with the
fail-fast retry loop. That is scoped as the next increment, not silently
claimed as done.

**3. Is the Critic an LLM recomputing math?** No — it is a **deterministic
Python validation module** (`critic.py`), by design. LLMs cannot be trusted
with arithmetic, so having the Critic *compute* would violate the very
directive it enforces. So yes: today it is closer to "runtime assertions over
the pipeline output" than an adversarial *language* agent — a fair
characterization. The intended full form keeps the deterministic numeric
checks as the ground truth and adds an LLM layer for **semantic** critique
only (does the rationale match the evidence? is the uncertainty communicated?),
and that LLM would call the deterministic checks as tools, never its own
weights for math.

**4. Flat-file memory will overflow the planner's context.** Right. `recall`
already never dumps the file — it filters by concept and hard-caps to the few
most recent matches (`RECALL_CAP`), so what reaches context is bounded today.
The documented **migration threshold**: at ~10k stored insights, or as soon as
recall needs semantic rather than substring matching, swap the file backend
for a local vector store (Chroma / LanceDB) behind the unchanged
`recall`/`commit` interface.

## Comparison (current, deterministic, keyless)

From `evals/ab_report.py` on the golden set:

| metric | workflow (fixed graph) | swarm (planner+critic) |
|---|---|---|
| task success | 100% | 100% |
| mean latency | ~57 ms | ~45 ms |
| cost/request | $0.00 | $0.00 |

The swarm is *faster* here because `gather_stats` and `gather_news` run
concurrently instead of sequentially — a genuine win from the parallel DAG.
Its distinct value is the adversarial Critic (≈9 verification checks per run)
and the discovery/planning layer that routes around down servers, neither of
which the fixed workflow has. Whether that verification catches real defects
the workflow would ship is the question the mode exists to answer as the model
and data mature.
