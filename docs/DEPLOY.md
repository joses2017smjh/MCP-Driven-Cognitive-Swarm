# Deployment guide

## The one thing to understand first

The gateway has two modes, set by `AGENT_RUNNER`:

- **`inprocess` (default)** — the gateway calls the three MCP servers' logic as
  in-process Python. You deploy **one backend container** (gateway) + the UI.
- **`mcp`** — the gateway is an MCP *client* talking to three separate server
  containers over Streamable HTTP. This is `docker-compose.yml` (5 services),
  for demonstrating the distributed topology.

For a live portfolio URL, use `inprocess`. Nothing about the prediction output
changes — the same tools run, just as function calls instead of HTTP.

**No CORS setup is ever needed:** the browser only talks to the Next.js app's
own `/api/*` Route Handlers, which proxy to the gateway server-side and attach
`GATEWAY_API_KEY`. The gateway is never exposed to the browser.

## Environment variables

| var | where | purpose |
|---|---|---|
| `GATEWAY_URL` | UI | server-side URL of the gateway (never shipped to browser) |
| `GATEWAY_API_KEY` | UI **and** gateway | shared secret; UI attaches it, gateway requires it |
| `AGENT_RUNNER` | gateway | `inprocess` (default) or `mcp` |
| `PREDICT_RATE_LIMIT` | gateway | e.g. `5/minute` per IP on the agent routes |
| `DATA_BACKEND` | gateway | `demo` (default) or `football_data` (real stats) |
| `ANTHROPIC_API_KEY` | gateway | optional; enables ReAct mode + LLM judge |
| `REDIS_URL` | gateway | optional; shared rate-limit store across replicas |

Generate a key with `openssl rand -hex 16`.

---

## Option A — Local (see it run on your machine)

```bash
GATEWAY_API_KEY=$(openssl rand -hex 16) \
  docker compose -f docker-compose.simple.yml up --build
# UI → http://localhost:3000   ·   gateway → http://localhost:8000
```

Or without Docker, two terminals:

```bash
# terminal 1 — backend
GATEWAY_API_KEY=devkey uvicorn gateway.app:app --port 8000
# terminal 2 — frontend
cd ui && GATEWAY_URL=http://localhost:8000 GATEWAY_API_KEY=devkey npm run dev
```

## Option B — One cheap VM (shows the full distributed architecture)

Any small VM works (DigitalOcean $6/mo droplet, GCP `e2-micro`, Oracle Cloud
always-free). ~1 GB RAM is enough for the demo model.

```bash
# on the VM, with Docker + compose plugin installed
git clone https://github.com/joses2017smjh/Agentic-Soccer-Match-Prediction-MCP.git
cd Agentic-Soccer-Match-Prediction-MCP
export GATEWAY_API_KEY=$(openssl rand -hex 16)
docker compose up -d --build          # all 5 services (distributed MCP)
```

Open port 3000 in the firewall (and 8000 only if you want the raw API public).
For a domain + HTTPS, put Caddy in front of the UI — a two-line Caddyfile
(`your-domain { reverse_proxy localhost:3000 }`) gets you automatic TLS.

## Option C — Split managed, mostly free (cleanest portfolio URL)

**Frontend → Vercel** (native Next.js, auto-deploys from GitHub):

1. Import the repo at vercel.com; set **Root Directory = `ui`**.
2. Add env vars: `GATEWAY_URL` = your backend URL (from the next step),
   `GATEWAY_API_KEY` = your key.
3. Deploy. Vercel gives you `https://<project>.vercel.app`.

**Backend → Render / Railway / Fly.io** (one container, `inprocess`):

- **Render**: New → Web Service → the repo → *Docker* environment (uses the root
  `Dockerfile`). Add env vars `GATEWAY_API_KEY`, `PREDICT_RATE_LIMIT=5/minute`,
  `AGENT_RUNNER=inprocess`. Render gives `https://<svc>.onrender.com` — put that
  in Vercel's `GATEWAY_URL`. (Free tier sleeps on idle; first request after
  idle is slow. Fine for a portfolio.)
- **Fly.io**: `fly launch` (detects the Dockerfile), `fly secrets set
  GATEWAY_API_KEY=…`, `fly deploy`.

The two deploys are independent; the UI reaches the backend only via
`GATEWAY_URL`, so update that one var if the backend URL changes.

---

## Verify any deployment

`scripts/smoke_test.sh` drives every capability against a running gateway:

```bash
BASE=https://<your-backend> KEY=<your-key> ./scripts/smoke_test.sh
```

It checks: health, full layered prediction (outcome + conformal set +
scoreline grid + headline scenario + evidence trail), the HITL interrupt on a
value-bet request, approval resume, the 422 on unparseable input, and the
reflection + calibration loop. 14 checks; exit code is nonzero on any failure,
so it works as a post-deploy gate.

## Notes for a public deploy

- **Set `GATEWAY_API_KEY`.** The rate limit slows abuse; the key stops it.
- **Served model is the synthetic demo bundle.** To serve a real trained
  bundle, build it (`scripts/build_demo_artifacts.py` is the template) and
  mount it at `ARTIFACT_ROOT`.
- **`ANTHROPIC_API_KEY` is optional.** Without it the deterministic workflow
  runs (keyless); with it the ReAct follow-up mode and LLM judge activate.
