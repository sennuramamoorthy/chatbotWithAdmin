# Test Strategy — Takshashila Chatbot (TDD)

> Companion to [`system-design.md`](./system-design.md). Maps every requirement
> test case (TC-001 → TC-040) to a test layer, defines how we test a *probabilistic*
> LLM deterministically, and lists what is built test-first in this session.

---

## 1. Philosophy

1. **TDD red→green→refactor.** Write the failing test that encodes an acceptance
   criterion, make it pass with the simplest code, then refactor. The requirement's
   TC table is the backlog; P0 rows lead.
2. **Push correctness into deterministic, pure code.** Everything that *must* be
   correct (dates, validation, rate limits, retention, first-pass boundary) is pure
   logic with injected dependencies — exhaustively unit-tested, zero flakiness.
3. **Isolate the probabilistic.** The LLM, embeddings, vector store, email, and clock
   sit behind interfaces. Tests inject **fakes**; only the dedicated eval suite touches
   a real model.
4. **Assert properties, not transcripts.** For LLM output we never assert exact
   strings — we assert *invariants*: "answer contains the fee figure", "reply is in
   Tamil script", "no competitor name appears", "fallback markers present".

---

## 2. Test pyramid & layers

```
        ▲  fewer, slower, higher-fidelity
        │   ┌─────────────────────────────────────────────┐
        │   │ E2E / UI (Playwright + axe-core)             │  embed, responsive,
        │   │                                              │  a11y, soft-fail, latency
        │   ├─────────────────────────────────────────────┤
        │   │ Eval / golden-set (real LLM, thresholded)    │  grounding, multilingual,
        │   │                                              │  boundary semantics
        │   ├─────────────────────────────────────────────┤
        │   │ Integration (API + test Postgres + fakes)    │  pipeline, leads+outbox,
        │   │                                              │  publish/reindex, purge
        │   ├─────────────────────────────────────────────┤
        │   │ Unit (pure domain logic, injected clock)     │  dates, validation,
        │   │  ★ built this session                        │  rate limit, guards, boundary
        ▼   └─────────────────────────────────────────────┘
            more, fast, deterministic
```

| Layer | Runs against | Determinism | Tooling |
|-------|--------------|-------------|---------|
| **Unit** | Pure functions | Fully deterministic (injected `Clock`) | pytest |
| **Integration** | FastAPI + ephemeral Postgres + **fake** LLM/embeddings/vector/email | Deterministic | pytest + httpx + testcontainers |
| **Eval / golden-set** | **Real** self-hosted model + curated Q&A set | Thresholded (non-deterministic) — separate CI gate, not per-run pass/fail | pytest + eval harness |
| **E2E / UI** | Built widget in a browser | Deterministic w/ stubbed backend | Playwright, axe-core |
| **Load** | Full stack under synthetic load | Statistical | k6 / Locust |

**Why a separate eval gate:** LLM phrasing varies run-to-run. Asserting it like a unit
test produces flaky CI. Instead the eval suite runs the golden set, scores property
checks (grounded? right language? refused?), and gates on an **aggregate threshold**
(e.g. ≥98% grounded, 0 fabrications, 0 competitor mentions). Determinism-sensitive
pieces (retrieval, date enrichment) are tested with **fakes** at the integration layer
so they stay hard pass/fail.

---

## 3. Determinism strategy (the enablers)

- **`Clock` interface** → `SystemClock` (prod, `Asia/Kolkata`) and `FixedClock` (tests).
  Used by date logic, rate limiter, retention purge. No production logic ever calls
  `datetime.now()` directly. This is what makes every date-boundary TC reproducible.
- **`LanguageModel`, `Embedder`, `VectorStore`, `EmailSender` interfaces** → real impls
  in prod, fakes in tests. A `FakeVectorStore` returns scripted chunks/scores so the
  grounding gate and fallback are deterministic (TC-001/002/003).
- **`RateLimitStore` interface** → in-memory (tests/single-node) and Redis (prod).

---

## 4. Full traceability — every TC → layer

| TC | Scenario | Layer(s) | Notes / how |
|----|----------|----------|-------------|
| TC-001 | In-scope KB answer + latency | Integration (fake retrieval) + Eval (accuracy) + E2E (latency) | Property: answer contains KB fee; first token <2s measured in E2E/load. |
| TC-002 | Unknown → fallback | **Unit** (grounding gate) + Integration | FakeVectorStore returns below-threshold → fallback; no LLM call; dead_end logged. |
| TC-003 | Partial answer | Integration + Eval | Mixed retrieval; assert known part present, unknown flagged + handoff. |
| TC-004 | Admission open before close | **Unit** `admissions` | `admission_status` OPEN. |
| TC-005 | Admission closed after close (no edit) | **Unit** `admissions` | Past close → CLOSED, computed. |
| TC-006 | Admission on exact close date | **Unit** `admissions` | today==close → OPEN (inclusive). |
| TC-007 | Fee overdue | **Unit** `fees` | Past due → OVERDUE. |
| TC-008 | Fee upcoming | **Unit** `fees` | Future due → UPCOMING. |
| TC-009 | Tamil question | Eval (multilingual) + Integration | Property: reply in Tamil script, fee figure present. |
| TC-010 | Mixed Tamil-English | Eval + Integration | Code-switched query retrieves EN chunk; understood. |
| TC-011 | Off-topic homework | Eval (semantic redirect) | Prompt/grounding backstop; polite redirect, not attempted. |
| TC-012 | Prompt injection | **Unit** `boundary` + Eval | Rule pre-filter catches; stays in role, redirects. |
| TC-013 | Competitor comparison | **Unit** `boundary` + Eval | Decline ranking/criticism. |
| TC-014 | Abuse, repeated | **Unit** `boundary` | Calm boundary; **idempotent** on repeat (no escalation). |
| TC-015 | Contextual follow-up | Integration (query rewrite) + Eval | "and the M.Tech?" rewritten using session. |
| TC-016 | Context across pages | Integration | Redis session survives page change. |
| TC-017 | Context expires | **Unit** (TTL logic) + Integration | After idle → fresh; no stale context. |
| TC-018 | Lead capture on dead-end | **Unit** `leads` (validation) + Integration (delivery) | Valid lead → DB + email enqueued + confirmation. |
| TC-019 | Always-available "Talk to Admissions" | E2E | Form opens on demand; not proactive mid-answer. |
| TC-020 | Lead name blank | **Unit** `leads` | Reject, inline error on name. |
| TC-021 | Invalid email, no phone | **Unit** `leads` | Reject; contact-field error; no lead. |
| TC-022 | Implausible phone | **Unit** `leads` | 7-digit → reject, phone error. |
| TC-023 | One valid channel only | **Unit** `leads` | Valid phone, blank email → accept. |
| TC-024 | Over-long message | **Unit** `leads` | >1000 chars → blocked w/ notice. |
| TC-025 | Consent not ticked | **Unit** `leads` | Submit blocked until consent. |
| TC-026 | Lead email failure | Integration (outbox) | Email fake fails → lead persisted, flagged, retried. |
| TC-027 | Per-visitor rate limit | **Unit** `rate_limit` + Integration | >15/min → slow-down; deterministic via FixedClock. |
| TC-028 | Peak-load degradation | Load | Queue/"busy"; no hard errors. |
| TC-029 | Backend/LLM outage soft-fail | Integration + E2E | Inference down → 503 + static contact; widget shows contact. |
| TC-030 | Edit without Publish hidden | Integration | Draft not retrieved; last published served. |
| TC-031 | Publish goes live + timestamp | Integration | Reindex → new value; last_updated set. |
| TC-032 | Dashboard dead-ends ranked | **Unit** (cluster ranking) + Integration | Grouped by similarity, ranked by frequency. |
| TC-033 | Dashboard volume + leads | Integration | Stats + leads list returned. |
| TC-034 | Logs no identity + purge | **Unit** (purge selector) + Integration | No identity column; >12mo purged. |
| TC-035 | Single-snippet responsive embed | E2E | Bubble appears, opens, responsive, no hijack. |
| TC-036 | Accessibility | E2E (axe + keyboard) | Keyboard-operable, screen-reader-announced. |
| TC-037 | Empty/whitespace question | **Unit** `input_guards` | No LLM call; prompt to type. |
| TC-038 | Sensitive info in chat | Integration | Logged w/o identity; within purge window. |
| TC-039 | Over-long single question | **Unit** `input_guards` | Beyond cap → prompt to shorten. |
| TC-040 | Mid-edit publish ships only published | Integration | Only published version live. |

**Covered so far (172 tests, 100% coverage):** TC-002 (gate), TC-004–008, TC-012–014,
TC-020–025, TC-027, TC-034 (cutoff), TC-037, TC-039 at the **unit** layer;
TC-001/002/003/005/007/012/037 at the **pipeline integration** layer; TC-001/002/027
(rate limit → 429), TC-029 (soft-fail → 503), leads TC-018/020/021/023/025,
**TC-032/033** (dashboard), and **TC-030/031/040** (edit hidden → Publish goes live +
timestamp → only published state served) at the **HTTP/service integration** layer;
**adapter contract tests** for the vLLM LLM, embeddings, pgvector retriever, Postgres
lead repo, question log, dead-end cluster repo, content repo, and chunk writer
(`httpx.MockTransport` + a fake SQL executor); and a **production-wiring** test that
drives the whole real-adapter path (learning loop + content publish) with only the DB
connection and HTTP endpoints mocked. An **opt-in real-Postgres roundtrip** runs when
`TEST_DATABASE_URL` is set (skipped otherwise).

Also covered: **session memory + follow-up rewrite** (TC-015/016/017), **true token
streaming** + in-band soft-fail, the **lead-delivery outbox** (TC-018/026, retry/never-
lost), the **interval scheduler** + worker loop, and their integration into `/chat`
and `/leads`.

The **embeddable widget** (`widget/`) adds **41 Vitest + jsdom tests** and the **admin
web UI** (`admin/`) adds **47** (both 100% covered): SSE parsing, client-side lead
validation, API clients (soft-fail / error paths), and the rendered UIs (ARIA/keyboard,
streaming, lead capture, dashboard, content publish).

The widget also has a **Playwright + axe E2E** suite (`widget/e2e/`) that passes **5/5
in real Chromium** — embed/open (TC-035), responsive (AC-10.2), a streamed answer
(TC-001), accessibility with no serious/critical axe violations (TC-036), and soft-fail
to static contact (TC-029/AC-10.3). It earned its keep immediately: it caught a
browser-only bug (calling the global `fetch` with `this === ChatClient` → "Illegal
invocation") that jsdom's `this`-agnostic fake fetch could never surface — fixed by
binding to `globalThis`, with a jsdom regression test. A **k6 load** script (`load/`)
exercises the rate-limit/latency path (run where the k6 binary exists).

Totals: **223 backend + 88 frontend unit + 5 E2E = 316 tests.** This is exactly why
the strategy keeps a real-browser layer above the deterministic fakes.

---

## 5. Modules built so far (test-first)

**Deterministic domain core** (`domain/`, pure, unit-tested):

| Module | Responsibility | Primary TCs / ACs |
|--------|----------------|-------------------|
| `clock.py` | `Clock` protocol, `SystemClock` (Asia/Kolkata), `FixedClock` | enabler for all date/time tests |
| `admissions.py` | `admission_status` UPCOMING/OPEN/CLOSED, inclusive close | TC-004/005/006, AC-2.1–2.3, EC-3/4 |
| `fees.py` | `fee_status` UPCOMING/DUE_TODAY/OVERDUE | TC-007/008, AC-2.4, EC-5 |
| `leads.py` | `validate_lead` — name, ≥1 valid channel, message cap, consent | TC-020–025, EC-12–17, FR-11/12 |
| `rate_limit.py` | sliding-window `RateLimiter` (15/min, 100/hr), injected clock | TC-027, EC-19, FR-14 |
| `input_guards.py` | empty/whitespace reject, length cap | TC-037/039, EC-25/26 |
| `boundary.py` | rule pre-filter: injection, profanity (idempotent), competitor | TC-012/013/014, AC-5.2–5.4 |
| `language.py` | `detect_language` — Tamil/Latin/mixed by script | FR-7 |
| `retrieval.py` | grounding gate — `is_grounded` / `select_grounded` | TC-002, AC-1.2, NFR-5 |
| `enrichment.py` | `compute_facts` — date status as injected ground truth | FR-4/5, EC-3–5 |

**Answer pipeline** (`application/`, orchestration tested with fakes):

| Module | Responsibility | Primary TCs / ACs |
|--------|----------------|-------------------|
| `ports.py` | `Retriever` / `LanguageModel` / `OutcomeSink` boundaries | enabler for fakes |
| `prompt.py` | `render_prompt` — grounding + partial-answer policy | TC-003, EC-2, FR-1 |
| `answer_service.py` | `AnswerService.answer` — full pipeline + outcome logging | TC-001/002/003/005/007 |
| `lead_service.py` | `LeadService.submit` — validate + persist + stamp | TC-018, FR-11/12/13 |

**HTTP transport** (`api/`, FastAPI TestClient integration):

| Module | Responsibility | Primary TCs / ACs |
|--------|----------------|-------------------|
| `app.py` | `/chat` (SSE), `/leads`, `/health`; authed `/admin/*` | TC-001/002/027/029, leads, TC-032/033 |
| `main.py` | dev/demo wiring (smoke-tested end-to-end through the loop) | — |

**Edge adapters** (`adapters/`, contract-tested — no real server/DB needed):

| Module | Responsibility | How tested |
|--------|----------------|-----------|
| `vllm_llm.py` | OpenAI-compatible chat (`generate` + `stream_tokens`) | `httpx.MockTransport` — request shape + response/SSE parsing |
| `embeddings.py` | OpenAI-compatible `/v1/embeddings` | `httpx.MockTransport` |
| `pgvector_retriever.py` | embed + cosine search; pure SQL/row mapping | recording `Executor` + `FakeEmbedder` |
| `pg_lead_repository.py` | `INSERT…RETURNING` + row mapping + purge | recording `Executor` |
| `pg_question_log.py` | record / dead-ends / volume stats / purge | recording `Executor` |
| `pg_dead_end_cluster_repository.py` | replace-all + frequency-ranked read | recording `Executor` |
| `pg_content_repository.py` | documents upsert + published-version snapshot | recording `Executor` |
| `pg_chunk_writer.py` | re-index published chunks (delete + insert) | recording `Executor` |
| `pg_outbox.py` | durable lead-email outbox (retry-eligible) | recording `Executor` |
| `redis_session.py` | durable session memory (JSON + sliding TTL) | fake Redis client |

**Production wiring & schema**:

| Module | Responsibility | How tested |
|--------|----------------|-----------|
| `config.py` | `Settings.from_env` | unit — defaults, overrides, missing-required |
| `adapters/connection_executor.py` | DB-API 2.0 → `Executor` | fake connection (result-set vs none) |
| `wiring.py` | `build_app` composes real adapters | end-to-end via TestClient, edges mocked |
| `db/schema.sql` | tables + pgvector index | applied to a live Postgres; opt-in roundtrip |

**Learning loop** (US-9, FR-17/18 — `domain/` + `application/`):

| Module | Responsibility | Primary TCs / ACs |
|--------|----------------|-------------------|
| `domain/clustering.py` | `cluster_questions` — group by similarity, rank by frequency | AC-9.1 |
| `domain/retention.py` | `purge_cutoff` — 12-month boundary | TC-034, FR-18 |
| `dead_end_clustering.py` | batch worker: embed dead-ends → cluster → persist | AC-9.1 |
| `dashboard.py` | ranked dead-ends + volume stats + leads | TC-032/033, AC-9.2 |
| `retention.py` | purge logs + leads past the cutoff | TC-034 |

**Content publishing** (US-8 — `domain/content.py` + `application/content_service.py`):

| Module | Responsibility | Primary TCs / ACs |
|--------|----------------|-------------------|
| `content.py` | `chunk_text` — body → retrieval chunks | US-8 |
| `content_service.py` | `save_draft` (staged) + `publish` (chunk → embed → re-index) | TC-030/031/040, AC-8.x |

**Session, streaming, delivery & worker** (`application/` + `worker.py`):

| Module | Responsibility | Primary TCs / ACs |
|--------|----------------|-------------------|
| `session.py` | ephemeral store (TTL) + bare-follow-up query rewrite | TC-015/016/017, FR-9 |
| `answer_stream.py` | `AnswerStreamService.stream` — token-by-token events | AC-1.3 |
| `lead_delivery.py` | `LeadDeliveryService` — outbox enqueue + retry delivery | FR-13, EC-18, TC-026 |
| `scheduler.py` + `worker.py` | interval scheduler + worker loop (clustering, retention) | US-9, FR-18 |
| `api/app.py` (integration) | `/chat` streaming + session; `/leads` outbox enqueue | TC-015, AC-1.3, EC-18 |

Deterministic fakes ship in `testing/fakes.py` (`FakeRetriever`, `FakeLanguageModel`,
`FakeEmbedder`, `RecordingExecutor`, `RecordingOutcomeSink`, `FakeConnection`), reused
across suites. `build_app_from_env` (the psycopg/`httpx.Client` glue) and the real
Postgres roundtrip are the only parts that need live infra — the latter is an opt-in
test gated on `TEST_DATABASE_URL`.

---

## 6. Running the tests

```bash
make install                      # venv + editable install
make test                         # all tests (unit + integration)
make test-unit                    # just the deterministic core
make cov                          # coverage (term-missing)
```

Unit tests have **no external dependencies** — they run anywhere, in milliseconds,
and gate every commit. Integration tests spin an ephemeral Postgres; eval/E2E/load
run in dedicated CI stages.
