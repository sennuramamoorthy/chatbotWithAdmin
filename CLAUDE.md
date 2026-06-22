# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status (read first)

Built so far (test-first, 100% covered): the **deterministic domain core**
(`domain/`), the **answer pipeline** (`application/answer_service.py` + ports), the
**lead service** (`application/lead_service.py`), the **FastAPI transport layer**
(`api/`: `/chat` SSE, `/leads`, `/health`, rate limiting, soft-fail), and the
**self-hosted adapters** (`adapters/`: vLLM LLM, embeddings, pgvector retriever,
Postgres lead repo, question log, dead-end cluster repo + `ConnectionExecutor`), the
**production wiring** (`config.py`, `wiring.py` `build_app`/`build_app_from_env`,
`db/schema.sql`), and the **human-in-the-loop learning loop**: dead-end logging →
similarity clustering (`domain/clustering.py`) → frequency-ranked admin dashboard
(`/admin/*`, bearer-token auth) → **content publish/re-index** (`content_service.py`:
edit a draft, Publish chunks + embeds it into `kb_chunks`, the bot then answers it) →
retention purge (`domain/retention.py`). Adapters are tested with `httpx.MockTransport`
+ a fake SQL `Executor`; `build_app` is tested end-to-end with mocked edges; the
schema, the real-driver roundtrip, and the **full loop closing** are verified against
a live Postgres and over HTTP. The visitor-facing **embeddable widget** is a separate
vanilla-TS project in `widget/` (shadow-DOM isolated, accessible, soft-failing;
Vitest + jsdom, 100% covered); the backend serves CORS for cross-origin embedding.

**Two wirings:** `make run` → demo (`api/main.py`: in-memory fakes + echo responder +
`HashingEmbedder`, a deterministic bag-of-words embedder so the demo learning-loop
clusters rank distinctly; production uses the real `HttpEmbedder`). The admin dashboard
reads an **answer-coverage** stat (`VolumeStats.answered_count`/`dead_end_count`) and is
behind a **username/password login** (demo `admin` / `takshashila`; `domain/auth.py` +
`application/admin_auth.py` → `POST /admin/login` issues a signed, clock-expiring session
token; the old `demo-admin-token` still works as a service/break-glass token).
`make run-prod` → real adapters via `wiring.build_app_from_env` (needs `DATABASE_URL`,
`LLM_BASE_URL`, the `postgres` extra, and live infra). psycopg is an optional extra;
it is imported lazily only in `build_app_from_env`, so the core suite never needs it.

Also wired: **true token streaming** (`answer_stream.py` → `/chat`, via the vLLM
adapter's `stream_tokens`), **session memory + follow-up rewrite** (`session.py`),
**lead-delivery outbox** (`lead_delivery.py`, enqueued on lead submit), a **background
worker** (`worker.py` + `scheduler.py`, `make worker`) for clustering + retention, and
a separate **admin web UI** (`admin/`). All ten user stories (US-1..US-10) are
implemented end-to-end.

**Multi-replica hardening (done):** production wiring (`build_app_from_env`) uses the
durable **Postgres outbox** (`adapters/pg_outbox.py`, `outbox` table) and **Redis
session store** (`adapters/redis_session.py`); `build_app` defaults to the in-memory
versions for single-instance/dev (both behind the `OutboxStore`/`SessionStore` ports).
Prod needs the `postgres` + `redis` extras (`pip install -e ".[postgres,redis]"`).
Browser **E2E** (Playwright + axe, `widget/e2e/`, run via `cd widget && npm run e2e`)
passes 5/5 in Chromium — it caught a real browser-only bug (the widget invoked the
global `fetch` with `this === ChatClient` → "Illegal invocation", invisible to jsdom;
fixed in `widget/src/api.ts` by binding to `globalThis`, with a regression test). The
**admin client** (`admin/src/api.ts`) had the identical bug — fixed the same way + a
regression test, and verified loading the dashboard in a real browser. A **k6 load**
script lives in `load/` (run where the k6 binary exists).

The source of truth for *what* to build is
[`takshashila-chatbot-requirement.md`](./takshashila-chatbot-requirement.md): a
hardened requirement whose acceptance criteria and edge cases all trace to a
test-case table (TC-001..TC-040). The *how* lives in
[`docs/system-design.md`](./docs/system-design.md) (architecture, the
human-in-the-loop learning loop, scale, trade-offs) and
[`docs/test-strategy.md`](./docs/test-strategy.md) (every TC mapped to a test layer).

## Commands

Requires Python 3.11+ and Docker. The `Makefile` is the entry point (`make help`):

```bash
make install     # create .venv, editable-install package + dev deps
make test        # full pytest suite
make test-unit   # only the deterministic core (pytest -m unit)
make cov         # tests + coverage (term-missing)
make run         # dev/demo API server (uvicorn :8000, demo wiring)
make run-prod    # API with REAL adapters (needs DATABASE_URL + LLM_BASE_URL + infra)
make worker      # background worker: clustering + retention on a schedule
make admin       # build + serve the admin web UI (static, :5173; needs make run for the API)
make up          # start Postgres+pgvector and Redis (docker compose, background)
make migrate     # apply db/schema.sql to a running Postgres
make down        # stop infra (volumes kept); make ps / logs / db-shell / redis-cli
make clean-all   # remove venv + infra volumes (destroys local data)
```

Run a **single test** (pytest finds `src/` via `pythonpath` in `pyproject.toml`,
so no install is strictly required):

```bash
.venv/bin/python -m pytest tests/unit/test_leads.py::test_consent_not_ticked_is_rejected
.venv/bin/python -m pytest -k "overdue or inclusive"        # keyword filter
.venv/bin/python -m pytest -m integration                   # by marker (unit | integration)
```

`docker-compose.yml` provisions **only the datastores** (Postgres+pgvector for
content/leads/logs/vectors, Redis for session/rate-limit/cache/broker). The app
and the self-hosted inference tier (vLLM + embeddings, GPU) are later increments.
No linter is configured yet.

The **widget** is a separate TS project: `cd widget && npm install && npm test`
(Vitest + jsdom), `npm run build` → `dist/widget.js`. Its lead validation and SSE
framing mirror the backend — keep them in sync if the backend contract changes.

## Architecture — the load-bearing ideas

These span multiple files and the design doc; internalize them before changing code.

**1. Separate the deterministic from the probabilistic.** This is the spine of the
whole system. Anything that *must* be correct — date status, lead validation, rate
limits, retention, first-pass boundary checks, admin auth (password hashing + signed
session tokens) — is pure, dependency-injected code in `domain/`, exhaustively
unit-tested. The LLM is *only* allowed to retrieve grounded
content and phrase facts it is handed. It never computes dates and never answers
without retrieved content (the "grounding gate"). This is what makes "zero fabricated
answers" and "correct on the day you ask" achievable with a probabilistic model.

**2. Time is injected, never read directly.** `domain/clock.py` defines a `Clock`
(business timezone = `Asia/Kolkata`); production uses `SystemClock`, tests use
`FixedClock`. `admission_status` / `fee_status` / the rate limiter all take a clock or
an explicit `today`. **Never call `datetime.now()` in logic** — it breaks determinism
and the inclusive-close / due-date semantics. Admission close is *inclusive* (open
through the end of the close date).

**3. The "learning" loop is human-in-the-loop curation, not auto-ingestion.** The bot
expands its knowledge only through admin-curated, explicitly-published content — a
human authorizes every new fact (the anti-fabrication guarantee). The loop:
unanswered questions are logged as dead-ends → a **batch** worker clusters & ranks
them by frequency → the admin dashboard surfaces the top gaps → admin curates and
clicks **Publish** → only changed chunks are re-embedded/re-indexed (≤~2 min) → future
asks are answered. The only synchronous cost is a fire-and-forget log write, which is
why the loop scales. (Full diagram: design doc §3.)

**4. External dependencies sit behind interfaces, with fakes in tests.** LLM,
embeddings, vector store, email sender, and the rate-limit store are abstractions.
Unit/integration tests inject fakes (deterministic); a *separate, thresholded* eval
suite is the only thing that hits a real model. **Assert properties, not transcripts**
for LLM output (e.g. "contains the fee figure", "reply is in Tamil script", "no
competitor name") — never exact strings.

**5. Self-hosted for data residency (DPDP).** LLM + embeddings + vector store are
self-hosted by design; question logs carry **no visitor identity** and are purged at
12 months; lead PII requires explicit consent. Keep these invariants when adding code
that touches logs or leads.

## Conventions

- **TDD, test-first.** Each change traces to a TC in the requirement doc; P0 rows lead.
  Write the failing test (red), make it pass (green), refactor. Keep `domain/` at 100%.
- **`src/` layout**, package `takshashila_chatbot`. Pure logic goes in `domain/`
  (no I/O); I/O and orchestration belong in the (future) app/service layers behind
  interfaces.
- Validation returns **structured field errors** (see `domain/leads.py`), not
  exceptions, so the API can surface inline messages.
- Boundary rules favor **precision** — when unsure, allow through to the grounded
  pipeline rather than wrongly blocking a legitimate question.
