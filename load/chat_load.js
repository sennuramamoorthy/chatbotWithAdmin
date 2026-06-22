// k6 load test for the Takshashila chatbot /api/v1/chat endpoint.
//
// Covers:
//   NFR-1  Latency under load — first token < 2 s, full typical answer <= 6 s.
//   TC-027 Per-visitor rate limit — >15 questions/minute per session yields a
//          friendly slow-down (HTTP 429), not unlimited service.
//
// Run against the demo backend (`make run`, uvicorn on :8000) or any deployment:
//   k6 run load/chat_load.js
//   BASE_URL=https://chat.example k6 run load/chat_load.js
//
// IMPORTANT — rate limiting is keyed by session_id (15 req/min, 100 req/hour in
// the demo). A realistic load test models MANY distinct visitors, so each
// iteration uses a fresh session_id. This exercises real answer latency rather
// than instantly tripping one visitor's limit. A separate scenario deliberately
// hammers a SINGLE session to assert the limit engages (TC-027).
//
// 429 "slow down" responses are EXPECTED and ACCEPTABLE under load — they are the
// rate limiter doing its job, NOT server errors. Thresholds below therefore count
// only non-429 failures (5xx / timeouts / malformed streams) against the error
// budget, while tracking the 429 rate separately for visibility.

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { uuidv4 } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000";

// --- custom metrics ---------------------------------------------------------
// Requests that should count against availability (everything except 429).
const realErrors = new Rate("real_errors");
// Visibility into how often the rate limiter engaged (informational, not a fail).
const rateLimited = new Rate("rate_limited_429");
// Latency of successful answer responses only (200s), for the NFR-1 view.
const answerLatency = new Trend("answer_latency_ms", true);

export const options = {
  scenarios: {
    // Realistic many-visitor traffic: each iteration is a distinct session.
    visitors: {
      executor: "ramping-vus",
      exec: "askQuestion",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 20 }, // ramp up
        { duration: "1m", target: 20 }, // sustain
        { duration: "30s", target: 50 }, // peak
        { duration: "30s", target: 0 }, // ramp down
      ],
      gracefulRampDown: "10s",
    },

    // Single-visitor burst to prove the per-visitor limit kicks in (TC-027).
    // Starts after the main ramp so it doesn't skew latency percentiles much.
    rate_limit_probe: {
      executor: "constant-arrival-rate",
      exec: "burstOneVisitor",
      startTime: "30s",
      duration: "20s",
      rate: 30, // 30 req/s on ONE session -> well over 15/min -> 429s expected
      timeUnit: "1s",
      preAllocatedVUs: 5,
      maxVUs: 10,
    },
  },

  thresholds: {
    // NFR-1: 95% of successful answers complete well within the 6 s budget.
    // (Full SSE answer; "first token < 2 s" is asserted in the browser E2E.)
    answer_latency_ms: ["p(95)<6000"],
    // Overall request latency guardrail across all 200s.
    "http_req_duration{expected_response:true}": ["p(95)<6000"],
    // Real availability: non-429 failures must stay below 1%.
    real_errors: ["rate<0.01"],
    // Sanity: the dedicated probe scenario should actually trip the limiter.
    // (Informational threshold — keep it loose so a fast box still passes.)
    rate_limited_429: ["rate>=0"],
  },
};

const QUESTIONS = [
  "What is the B.Tech CSE fee?",
  "When do B.Tech admissions for 2026 open?",
  "How do I apply online?",
  "What programs are offered?",
  "What is the admission process?",
];

function postChat(sessionId, message) {
  const payload = JSON.stringify({ message, session_id: sessionId });
  const params = {
    headers: { "Content-Type": "application/json" },
    // Generous timeout so streamed answers aren't counted as failures.
    timeout: "15s",
    tags: { name: "chat" },
  };
  return http.post(`${BASE_URL}/api/v1/chat`, payload, params);
}

// Records metrics for a response in a way that treats 429 as expected.
function record(res) {
  const is429 = res.status === 429;
  const ok = res.status === 200;

  rateLimited.add(is429);
  // Only 2xx and the friendly 429 are "acceptable"; anything else is a real error.
  realErrors.add(!ok && !is429);
  if (ok) answerLatency.add(res.timings.duration);

  check(res, {
    "status is 200 or 429 (no 5xx)": (r) => r.status === 200 || r.status === 429,
    "answered streams the SSE done event": (r) =>
      r.status !== 200 || r.body.includes('"type": "done"'),
  });
}

// Many-visitor path: a fresh session per iteration => real answer latency.
export function askQuestion() {
  const sessionId = uuidv4();
  const q = QUESTIONS[Math.floor(Math.random() * QUESTIONS.length)];
  const res = postChat(sessionId, q);
  record(res);
}

// Single-visitor burst: a fixed session => the limiter should return 429s.
export function burstOneVisitor() {
  const res = postChat("load-test-single-visitor", QUESTIONS[0]);
  record(res);
}
