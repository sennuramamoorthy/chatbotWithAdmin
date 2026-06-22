// Single-snippet entry (AC-10.1). Reads config from the <script> tag's data
// attributes and auto-mounts the widget. Bundled to dist/widget.js for the CDN.
//
//   <script src="https://cdn.example/widget.js"
//           data-base-url="https://chat.takshashila.edu"
//           data-contact-email="admissions@takshashila.edu"
//           data-contact-phone="+91-..." data-contact-page="https://.../admissions"></script>

import { ChatClient } from "./api";
import { Widget } from "./widget";

const script = document.currentScript as HTMLScriptElement | null;
const data = script?.dataset ?? {};

const baseUrl = data.baseUrl ?? window.location.origin;
const sessionId =
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `s-${Math.floor(performance.now())}`;

new Widget({
  client: new ChatClient(baseUrl),
  contact: {
    email: data.contactEmail ?? "admissions@takshashila.example",
    phone: data.contactPhone ?? "",
    page: data.contactPage ?? "",
  },
  sessionId,
});
