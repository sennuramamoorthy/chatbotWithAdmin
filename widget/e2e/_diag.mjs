// One-off diagnostic (not a spec). Drives the same Chromium against the already
// running static server (:4321) + backend (:8000) and logs the browser-side
// outcome of the widget's /chat fetch. Delete after debugging.
import { chromium } from "@playwright/test";

const base = "http://127.0.0.1:4321";
const browser = await chromium.launch();
const page = await browser.newPage();

page.on("console", (m) => console.log("[console]", m.type(), m.text()));
page.on("pageerror", (e) => console.log("[pageerror]", e.message));
page.on("requestfailed", (r) =>
  console.log("[requestfailed]", r.url(), r.failure()?.errorText),
);
page.on("request", (r) => {
  if (r.url().includes("/chat")) console.log("[widget request]", r.method(), r.url());
});
page.on("response", async (r) => {
  if (r.url().includes("/api/v1/chat")) {
    console.log("[response]", r.status(), r.url(), "ct=", r.headers()["content-type"]);
  }
});

await page.goto(base + "/");
// What baseUrl did the embed resolve? Read the script tag the way embed.ts does.
const scriptBase = await page.evaluate(() => {
  const s = document.querySelector('script[src*="widget.js"]');
  return s ? s.getAttribute("data-base-url") : "(no script tag found)";
});
console.log("[script data-base-url]", scriptBase);

await page.locator(".tk-bubble").click();
await page.locator(".tk-input").fill("What is the B.Tech CSE fee?");

// Capture the FULL raw stream the browser receives, end to end.
const probe = await page.evaluate(async () => {
  try {
    const res = await fetch("http://127.0.0.1:8000/api/v1/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message: "What is the B.Tech CSE fee?", session_id: "diag" }),
    });
    let full = "";
    if (res.body) {
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        full += dec.decode(value, { stream: true });
      }
    }
    return { ok: res.ok, status: res.status, fullLen: full.length, tail: full.slice(-300) };
  } catch (e) {
    return { threw: String(e) };
  }
});
console.log("[full stream tail]", JSON.stringify(probe));

await page.locator(".tk-send").click();
await page.waitForTimeout(3000);
const botText = await page.locator(".tk-messages .tk-msg-bot").innerText().catch(() => "(none)");
console.log("[bot text]", botText);

await browser.close();
