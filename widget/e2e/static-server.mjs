// Minimal static file server for the Playwright E2E suite.
//
// Serves the built widget demo (widget/index.html + dist/widget.js) over HTTP so
// the specs exercise the *real* embed snippet in a browser — no extra npm deps.
// Playwright's `webServer` boots this; it is NOT part of the shipped widget.
//
//   PORT=4321 ROOT=/abs/path/to/widget node e2e/static-server.mjs
//
// It also synthesizes a couple of fixture pages used by the specs without adding
// files to the repo:
//   /dead-backend.html  — embeds the widget pointed at an unused port (TC-029)

import http from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";

const ROOT = resolve(process.env.ROOT ?? process.cwd());
const PORT = Number(process.env.PORT ?? 4321);
// A port nothing is listening on, so the widget's fetch fails fast → soft-fail.
const DEAD_PORT = Number(process.env.DEAD_PORT ?? 59999);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
};

// Host page whose widget talks to a dead backend (TC-029 / AC-10.3 soft-fail).
const DEAD_BACKEND_PAGE = `<!doctype html>
<html lang="en">
  <head><meta charset="utf-8" /><title>dead-backend fixture</title></head>
  <body>
    <h1>Host page (dead backend)</h1>
    <script
      src="/dist/widget.js"
      data-base-url="http://127.0.0.1:${DEAD_PORT}"
      data-contact-email="admissions@takshashila.example"
      data-contact-phone="+91-99999-00000"
      data-contact-page="https://takshashila.example/admissions"
    ></script>
  </body>
</html>
`;

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
    let pathname = decodeURIComponent(url.pathname);

    if (pathname === "/dead-backend.html") {
      res.writeHead(200, { "content-type": MIME[".html"] });
      res.end(DEAD_BACKEND_PAGE);
      return;
    }

    if (pathname === "/" || pathname === "") pathname = "/index.html";

    // Resolve safely under ROOT (no path traversal out of the served dir).
    const filePath = normalize(join(ROOT, pathname));
    if (!filePath.startsWith(ROOT)) {
      res.writeHead(403);
      res.end("Forbidden");
      return;
    }

    const body = await readFile(filePath);
    res.writeHead(200, { "content-type": MIME[extname(filePath)] ?? "application/octet-stream" });
    res.end(body);
  } catch {
    res.writeHead(404, { "content-type": "text/plain" });
    res.end("Not found");
  }
});

server.listen(PORT, "127.0.0.1", () => {
  // Playwright waits on this URL; the log line aids local debugging.
  console.log(`[e2e static] serving ${ROOT} at http://127.0.0.1:${PORT}`);
});
