# Takshashila University Chatbot

A grounded, multilingual chat widget for Takshashila University's public website.
It answers visitor questions about **admissions & fees, placements, facilities,
transport, courses, and faculty** strictly from an admin-curated knowledge base,
self-computes date-sensitive status, captures consented Admissions leads, and
**learns new knowledge through a human-in-the-loop curation loop**.

## Documentation

| Doc | What's in it |
|-----|--------------|
| [`takshashila-chatbot-requirement.md`](./takshashila-chatbot-requirement.md) | The hardened requirement + TC-001..TC-040 test-case table. |
| [`docs/system-design.md`](./docs/system-design.md) | Architecture, the **human-in-the-loop learning loop**, scale & reliability, trade-offs. |
| [`docs/test-strategy.md`](./docs/test-strategy.md) | Test pyramid, every TC mapped to a test layer, determinism strategy. |
| [`CLAUDE.md`](./CLAUDE.md) | Orientation for contributors (and Claude Code): commands + the load-bearing architecture ideas. |

## Architecture in one line

Stateless FastAPI chat tier + an independently-scaled self-hosted inference tier,
with **deterministic logic separated from the probabilistic LLM** — dates,
validation, rate limits, and boundary checks are pure code; the model only
retrieves grounded content and phrases facts it is handed. See the design doc.

## What's built so far

Test-first (TDD), **100% covered** — **248 backend tests** (+ 1 opt-in real-Postgres)
**plus 41 widget + 64 admin-UI** unit tests and **5 Playwright E2E** specs that pass in
real Chromium = **358 tests**. The full learning loop runs via `make run` — ask an
unanswerable question → it's a dead-end → admin publishes content → the bot answers.
Production wiring (real adapters) is verified against a live Postgres; the widget is
verified end-to-end (streaming, soft-fail, axe accessibility) in a real browser.

**Deterministic domain core** (`src/takshashila_chatbot/domain/`):

```
  clock.py          Clock abstraction (Asia/Kolkata), FixedClock for tests
  admissions.py     admission_status() — open/closed, inclusive close (US-2)
  fees.py           fee_status() — upcoming/due-today/overdue (AC-2.4)
  leads.py          validate_lead() — name, channels, message cap, consent (FR-11/12)
  rate_limit.py     RateLimiter — sliding window, 15/min + 100/hr (FR-14)
  input_guards.py   validate_question() — empty/whitespace, length cap (EC-25/26)
  boundary.py       screen() — injection / abuse / competitor pre-filter (FR-8)
  language.py       detect_language() — Tamil/Latin/mixed by script (FR-7)
  retrieval.py      grounding gate — is_grounded/select_grounded (AC-1.2, NFR-5)
  enrichment.py     compute_facts() — date status as injected ground truth (FR-4/5)
  clustering.py     cluster_questions() — group dead-ends by similarity (AC-9.1)
  retention.py      purge_cutoff() — 12-month retention boundary (FR-18, TC-034)
  content.py        chunk_text() — split a document body into retrieval chunks (US-8)
  auth.py           salted password hash + signed session tokens — admin login (A-1)
```

**Application layer** (`src/takshashila_chatbot/application/`):

```
  ports.py          Retriever / LanguageModel / OutcomeSink boundaries
  prompt.py         render_prompt() — grounding + partial-answer policy (EC-2)
  answer_service.py AnswerService.answer() — guard→boundary→retrieve→gate→
                    enrich→generate→log  (TC-001/002/003/005/007)
  lead_service.py   LeadService.submit() — validate + persist (FR-11/12/13)
  dead_end_clustering.py  DeadEndClusteringService — the learning-loop batch (AC-9.1)
  dashboard.py      DashboardService — ranked dead-ends, volume stats, leads (FR-17)
  retention.py      RetentionService — purge logs + leads past cutoff (FR-18)
  content_service.py  ContentService.save_draft/publish — edit → re-index (US-8)
  session.py        SessionMemory — ephemeral context + follow-up rewrite (FR-9, TC-015/17)
  answer_stream.py  AnswerStreamService — true token-by-token streaming (AC-1.3)
  lead_delivery.py  LeadDeliveryService — email outbox with retry (FR-13, EC-18)
  scheduler.py      Scheduler — interval jobs for the worker (clustering + retention)
  admin_auth.py     AdminAuth — service token + username/password login (clock-injected)
  repositories.py   in-memory log / cluster / lead / content / chunk / session stores
```

A background `worker.py` (`make worker`) ticks the Scheduler to run clustering +
retention on an interval.

**HTTP transport** (`src/takshashila_chatbot/api/`):

```
  app.py            create_app() factory — /chat (SSE), /leads, /health, rate-limit,
                    soft-fail, authed /admin/* (dashboard, cluster, content publish)
  main.py           dev/demo wiring; `make run` demonstrates the full learning loop
```

**Self-hosted adapters** (`src/takshashila_chatbot/adapters/`) — real implementations
behind the ports, no pipeline changes:

```
  vllm_llm.py            VllmLanguageModel — OpenAI-compatible chat (generate + stream_tokens)
  embeddings.py          HttpEmbedder — OpenAI-compatible /v1/embeddings (BGE-M3 class)
  pgvector_retriever.py  PgVectorRetriever — embed + cosine search over published chunks
  pg_lead_repository.py  PgLeadRepository — INSERT…RETURNING + row mapping + purge
  pg_question_log.py     PgQuestionLog — record / dead-ends / volume stats / purge
  pg_dead_end_cluster_repository.py  PgDeadEndClusterRepository — replace-all + ranked
  pg_content_repository.py  PgContentRepository — documents + published versions
  pg_chunk_writer.py     PgChunkWriter — re-index published chunks into kb_chunks
  pg_outbox.py           PgOutboxStore — durable lead-email outbox (EC-18)
  redis_session.py       RedisSessionStore — durable, multi-replica session memory
  db.py                  Executor seam (DB-API 2.0)
  connection_executor.py ConnectionExecutor — adapts a psycopg/DB-API connection
```

**Production wiring & schema**:

```
  config.py         Settings.from_env() — DATABASE_URL, LLM_BASE_URL, models, limits
  wiring.py         build_app() composes the real adapters; build_app_from_env() for prod
  db/schema.sql     kb_chunks (pgvector) / kb_documents / kb_document_versions /
                    fee_items / admission_windows / leads / question_logs / dead_end_clusters
```

`build_app()` is tested end-to-end with only the DB connection and HTTP endpoints
mocked; the schema and the full loop are verified against a live Postgres 16 +
pgvector and over HTTP (`make run` → ask → dead-end → `/admin/content` publish → answered).

**Embeddable widget** (`widget/` — separate vanilla-TS project, Vitest + jsdom):

```
  src/sse.ts         streaming SSE parser
  src/validation.ts  client-side lead validation (mirrors the backend rules)
  src/api.ts         ChatClient — fetch /chat (SSE), /leads, /health; soft-fails
  src/widget.ts      shadow-DOM widget — bubble, panel, streaming, lead form, a11y
  src/embed.ts       single-snippet entry → dist/widget.js (AC-10.1)
```

Shadow-DOM isolated, keyboard/screen-reader accessible (US-10), and soft-fails to
static Admissions contact when the backend is down (AC-10.3, see the demo screenshot
behaviour). The backend serves CORS so the widget can call the API cross-origin.

**Admin web UI** (`admin/` — separate vanilla-TS project, Vitest + jsdom): a polished
analytics SPA over the authenticated admin API — a gated **username/password login**
(exchanged for a signed, auto-expiring session token kept in `sessionStorage`; a 401
mid-session bounces back to login), an operations **dashboard** (KPI cards for total
questions, **answer coverage**, unanswered volume and leads; dependency-free **SVG
charts** for question volume, top topics and the answered-vs-unanswered donut; a ranked
**knowledge-gaps** table with frequency bars and a leads table with delivery-status
pills; "cluster now"), and the content editor (load → edit → save draft → publish).
Responsive, light/dark, accessible. Build + serve it with **`make admin`** (→
http://localhost:5173/; run `make run` for the API, **demo login `admin` / `takshashila`**;
`demo-admin-token` still works as a service/break-glass token); tests via
`npm --prefix admin test`.

All ten user stories (US-1 → US-10) are implemented, plus the multi-replica hardening:
production wiring (`build_app_from_env`) uses the durable **Postgres outbox** and
**Redis session store** (single-instance/dev keeps the in-memory versions). The
**E2E suite** (Playwright + axe, `widget/e2e/` — `cd widget && npm run e2e:install && npm run e2e`)
passes 5/5 in Chromium and caught a real browser-only bug (the widget called the global
`fetch` bound to the wrong `this` — invisible to jsdom). A **k6 load** script lives in
`load/` (run where the k6 binary is available). The only remaining gaps are scale/ops
tuning, not features.

## Quickstart

Requires Python 3.11+ and Docker. The `Makefile` is the entry point — `make help`
lists every target.

```bash
make install     # create .venv, editable-install package + dev deps
make test        # full test suite
make test-unit   # just the deterministic core
make cov         # tests + coverage (term-missing)
```

Run a **single test** (pytest finds `src/` via `pythonpath`, so no install is
strictly required):

```bash
.venv/bin/python -m pytest tests/unit/test_leads.py::test_consent_not_ticked_is_rejected
.venv/bin/python -m pytest -k "overdue or inclusive"   # keyword filter
```

### Run the API (demo)

The demo is seeded from the **real admissions data** in `data/admissions.db`
(courses, fees, hostels, placements, scholarships, transport — see
`ingest/admissions_db.py`), so it answers genuine questions out of the box:

```bash
make run          # uvicorn on http://127.0.0.1:8000 (in-memory demo wiring)

curl http://127.0.0.1:8000/api/v1/health
for q in "What is the application and registration fee?" \
         "hostel fees at Mailam" "transport to Villianoor" \
         "placements at IDFC bank" "B.Tech CSE data science fees"; do
  curl -sN -X POST http://127.0.0.1:8000/api/v1/chat -H 'content-type: application/json' \
    -d "{\"message\":\"$q\",\"session_id\":\"demo\"}"; echo
done
```

The demo uses an echo responder over **TF-IDF keyword retrieval** (no embeddings):
great recall for in-scope questions, but — being keyword-based — it can occasionally
surface an out-of-scope query that shares a word with the data. Production swaps in
the self-hosted LLM + **pgvector semantic retrieval** behind the same ports, which
ranks by meaning and handles out-of-scope correctly. Date status
(`upcoming`/`open`/`overdue`) is computed for real in both.

To load the data into **production** (pgvector), embed the chunks from
`read_admissions_db("data/admissions.db")` with the `HttpEmbedder` and write them via
`PgChunkWriter` (same chunks, real embeddings).

### Local infrastructure & production run

`docker-compose.yml` provisions Postgres+pgvector and Redis; `db/schema.sql` is
applied automatically on a fresh `make up` (and via `make migrate` otherwise):

```bash
make up          # start Postgres+pgvector and Redis (pulls images on first run)
make migrate     # apply db/schema.sql to a running Postgres
make ps          # status   (also: make logs / db-shell / redis-cli)
make down        # stop, keeping data volumes (make clean-all wipes them)
```

Run with the **real adapters** (needs a self-hosted vLLM endpoint, Postgres, and the
`postgres` extra: `pip install -e ".[postgres]"`):

```bash
DATABASE_URL=postgresql://takshashila:takshashila@localhost:5432/takshashila \
LLM_BASE_URL=http://localhost:8001 LLM_MODEL=<served-model> \
make run-prod    # uvicorn --factory build_app_from_env

DATABASE_URL=... LLM_BASE_URL=... make worker   # background clustering + retention
```

### Widget (build, test, embed)

```bash
cd widget
npm install
npm test           # 39 Vitest tests (jsdom)
npm run build      # -> dist/widget.js (single CDN bundle)
# manual preview: serve this dir and open index.html with `make run` going
```

Host sites embed it with one script tag (AC-10.1):

```html
<script src="https://cdn.example/widget.js"
        data-base-url="https://chat.takshashila.edu"
        data-contact-email="admissions@takshashila.edu"
        data-contact-phone="+91-..." data-contact-page="https://.../admissions"></script>
```
