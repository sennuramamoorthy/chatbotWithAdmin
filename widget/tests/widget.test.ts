import { beforeEach, describe, expect, it } from "vitest";

import type { ChatCallbacks, LeadResult } from "../src/api";
import { Widget } from "../src/widget";

const CONTACT = { email: "adm@takshashila.edu", phone: "+91-99999-00000", page: "https://x.edu" };

class FakeClient {
  sent: string[] = [];
  leads: unknown[] = [];
  streamImpl: (cb: ChatCallbacks) => void = (cb) => {
    cb.onToken("Hi");
    cb.onDone({ outcome: "answered", offer_lead: false });
  };
  submitImpl: () => Promise<LeadResult> = async () => ({ ok: true, lead_id: "lead-1" });

  async streamChat(message: string, _sid: string, cb: ChatCallbacks): Promise<void> {
    this.sent.push(message);
    this.streamImpl(cb);
  }
  async submitLead(payload: unknown): Promise<LeadResult> {
    this.leads.push(payload);
    return this.submitImpl();
  }
  async health(): Promise<boolean> {
    return true;
  }
}

const mount = (client: FakeClient): Widget =>
  new Widget({ client: client as never, contact: CONTACT, sessionId: "s1" });

const q = (w: Widget, sel: string) => w.root.querySelector(sel) as HTMLElement;
const input = (w: Widget, name: string) => w.root.querySelector(`[name=${name}]`) as HTMLInputElement;

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("Widget rendering & accessibility", () => {
  it("renders a collapsed, labelled bubble inside a shadow root", () => {
    const w = mount(new FakeClient());
    expect(w.host.shadowRoot).toBe(w.root); // isolated from the page
    const bubble = q(w, ".tk-bubble");
    expect(bubble.getAttribute("aria-label")).toBeTruthy();
    expect(w.isOpen).toBe(false);
  });

  it("exposes the panel as a dialog with a live message log", () => {
    const w = mount(new FakeClient());
    expect(q(w, ".tk-panel").getAttribute("role")).toBe("dialog");
    expect(q(w, ".tk-messages").getAttribute("aria-live")).toBe("polite");
  });

  it("toggles open/closed on bubble click and reflects aria-expanded", () => {
    const w = mount(new FakeClient());
    q(w, ".tk-bubble").click();
    expect(w.isOpen).toBe(true);
    expect(q(w, ".tk-bubble").getAttribute("aria-expanded")).toBe("true");
    q(w, ".tk-bubble").click();
    expect(w.isOpen).toBe(false);
  });

  it("closes on Escape", () => {
    const w = mount(new FakeClient());
    w.open();
    q(w, ".tk-panel").dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(w.isOpen).toBe(false);
  });

  it("closes via the close button", () => {
    const w = mount(new FakeClient());
    w.open();
    q(w, ".tk-close").click();
    expect(w.isOpen).toBe(false);
  });

  it("ignores other keys", () => {
    const w = mount(new FakeClient());
    w.open();
    q(w, ".tk-panel").dispatchEvent(new KeyboardEvent("keydown", { key: "a", bubbles: true }));
    expect(w.isOpen).toBe(true);
  });
});

describe("Widget chat", () => {
  it("streams an answer into the message log", async () => {
    const client = new FakeClient();
    client.streamImpl = (cb) => {
      cb.onToken("Hello ");
      cb.onToken("world");
      cb.onDone({ outcome: "answered", offer_lead: false });
    };
    const w = mount(client);
    w.open();
    await w.send("hi");
    const log = q(w, ".tk-messages").textContent ?? "";
    expect(log).toContain("hi"); // the visitor's message
    expect(log).toContain("Hello world"); // the streamed answer
    expect(client.sent).toEqual(["hi"]);
  });

  it("ignores empty input (no request)", async () => {
    const client = new FakeClient();
    const w = mount(client);
    w.open();
    await w.send("   ");
    expect(client.sent).toEqual([]);
  });

  it("sends via the composer form submit", async () => {
    const client = new FakeClient();
    const w = mount(client);
    w.open();
    (q(w, ".tk-input") as HTMLInputElement).value = "hello";
    q(w, ".tk-composer").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(client.sent).toEqual(["hello"]);
  });

  it("offers lead capture on a dead-end", async () => {
    const client = new FakeClient();
    client.streamImpl = (cb) => cb.onDone({ outcome: "dead_end", offer_lead: true });
    const w = mount(client);
    w.open();
    await w.send("hostel fee?");
    expect(w.root.querySelector(".tk-lead-offer")).toBeTruthy();
  });

  it("soft-fails to static Admissions contact when the backend errors", async () => {
    const client = new FakeClient();
    client.streamImpl = (cb) => cb.onError();
    const w = mount(client);
    w.open();
    await w.send("hi");
    expect((q(w, ".tk-messages").textContent ?? "")).toContain(CONTACT.email);
  });
});

describe("Widget lead capture", () => {
  it("blocks submit until consent is ticked (not pre-checked)", async () => {
    const client = new FakeClient();
    const w = mount(client);
    w.open();
    w.openLeadForm();
    expect(input(w, "consent").checked).toBe(false); // AC-7.3
    input(w, "name").value = "Asha";
    input(w, "email").value = "a@b.co";
    await w.submitLead();
    expect(client.leads.length).toBe(0);
    expect((w.root.querySelector(".tk-error")?.textContent ?? "")).toMatch(/consent/i);
  });

  it("submits a valid consented lead and shows a confirmation", async () => {
    const client = new FakeClient();
    const w = mount(client);
    w.open();
    w.openLeadForm();
    input(w, "name").value = "Asha";
    input(w, "email").value = "a@b.co";
    input(w, "consent").checked = true;
    await w.submitLead();
    expect(client.leads).toHaveLength(1);
    expect(client.leads[0]).toMatchObject({ name: "Asha", email: "a@b.co", consent: true });
    expect(w.root.querySelector(".tk-confirm")).toBeTruthy();
  });

  it("surfaces server-side field errors", async () => {
    const client = new FakeClient();
    client.submitImpl = async () => ({
      ok: false,
      errors: [{ field: "email", code: "invalid", message: "Bad email" }],
    });
    const w = mount(client);
    w.open();
    w.openLeadForm();
    input(w, "name").value = "Asha";
    input(w, "email").value = "a@b.co";
    input(w, "consent").checked = true;
    await w.submitLead();
    expect((w.root.querySelector(".tk-error")?.textContent ?? "")).toMatch(/Bad email/);
  });

  it("shows a generic error when submission fails without field errors", async () => {
    const client = new FakeClient();
    client.submitImpl = async () => ({ ok: false });
    const w = mount(client);
    w.open();
    w.openLeadForm();
    input(w, "name").value = "Asha";
    input(w, "email").value = "a@b.co";
    input(w, "consent").checked = true;
    await w.submitLead();
    expect((w.root.querySelector(".tk-error")?.textContent ?? "")).toMatch(/try again/i);
  });

  it("opens the lead form from the always-available header button", () => {
    const w = mount(new FakeClient());
    w.open();
    q(w, ".tk-lead-btn").click();
    expect(input(w, "name")).toBeTruthy();
  });

  it("submits the lead form via its submit event", async () => {
    const client = new FakeClient();
    const w = mount(client);
    w.open();
    w.openLeadForm();
    input(w, "name").value = "Asha";
    input(w, "email").value = "a@b.co";
    input(w, "consent").checked = true;
    q(w, ".tk-lead-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(client.leads).toHaveLength(1);
  });

  it("carries the dead-end question into the lead payload", async () => {
    const client = new FakeClient();
    client.streamImpl = (cb) => cb.onDone({ outcome: "dead_end", offer_lead: true });
    const w = mount(client);
    w.open();
    await w.send("hostel fee?");
    (w.root.querySelector(".tk-lead-offer") as HTMLElement).click(); // open from the offer
    input(w, "name").value = "Asha";
    input(w, "phone").value = "9876543210";
    input(w, "consent").checked = true;
    await w.submitLead();
    expect(client.leads[0]).toMatchObject({ dead_end_question: "hostel fee?" });
  });
});
