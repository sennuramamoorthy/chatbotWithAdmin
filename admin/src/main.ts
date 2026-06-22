// Thin entry for the admin UI. Reads the API base URL from the mounting script tag's
// data-base-url attribute (falling back to the current origin) and mounts AdminApp
// into <body>. Bundled to dist/admin.js. Excluded from coverage like the widget's
// embed.ts — it is exercised manually via index.html.

import { AdminApp } from "./app";

const script = document.currentScript as HTMLScriptElement | null;
const baseUrl = script?.dataset.baseUrl ?? window.location.origin;

new AdminApp({ container: document.body, baseUrl });
