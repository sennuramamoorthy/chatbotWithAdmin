import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

// E2E config for the embeddable widget (US-10). Covers TC-035 (embed/responsive),
// TC-036 (accessibility), TC-001 (streaming answer) and TC-029 (soft-fail).
//
// Two background servers are started by Playwright itself:
//   1. a static file server for this `widget/` dir (serves the real embed bundle)
//   2. the demo backend (uvicorn, in-memory adapters, CORS open) on :8000
//
// The demo backend is the same one `make run` starts. We launch it via the repo
// `.venv` so the in-memory sample KB ("B.Tech CSE fee is INR 1,50,000") is live.

const widgetDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(widgetDir, "..");

const STATIC_PORT = Number(process.env.E2E_STATIC_PORT ?? 4321);
const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8000);
// Port nothing listens on — the soft-fail spec points a widget here.
const DEAD_PORT = Number(process.env.E2E_DEAD_PORT ?? 59999);

const baseURL = `http://127.0.0.1:${STATIC_PORT}`;
const backendURL = `http://127.0.0.1:${BACKEND_PORT}`;

// Resolve the venv's uvicorn (cross-platform: POSIX `bin`, Windows `Scripts`).
const venvUvicorn =
  process.platform === "win32"
    ? resolve(repoRoot, ".venv", "Scripts", "uvicorn.exe")
    : resolve(repoRoot, ".venv", "bin", "uvicorn");

export default defineConfig({
  testDir: "./e2e",
  // Each spec brings its own server expectations; keep them serial-friendly but
  // allow Playwright's default parallelism across files.
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  timeout: 30_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL,
    trace: "on-first-retry",
    // Make the backend URL available to specs (e.g. the soft-fail control case).
    extraHTTPHeaders: {},
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // (a) build + serve the widget statically, (b) start the demo backend.
  webServer: [
    {
      // Build the bundle first, then serve `widget/` over HTTP.
      command: `npm run build && node e2e/static-server.mjs`,
      cwd: widgetDir,
      url: baseURL,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      stdout: "pipe",
      stderr: "pipe",
      env: {
        PORT: String(STATIC_PORT),
        ROOT: widgetDir,
        DEAD_PORT: String(DEAD_PORT),
      },
    },
    {
      // Demo API (same as `make run`); editable-installed package is importable
      // from any cwd, so no PYTHONPATH wrangling is needed.
      command: `${JSON.stringify(venvUvicorn)} takshashila_chatbot.api.main:app --port ${BACKEND_PORT} --log-level warning`,
      cwd: repoRoot,
      url: `${backendURL}/api/v1/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
