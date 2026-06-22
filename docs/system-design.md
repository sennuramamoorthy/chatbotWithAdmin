# System Design — Takshashila University Chatbot Widget (v1)

> Companion to [`takshashila-chatbot-requirement.md`](../takshashila-chatbot-requirement.md).
> This document turns the hardened requirement into an architecture, with explicit
> emphasis on the two asks: (1) a **human-in-the-loop knowledge-learning loop** that
> scales, and (2) a **test-driven** build. The test strategy lives in
> [`test-strategy.md`](./test-strategy.md).

---

## 0. Decisions locked for this design

| Area | Decision | Why |
|------|----------|-----|
| Backend | **Python 3.11+ / FastAPI** (async, SSE streaming) | Richest RAG/embeddings/eval ecosystem; native async for the streaming + fan-out path. |
| Widget | **Vanilla TypeScript**, shadow-DOM isolated, CDN-served | Single `<script>` embed (AC-10.1), no page hijack, framework-agnostic. |
| Admin | **React + TypeScript** SPA | Content editor + dashboard; richer interactions than the widget. |
| LLM | **Self-hosted open-weight instruct model** behind a `LanguageModel` interface | DPDP data-residency: no PII or question text leaves university infra (NFR-6, OQ-2). |
| Embeddings | **Self-hosted multilingual embedding model** (e.g. BGE-M3 / multilingual-e5 class) | Cross-lingual retrieval (Tamil/mixed → English KB) without a translate step (FR-7). |
| Vector store | **pgvector in Postgres** for v1, behind a `VectorStore` interface | KB is *small* (a university's content = low-thousands of chunks). One datastore, transactional with content. Swap to Qdrant when corpus/QPS grows. |
| State / cache / queue | **Redis** (session memory, rate-limit counters, semantic cache, broker) | Ephemeral, shared across stateless API replicas. |
| Workers | **Arq / Celery** task tier | Re-index on publish, dead-end clustering, lead email outbox, retention purge. |

**Architectural spine of the whole system:** *separate the deterministic from the
probabilistic.* Dates, validation, rate limits, retention, and the first-pass
boundary checks are pure logic with a guaranteed-correct answer — they must **never**
be delegated to the LLM. The LLM only **phrases** facts it is handed and **retrieves**
grounded content. This is what lets us promise "zero fabricated answers" (NFR-5) and
"correct on the day you ask" (US-2) while still using a probabilistic model. It is
also why the deterministic core is the first thing we build and the most heavily
unit-tested.

---

## 1. Requirements at a glance

Full detail is in the requirement doc; the load-bearing constraints for architecture:

- **Grounded-only** answers from a curated KB; honest fallback on miss (FR-1, FR-3, NFR-5).
- **Self-computed** date status for fees & admissions (FR-4, FR-5) — correct between admin edits.
- **Multilingual** (EN / Tamil / mixed) from a single English source (FR-7).
- **Boundary policy**: redirect off-topic, ignore injection, decline competitor talk, stay calm under abuse (FR-8).
- **Ephemeral session memory**, ~30 min idle TTL, no identity (FR-9).
- **Consented lead capture** with reliable delivery (email + dashboard, never lose a lead) (FR-10–13).
- **Rate limiting** ~15/min, ~100/hr per source (FR-14); **graceful degradation** + **soft-fail** (FR-15).
- **Admin self-serve** content + explicit **Publish** → re-index ≤ ~2 min (FR-16).
- **Dashboard**: dead-ends grouped & ranked, volume, leads (FR-17) — *this is the learning loop's UI.*
- **Logging + 12-month purge**, no identity (FR-18, NFR-6).
- **Single-snippet embed**, responsive, accessible (FR-19).
- **Scale**: low-hundreds concurrent conversations, degrade not error (NFR-2).

---

## 2. High-level architecture

```
                          ┌──────────────────────────────────────────┐
   University website      │                  CDN                      │
   ┌───────────────┐       │   widget.js (single-snippet embed)        │
   │ <script        │◀──────┤   + baked-in static Admissions contact   │
   │  src=cdn/...>  │       │     (soft-fail payload, AC-10.3)          │
   └──────┬────────┘       └──────────────────────────────────────────┘
          │ HTTPS (SSE stream)
          ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │                      API gateway / load balancer                       │
   │            (TLS, per-source rate-limit pre-check, routing)             │
   └───────┬───────────────────────────────────────────────┬──────────────┘
           │                                                 │
           ▼ (visitor)                                       ▼ (admin, authed)
   ┌────────────────────────────┐                  ┌──────────────────────────┐
   │   Chat API (FastAPI)        │                  │   Admin API (FastAPI)     │
   │  stateless, N replicas      │                  │  content CRUD, publish,   │
   │                             │                  │  dashboard, leads, auth   │
   │  pipeline (see §4.2):       │                  └─────────────┬────────────┘
   │  guards→boundary→ratelimit  │                                │
   │  →session→rewrite→retrieve  │                                │
   │  →date-enrich→generate(stream)                               │
   │  →log outcome               │                                │
   └───┬───────┬─────────┬───────┘                                │
       │       │         │                                        │
       │       │         │                                        │
       ▼       ▼         ▼                                        ▼
  ┌────────┐ ┌──────────────┐  ┌──────────────────────────────────────────┐
  │ Redis  │ │ Inference tier│  │            Postgres (primary + replica)    │
  │ session│ │ (GPU)         │  │  kb_documents / kb_document_versions       │
  │ ratelim│ │ • vLLM (LLM)  │  │  kb_chunks (pgvector)   ◀── VectorStore    │
  │ cache  │ │ • embeddings  │  │  fee_items / admission_windows (structured)│
  │ broker │ │   server      │  │  leads (+ delivery_status outbox)          │
  └────────┘ └──────────────┘  │  question_logs (no identity, 12-mo purge)  │
                               │  dead_end_clusters / dead_end_members      │
                               │  daily_stats (rollups)                     │
                               └──────────────────────────────────────────┘
       ▲
       │ enqueue jobs
  ┌────┴───────────────────────────────────────────────────────────────────┐
  │                         Worker tier (Arq/Celery)                         │
  │  • reindex_on_publish   • cluster_dead_ends (batch)                      │
  │  • deliver_lead_email (outbox + retry)   • purge_expired (retention)     │
  └────────┬──────────────────────────────────────────────────────────────┘
           ▼
      ┌──────────┐
      │  SMTP /   │  Admissions leads inbox (OQ-4)
      │  email    │
      └──────────┘
```

**Why this shape:**
- **Stateless API replicas** + **Redis** for all per-session state → scale the chat tier horizontally; any replica serves any visitor (AC-6.2 context survives page nav because it's in Redis, not memory).
- **Inference tier is a separate, independently-scaled pool.** It is the scarce, expensive resource (GPU). Decoupling it lets us put a queue in front and **degrade gracefully** ("busy, one moment", FR-15) instead of hard-failing when GPUs saturate.
- **Workers** absorb everything that must not block the visitor or must survive failure: email delivery (retry/outbox), re-indexing, clustering, purge.
- **CDN-hosted widget carries its own static fallback**, so even a total backend outage renders Admissions contact info, never a blank/broken box (AC-10.3, NFR-4).

---

## 3. The human-in-the-loop knowledge-learning loop ★

This is the heart of ask #1. "Learning new knowledge" here is **not** model
fine-tuning or auto-ingestion — that would risk fabrication, which the requirement
forbids (NFR-5). Instead the system **discovers what it doesn't know**, **prioritizes
the gaps for a human**, and the human **teaches it by curating grounded content**.
The model never invents facts; a person authorizes every new fact.

```
        ┌──────────────────────────────────────────────────────────────┐
        │                                                                │
        │   (1) VISITOR ASKS  ───────────────────────────────────────┐  │
        │        question                                            │  │
        │           │                                                ▼  │
        │           │                                   ┌──────────────────────┐
        │           │   answered ✓                      │ (2) OUTCOME LOGGED    │
        │           ▼                                   │  answered | dead_end  │
        │   ┌──────────────┐   dead_end (no grounded    │  topic, lang, ts      │
        │   │ RAG pipeline │──────── answer found) ─────▶│  (NO identity)        │
        │   └──────────────┘                            └───────────┬──────────┘
        │                                                           │ async
        │                                                           ▼
        │                                          ┌───────────────────────────────┐
        │                                          │ (3) CLUSTER & RANK (batch job) │
        │                                          │  embed dead-ends → group by    │
        │                                          │  similarity → count frequency  │
        │                                          │  → "knowledge-gap backlog"     │
        │                                          └───────────────┬───────────────┘
        │                                                          ▼
        │                                          ┌───────────────────────────────┐
        │                                          │ (4) ADMIN DASHBOARD            │
        │                                          │  gaps ranked by frequency      │
        │   ┌───────────────────────────┐         │  (FR-17 / AC-9.1) — the human  │
        │   │ (6) RE-INDEX (≤ ~2 min)    │         │  sees exactly what to teach    │
        │   │  embed changed chunks →    │         └───────────────┬───────────────┘
        │   │  upsert vector store →     │                         ▼
        │   │  flip published version    │         ┌───────────────────────────────┐
        │   │  set "last updated"        │◀────────┤ (5) ADMIN CURATES & PUBLISHES  │
        │   └─────────────┬─────────────┘ Publish  │  authors/edits grounded KB     │
        │                 │                         │  content + dates; clicks       │
        │                 │                         │  Publish (FR-16 / AC-8.x)      │
        │                 ▼                         └───────────────────────────────┘
        │   future asks on that topic now resolve ✓ → cluster shrinks
        │                 │
        └─────────────────┘   loop closes: the gap that was a dead-end is now knowledge
```

### Loop stages in detail

1. **Ask → answer or dead-end.** The RAG pipeline (§4.2) only answers when retrieval
   clears a grounding threshold. Below it → honest fallback (FR-3) **and** the event is
   the raw signal of a knowledge gap.
2. **Log the outcome (async, no identity).** Every turn writes `{question_text,
   outcome, topic, lang, ts}` to `question_logs` — fire-and-forget so it never adds
   latency. No visitor identity is stored (AC-9.3, EC-24).
3. **Cluster & rank (scheduled batch).** A worker periodically embeds new dead-end
   questions and assigns each to a semantic cluster (nearest-centroid against existing
   `dead_end_clusters`; new centroid if nothing is close enough). It updates
   `frequency` and `last_seen_at`. **Batch, not real-time** — this is what makes the
   loop scale: thousands of raw misses collapse into a short, ranked backlog without
   any synchronous cost. (AC-9.1: "grouped by similarity, ranked by frequency.")
4. **Surface to the human.** The dashboard reads the *pre-aggregated* cluster table
   (not raw logs), so it's fast and shows the admin the highest-leverage gaps first:
   "37 people asked about hostel fees this week, and we can't answer."
5. **Human curates & publishes.** The admin authors grounded content (or sets the
   missing fee/admission dates), staged as a draft. Nothing is live until **Publish**
   (AC-8.2). This is the "human in the loop" — a person decides what becomes a fact.
6. **Re-index & close the loop.** Publish enqueues a job that re-embeds only the
   *changed* chunks, upserts them into the vector store, flips the published version
   pointer atomically, and stamps "last updated" (AC-8.3) — live within ~2 min (AC-8.2).
   Future instances of that question now retrieve the new content and get answered, so
   the dead-end cluster stops growing. **Optional measurable feedback:** because we log
   outcomes, the dashboard can show a cluster's answered-rate climbing after a publish —
   visible proof the bot "learned."

### Why this design for the loop

- **Safety:** a human authorizes every new fact → no fabrication path (NFR-5). The bot
  expands its knowledge *only* through curated, published content.
- **Prioritization:** clustering + frequency ranking means finite admin time is spent
  on the gaps that affect the most visitors (AC-9.1).
- **Scalability of the loop itself:** the only synchronous cost is a fire-and-forget
  log write. All learning work (embedding, clustering, ranking, re-indexing) is async/
  batch and reads from aggregates, so it stays cheap as volume grows.
- **Closed measurement:** the same outcome log that detects gaps also proves they
  closed, turning "learning" into something observable instead of assumed.

**Extensions when it grows (out of scope for v1, noted in §8):** explicit answer
feedback (👍/👎) as a second learning signal; admin "draft answer suggested from the
dead-end cluster" to speed curation; online (incremental) clustering if batch lag
becomes material.

---

## 4. Deep dive

### 4.1 Data model (Postgres)

```
kb_documents            kb_document_versions          kb_chunks
─────────────           ────────────────────          ─────────
id (pk)                 id (pk)                        id (pk)
topic  (enum: admissions| document_id (fk)             document_version_id (fk)
  fees|placements|       version_no                    chunk_text   (English source)
  facilities|transport|  body (immutable snapshot)     embedding    vector(1024)  ◀ pgvector index
  courses|faculty)       published_at                  metadata jsonb (topic, anchors)
title                    published_by
status (draft|published) created_at
current_version (fk)
last_updated_at         ── only the row referenced by a document's published version
created_at/updated_at      is ever retrieved → "edit without Publish stays hidden"
                           (EC-22); publishing flips current_version atomically (EC-23/40)

fee_items                       admission_windows
─────────                       ─────────────────
id (pk)                         id (pk)
program                         program / intake_label
amount_inr                      open_date   (date)
due_date  (date)   ◀ structured  close_date  (date)   ◀ structured, NOT prose
currency                        notes
notes                           ── status computed at query time (§4.3); never stored

leads                                  question_logs               (no identity)
─────                                  ─────────────
id (pk)                                id (pk)
name / email / phone / program         question_text
message (<=1000)                       outcome (answered|dead_end)
consent_at  (ts, not null)             topic / detected_lang
dead_end_question (nullable)           created_at   ◀ 12-month purge key
created_at                             ── NO session/visitor identity stored (EC-24)
delivery_status (pending|sent|failed)
delivery_attempts (int)   ◀ outbox/retry (EC-18)
last_delivery_error

dead_end_clusters              dead_end_members           daily_stats
─────────────────              ────────────────           ───────────
id (pk)                        cluster_id (fk)            date (pk part)
centroid_embedding vector      question_log_id (fk)       topic (pk part)
representative_text                                       question_count
frequency (int)   ◀ ranking    ── built by the batch      dead_end_count
last_seen_at         (AC-9.1)     clustering worker        lead_count   ◀ dashboard volume (AC-9.2)
```

Key modeling choices:
- **Versioned content** (`kb_document_versions`) + a `current_version` pointer is what
  makes "only the published state goes live" (EC-22, EC-23, EC-40) atomic and gives
  free rollback. Retrieval *only* sees published versions' chunks.
- **Fees & admissions are structured columns, not prose.** Dates live as `date`
  columns so the deterministic layer can compute status (§4.3). Prose for these topics
  is generated by the LLM *around* the computed status, never as the source of truth.
- **Leads carry a delivery state machine** (`pending→sent|failed` + attempts) — the
  transactional-outbox pattern that guarantees a consented lead is never lost (EC-18).
- **`question_logs` has no identity column at all** — privacy by construction (NFR-6).
- **Aggregates** (`dead_end_clusters`, `daily_stats`) are written by workers so the
  dashboard reads small, pre-computed tables.

### 4.2 RAG / answer pipeline (Chat API)

A question flows through cheap-and-deterministic stages first, expensive-and-
probabilistic stages last — fail fast, spend GPU only when warranted:

```
 1. INPUT GUARD        empty/whitespace → prompt to type (EC-25, no LLM call)
    (deterministic)    over-cap length  → ask to shorten (EC-26)
 2. RATE LIMIT         over 15/min or 100/hr → friendly slow-down (FR-14, no LLM call)
    (deterministic)
 3. BOUNDARY PRE-FILTER injection / profanity / explicit competitor-compare →
    (deterministic)     canned localized redirect (FR-8) — no GPU spent on attacks
 4. SESSION LOAD       fetch last N turns from Redis (FR-9)
 5. LANG DETECT        detect EN | Tamil | mixed (FR-7)
 6. QUERY REWRITE      "and the M.Tech?" + context → standalone query (AC-6.1)
 7. RETRIEVE           embed query (multilingual model) → vector search published
                       chunks → top-k with scores
 8. GROUNDING GATE     best score < threshold OR no chunks → FALLBACK (FR-3),
    (deterministic)     log dead_end; never call the LLM to "guess" (AC-1.2, NFR-5)
 9. DATE ENRICH        if fee/admission topic: compute status deterministically
    (deterministic)     (§4.3) and inject as a hard fact into the prompt context
10. GENERATE (stream)  LLM answers in the visitor's language, grounded ONLY in
                       retrieved chunks + computed status; SSE stream (<2s first
                       token, AC-1.3)
11. LOG OUTCOME        async write {question, outcome, topic, lang} (FR-18)
```

- **Stages 1–3, 8, 9 are deterministic** → unit-tested exhaustively, no LLM flakiness,
  and they shield the GPU from empty/abusive/ungrounded calls (cost control, NFR-9).
- **Partial answers (EC-2):** retrieval can satisfy some sub-questions and not others;
  the prompt instructs the model to answer the grounded part and explicitly flag the
  rest as unavailable + offer handoff — never fill gaps with guesses.
- **Grounding gate is the anti-fabrication keystone.** If nothing retrieves above
  threshold, we *don't* ask the model to try — we fall back. This is enforced in code,
  not by prompt politeness.

### 4.3 Deterministic date layer (the correctness guarantee)

The bot must be right "on the day you ask" even if no admin edited anything (EC-3).
So status is **computed**, never stored or LLM-guessed:

- `admission_status(open_date, close_date, today)` → `UPCOMING | OPEN | CLOSED`
  - `OPEN` iff `open_date <= today <= close_date` (**inclusive** close — AC-2.3/EC-4).
  - `today > close_date` → `CLOSED` (AC-2.2/EC-3); `today < open_date` → `UPCOMING`.
- `fee_status(due_date, today)` → `UPCOMING | DUE_TODAY | OVERDUE` (AC-2.4/EC-5).
- **`today` is computed in `Asia/Kolkata`**, not UTC — "through end of that date" is a
  local-time statement. A `Clock` abstraction yields business-tz `today()`; tests use
  a `FixedClock` so every boundary case is deterministic (no wall-clock flake).

The computed status string is injected into the LLM context ("ADMISSION STATUS:
CLOSED as of 2026-06-15"); the model only phrases it in the visitor's language. The
model is never asked to compare dates.

### 4.4 Multilingual (FR-7)

- **One English KB** (A-2). No parallel Tamil source.
- **Cross-lingual retrieval via a multilingual embedding model:** a Tamil or
  code-switched query ("CSE course la fees evlo?") embeds *near* the English fee chunk,
  so retrieval works **without** a translation hop (simpler, fewer failure points).
- **Reply in the input language:** detected language is passed to generation; the model
  answers in EN / Tamil / the dominant language of mixed input, grounded in the English
  facts (AC-4.3). We assert *properties* (script, key figure present) in tests, not
  exact strings.

### 4.5 Boundary & guardrails (FR-8) — layered

1. **Deterministic pre-filter (built in this session):** high-precision rules catch
   prompt-injection patterns ("ignore previous instructions…"), profanity, and explicit
   competitor-comparison phrasing → return a canned, localized, non-escalating response
   (AC-5.2/5.3/5.4). The abuse response is **idempotent** — identical on repetition, no
   escalation (AC-5.4). Cheap and GPU-free.
2. **System-prompt constraints:** the model is instructed to stay in role, answer only
   in-scope topics, use only retrieved content, and never discuss other institutions —
   the semantic backstop for off-topic redirects (TC-011) the rules can't catch precisely.
3. **Grounding gate (§4.2 stage 8):** the ultimate guardrail — no grounded content, no
   generated answer.

We keep rule-based detection conservative (favor precision) and let the prompt +
grounding handle the fuzzy cases, so we don't wrongly block legitimate questions.

### 4.6 Session memory (FR-9)

- Non-identifying ephemeral `session_id` (cookie/localStorage, A-8) → Redis key
  `session:{id}` holding the last N turns, **TTL ~30 min, sliding** on each turn.
- Stored server-side in Redis (not the widget) so context **survives page navigation**
  across stateless replicas (AC-6.2). Expiry/end discards it (AC-6.3); a follow-up after
  expiry is treated as fresh (EC-11). Never linked to identity.

### 4.7 Lead capture, validation & delivery (FR-10–13)

- **Trigger:** offered on a dead-end **and** always via "Talk to Admissions"; never
  proactively mid-answer (AC-7.1).
- **Validation (deterministic, built this session):** name required; ≥1 valid channel
  (email basic-shape OR Indian mobile — 10 digits, optional +91/0, leading 6–9);
  message ≤1000; explicit consent (not pre-checked). Returns per-field errors
  (EC-12–17). Enforced **server-side** regardless of client.
- **Delivery (transactional outbox):** on submit → validate → **persist lead** (source
  of truth, `delivery_status=pending`) → enqueue email job. The worker delivers with
  retries; on failure the lead stays in the dashboard flagged `failed` for retry. A
  consented lead is **never silently lost** (EC-18). Visitor sees confirmation on the
  DB write, not on email success.

### 4.8 Rate limiting (FR-14)

- **Sliding-window counters in Redis**, keyed by ephemeral source: `(15, 60s)` and
  `(100, 3600s)`. Over limit → friendly slow-down, **no LLM call** (cost protection,
  NFR-9). Logic is deterministic with an injected clock → an in-memory implementation
  is unit-tested and the same interface is backed by Redis in prod.

### 4.9 API contracts (selected)

```
# Visitor (anonymous)
POST /api/v1/chat            {session_id, message, page_url?}
     → 200 text/event-stream: token deltas, then {outcome, detected_lang, offer_lead}
     → 429 {retry_after, message}            # rate limited (friendly)
     → 503 {static_contact}                  # soft-fail when inference down
POST /api/v1/leads           {session_id, name, email?, phone?, program?, message?,
                               consent, dead_end_question?}
     → 201 {lead_id}  | 422 {errors:[{field,code,message}]}
GET  /api/v1/health          → liveness for the widget's soft-fail decision

# Admin (authenticated, single role — A-1)
POST /api/v1/admin/login
GET/POST/PUT /api/v1/admin/content[/{id}]    # draft CRUD, incl. fee/admission dates
POST /api/v1/admin/publish                   # stage → re-index, returns last_updated
GET  /api/v1/admin/dashboard/dead-ends       # clusters ranked by frequency (AC-9.1)
GET  /api/v1/admin/dashboard/stats           # volume basics (AC-9.2)
GET  /api/v1/admin/leads                      # leads list incl. delivery_status
```

Streaming uses **SSE** (one-way token stream, simpler than WebSocket, proxy-friendly).

---

## 5. Scale & reliability

### 5.1 Load envelope (NFR-2)

- Target: low-hundreds concurrent conversations (admission-season peak). Say ~300
  concurrent, a question every ~20–30 s → **~10–15 LLM requests/sec** at peak. Rate
  limit caps any single source at 15/min.
- **Postgres, Redis, the vector search, and the API tier are nowhere near stressed** by
  this — the KB is small and the data is tiny. **The GPU inference tier is the only real
  bottleneck**, so it gets the scaling and degradation attention.
- Validate the envelope against real historical traffic before launch (OQ-5); the
  latency NFR (first token <2s, full ≤6s) must be checked **under representative load**,
  not single-request (per the requirement's coverage note).

### 5.2 Scaling each tier

| Tier | Scaling | Notes |
|------|---------|-------|
| Widget | CDN | Infinite read scale; carries soft-fail payload. |
| Chat/Admin API | Horizontal, stateless | Add replicas behind the LB; all state in Redis/PG. |
| Inference (GPU) | Horizontal pool + **request queue** | vLLM continuous batching; autoscale GPU nodes; **queue + "busy, one moment" when saturated** (FR-15) instead of erroring. |
| Embeddings | Co-located or small CPU/GPU pool | Cheap; cache query embeddings. |
| Vector store | pgvector now → Qdrant later | Small corpus; revisit at scale (§8). |
| Postgres | Primary + read replica | Dashboard/leads reads hit the replica. |
| Redis | Managed/replicated | Session + counters + cache + broker. |
| Workers | Scale by queue depth | Re-index, clustering, email, purge. |

### 5.3 Reliability & failure modes (maps to edge cases)

| Failure | Behavior | Ref |
|---------|----------|-----|
| Inference/backend down | Widget **soft-fails to static Admissions contact** (CDN payload); API returns 503 with contact | AC-10.3, NFR-4, EC-21, TC-029 |
| Peak beyond sizing | Queue + "busy, one moment"; **no hard errors** | NFR-2, EC-20, TC-028 |
| Abuse / scripted flood | Rate limit → slow-down; GPU & cost protected | FR-14, EC-19, TC-027 |
| Lead email fails | Lead persisted + dashboard-visible + retried/flagged | EC-18, TC-026 |
| Admin edits, no Publish | Last published version served | EC-22, TC-030 |
| Logs age out | Scheduled purge of `question_logs` & `leads` >12 mo | FR-18, NFR-6, TC-034 |

### 5.4 Observability

- **Metrics:** first-token & full-answer latency (p50/p95/p99), dead-end rate, fallback
  rate, rate-limit hits, queue depth, GPU utilization, lead delivery success/retry.
- **The dead-end rate is a product KPI**, not just an ops metric — it is the inverse of
  how well the learning loop is keeping up.
- **Alerts:** inference saturation, lead-delivery failure backlog, re-index lag >2 min,
  purge-job failure.

---

## 6. Trade-off analysis

| Decision | Chosen | Alternative | Trade-off |
|----------|--------|-------------|-----------|
| LLM hosting | **Self-hosted open model** | Managed (Claude) API | **+** DPDP data-residency, no per-token vendor cost, no data egress. **−** GPU capex/opex, ops burden, lower out-of-box quality (esp. Tamil), must build eval + guardrails. **Mitigation:** `LanguageModel` interface keeps a managed swap/burst-fallback cheap; invest in a Tamil eval set. |
| "Learning" mechanism | **Human-curated KB loop** | Auto-ingest / fine-tune on Q&A | **+** zero fabrication, every fact authorized, auditable. **−** human in the path → coverage improves only as fast as the admin curates. Acceptable: accuracy >> coverage speed for a university. |
| Date status | **Deterministic compute** | Let the LLM read dates | **+** guaranteed correct, free unit tests. **−** a little more pipeline plumbing. Non-negotiable given US-2/NFR-5. |
| Vector store | **pgvector (v1)** | Qdrant/Weaviate now | **+** one datastore, transactional with content, less ops. **−** fewer ANN features at huge scale — irrelevant for a small KB. Abstracted for later swap. |
| Multilingual retrieval | **Multilingual embeddings** | Translate query→EN, then embed | **+** no translation hop/failure, handles code-switching natively. **−** depends on embedding model's Tamil quality → validate by eval. |
| Streaming | **SSE** | WebSocket | **+** simpler, one-way, proxy/CDN-friendly. **−** no client→server stream (not needed). |
| Lead delivery | **Outbox + async retry** | Synchronous email on submit | **+** never lose a consented lead, fast confirmation. **−** eventual delivery + a worker. Worth it (EC-18). |
| Boundary policy | **Rules + prompt + grounding** | Rules-only / LLM-only | **+** cheap deterministic catch for attacks, semantic backstop for fuzzy cases. **−** two layers to maintain. |

---

## 7. Test-driven approach (summary; full plan in `test-strategy.md`)

- **Test pyramid:** many fast **unit** tests on the deterministic core; **integration**
  tests on API + DB with fakes for LLM/embeddings/vector/email; an **eval/golden-set**
  suite for the probabilistic behavior (grounding, language, refusals) asserting
  *properties* not exact strings; **E2E** (Playwright + axe) for embed, a11y, soft-fail,
  streaming latency; **load** tests for rate-limit/degradation/latency-under-load.
- **Determinism by injection:** a `Clock` is injected everywhere time matters (dates,
  rate limiter, retention) so boundary cases are reproducible. LLM, embeddings, vector
  store, and email are behind interfaces with fakes.
- **This session builds the deterministic core test-first** (red→green→refactor):
  `clock`, `admissions`, `fees`, `leads`, `rate_limit`, `input_guards`, `boundary` —
  the modules that carry the hardest correctness guarantees (US-2, FR-11/12, FR-14) and
  need no LLM. Every targeted TC maps to a test; see the traceability table in
  `test-strategy.md`.

---

## 8. What I'd revisit as it grows

- **Vector store:** pgvector → Qdrant when corpus or QPS outgrows a single Postgres.
- **Managed-LLM fallback:** a burst/quality fallback behind the same interface for
  spikes beyond GPU capacity, if DPDP review permits a residency-compliant region.
- **Second learning signal:** explicit 👍/👎 feedback to complement dead-ends.
- **Curation assist:** auto-draft a candidate answer from a dead-end cluster for the
  admin to verify (keeps the human in the loop, speeds it up).
- **Online clustering:** if batch lag on dead-ends becomes material.
- **Semantic answer cache:** cache frequent grounded answers to cut GPU spend.
- **Multi-tenant:** if the platform serves more than one university.
- **CRM integration** for leads (explicitly out of scope for v1).
```
