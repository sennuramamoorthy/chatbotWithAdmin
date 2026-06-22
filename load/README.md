# Load tests (k6)

[`chat_load.js`](./chat_load.js) is a [k6](https://k6.io/) load test for the
chatbot's `POST /api/v1/chat` (SSE) endpoint. It backs two requirements:

- **NFR-1 — latency under load.** 95% of full SSE answers complete within the
  6 s budget. ("First token < 2 s" is asserted in the browser E2E, not here —
  k6's default HTTP client buffers the whole streamed body.)
- **TC-027 — per-visitor rate limit.** A burst on a single `session_id` must
  trip the friendly slow-down (HTTP 429), not get unlimited service.

## Why two scenarios

Rate limiting is keyed by `session_id` (demo defaults: 15 req/min, 100 req/hour).
The script runs two scenarios so each measures the right thing:

| Scenario           | Models                              | Asserts                              |
| ------------------ | ----------------------------------- | ------------------------------------ |
| `visitors`         | Many distinct visitors (fresh UUID per iteration) | Real answer latency under ramping load |
| `rate_limit_probe` | One visitor hammering a fixed session | The limiter engages (429s appear)    |

`429` responses are **expected and acceptable** — they are the limiter doing its
job. The `real_errors` threshold therefore counts only non-429 failures (5xx,
timeouts, malformed streams) against the < 1% error budget; the 429 rate is
tracked separately (`rate_limited_429`) for visibility.

## Install k6

k6 is a standalone Go binary — it is **not** an npm package and is **not**
installed in this repo. Install it once:

```bash
brew install k6                 # macOS
# or: https://grafana.com/docs/k6/latest/set-up/install-k6/  (Linux / Windows / Docker)
docker run --rm -i grafana/k6 run - <load/chat_load.js   # no local install
```

## Run

Start the demo backend first (in the repo root), then point k6 at it:

```bash
make run                        # demo API on http://127.0.0.1:8000 (separate terminal)
k6 run load/chat_load.js        # uses BASE_URL default http://127.0.0.1:8000
```

Against another deployment, override the base URL:

```bash
BASE_URL=https://chat.example k6 run load/chat_load.js
```

The run exits non-zero if any [threshold](https://grafana.com/docs/k6/latest/using-k6/thresholds/)
fails (e.g. `answer_latency_ms p(95) >= 6000`, or `real_errors >= 1%`), so it is
CI-gateable. Tune the ramp in `options.scenarios` for your target concurrency.

> Note: the demo wiring uses an echo responder over an in-memory KB, so absolute
> latencies reflect transport + framing, not real model inference. Run against a
> `make run-prod` deployment (real vLLM + pgvector adapters) for representative
> NFR-1 numbers.
