import { beforeEach, describe, expect, it } from "vitest";

import {
  type ClusterResponse,
  type ContentDocument,
  type ContentDraft,
  type DeadEndsResponse,
  HttpError,
  type LeadsResponse,
  type LoginResponse,
  type StatsResponse,
} from "../src/api";
import { AdminApp } from "../src/app";

const DOC: ContentDocument = {
  id: "fees-2026",
  topic: "fees",
  title: "Fees 2026",
  draft_body: "Draft body",
  published_body: "Published body",
  published_version: 1,
  last_updated: "2026-06-15",
  metadata: { reviewed: true },
};

/** A fake AdminClient that records calls and lets tests override each response. */
class FakeClient {
  lastToken = "";
  loginCalls: Array<{ username: string; password: string }> = [];
  saved: Array<{ id: string; draft: ContentDraft }> = [];
  published: string[] = [];
  clusterCalls = 0;

  loginImpl: (u: string, p: string) => Promise<LoginResponse> = async (u) => ({
    token: "sess-token",
    username: u,
    expires_in: 3600,
  });
  deadEndsImpl: () => Promise<DeadEndsResponse> = async () => ({
    dead_ends: [{ question: "hostel fee?", frequency: 3 }],
  });
  statsImpl: () => Promise<StatsResponse> = async () => ({
    questions_per_day: { "2026-06-15": 5 },
    busiest_topics: [["fees", 9]],
    lead_count: 2,
    answered_count: 4,
    dead_end_count: 1,
  });
  leadsImpl: () => Promise<LeadsResponse> = async () => ({ leads: [] });
  clusterImpl: () => Promise<ClusterResponse> = async () => ({ clustered: 4 });
  getContentImpl: (id: string) => Promise<ContentDocument> = async (id) => ({ ...DOC, id });
  saveContentImpl: (id: string, draft: ContentDraft) => Promise<ContentDocument> = async (
    id,
    draft,
  ) => ({ ...DOC, id, ...draft, draft_body: draft.body });
  publishContentImpl: (id: string) => Promise<ContentDocument> = async (id) => ({
    ...DOC,
    id,
    published_version: 2,
  });

  login(username: string, password: string): Promise<LoginResponse> {
    this.loginCalls.push({ username, password });
    return this.loginImpl(username, password);
  }
  deadEnds(): Promise<DeadEndsResponse> {
    return this.deadEndsImpl();
  }
  stats(): Promise<StatsResponse> {
    return this.statsImpl();
  }
  leads(): Promise<LeadsResponse> {
    return this.leadsImpl();
  }
  cluster(): Promise<ClusterResponse> {
    this.clusterCalls += 1;
    return this.clusterImpl();
  }
  getContent(id: string): Promise<ContentDocument> {
    return this.getContentImpl(id);
  }
  saveContent(id: string, draft: ContentDraft): Promise<ContentDocument> {
    this.saved.push({ id, draft });
    return this.saveContentImpl(id, draft);
  }
  publishContent(id: string): Promise<ContentDocument> {
    this.published.push(id);
    return this.publishContentImpl(id);
  }
}

let container: HTMLElement;
let client: FakeClient;

function mount(): AdminApp {
  client = new FakeClient();
  return new AdminApp({
    container,
    baseUrl: "http://x",
    clientFactory: (_baseUrl, token) => {
      client.lastToken = token;
      return client as never;
    },
  });
}

const q = (app: AdminApp, sel: string) => app.root.querySelector(sel) as HTMLElement;
const statusText = (app: AdminApp) => q(app, ".adm-status").textContent ?? "";
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

/** Mount and sign in (the happy path most tests start from). */
async function signedIn(): Promise<AdminApp> {
  const app = mount();
  await app.login("admin", "pw");
  return app;
}

beforeEach(() => {
  document.body.innerHTML = "";
  sessionStorage.clear();
  container = document.createElement("div");
  document.body.appendChild(container);
});

describe("AdminApp login screen", () => {
  it("shows a username/password login form when not authenticated", () => {
    const app = mount();
    expect(app.authenticated).toBe(false);
    expect(q(app, ".adm-login-form")).toBeTruthy();
    expect(q(app, ".adm-login-username")).toBeTruthy();
    expect(q(app, ".adm-login-password")).toBeTruthy();
    // The shell (tabs / panel) is NOT rendered before login.
    expect(app.root.querySelector(".adm-panel")).toBeNull();
  });

  it("validates that both fields are filled before calling the API", async () => {
    const app = mount();
    await app.login("", "");
    expect(client.loginCalls).toHaveLength(0);
    expect(statusText(app)).toMatch(/username and password/i);
    expect(q(app, ".adm-status").dataset.kind).toBe("error");
  });

  it("signs in, reveals the shell, loads the dashboard and uses the issued token", async () => {
    const app = mount();
    await app.login("admin", "pw");

    expect(client.loginCalls).toEqual([{ username: "admin", password: "pw" }]);
    expect(app.authenticated).toBe(true);
    expect(q(app, ".adm-user").textContent).toMatch(/signed in as admin/i);
    expect(q(app, ".adm-stats")).toBeTruthy(); // dashboard auto-loaded
    expect(client.lastToken).toBe("sess-token"); // subsequent calls use the session token
    expect(statusText(app)).toMatch(/loaded/i);
  });

  it("signs in via the form submit", async () => {
    const app = mount();
    (q(app, ".adm-login-username") as HTMLInputElement).value = "admin";
    (q(app, ".adm-login-password") as HTMLInputElement).value = "pw";
    q(app, ".adm-login-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await tick();
    expect(client.loginCalls).toHaveLength(1);
    expect(q(app, ".adm-panel")).toBeTruthy();
  });

  it("shows a friendly message on a 401 (bad credentials)", async () => {
    const app = mount();
    client.loginImpl = async () => {
      throw new HttpError(401, "Request ... 401");
    };
    await app.login("admin", "wrong");
    expect(app.authenticated).toBe(false);
    expect(statusText(app)).toMatch(/invalid username or password/i);
    expect(q(app, ".adm-status").dataset.kind).toBe("error");
  });

  it("surfaces a non-401 login failure verbatim", async () => {
    const app = mount();
    client.loginImpl = async () => {
      throw new Error("network down");
    };
    await app.login("admin", "pw");
    expect(statusText(app)).toMatch(/network down/);
  });
});

describe("AdminApp session persistence & logout", () => {
  it("restores the shell from a stored session on construction", () => {
    sessionStorage.setItem("adm.session", JSON.stringify({ token: "saved-tok", username: "ada" }));
    const app = mount();
    expect(app.authenticated).toBe(true);
    expect(q(app, ".adm-user").textContent).toMatch(/ada/);
  });

  it("ignores a corrupt stored session", () => {
    sessionStorage.setItem("adm.session", "not json");
    const app = mount();
    expect(app.authenticated).toBe(false);
    expect(q(app, ".adm-login-form")).toBeTruthy();
  });

  it("ignores a stored session without a token", () => {
    sessionStorage.setItem("adm.session", JSON.stringify({ username: "ada" }));
    const app = mount();
    expect(app.authenticated).toBe(false);
  });

  it("logs out, clears the session and returns to login", async () => {
    const app = await signedIn();
    expect(sessionStorage.getItem("adm.session")).not.toBeNull();
    q(app, ".adm-logout").click();
    expect(app.authenticated).toBe(false);
    expect(q(app, ".adm-login-form")).toBeTruthy();
    expect(sessionStorage.getItem("adm.session")).toBeNull();
  });

  it("does nothing useful if a data call is made while signed out", async () => {
    const app = mount();
    await app.loadDashboard(); // not signed in
    expect(q(app, ".adm-login-form")).toBeTruthy(); // requireClient bounced to login
    await app.runCluster();
    await app.loadContent("fees-2026");
    expect(client.clusterCalls).toBe(0);
    expect(q(app, ".adm-login-form")).toBeTruthy();
  });
});

describe("AdminApp dashboard", () => {
  it("renders dead-ends, stats and leads", async () => {
    const app = await signedIn();
    expect(q(app, ".adm-stats")).toBeTruthy();
    expect(q(app, ".adm-dead-ends")).toBeTruthy();
    expect(q(app, ".adm-leads")).toBeTruthy();
    expect(app.root.textContent).toContain("hostel fee?");
  });

  it("reloads the dashboard via the Load button", async () => {
    const app = await signedIn();
    q(app, ".adm-refresh").click();
    await tick();
    expect(q(app, ".adm-stats")).toBeTruthy();
  });

  it("shows an error message when a dashboard request fails (non-401)", async () => {
    const app = await signedIn();
    client.statsImpl = async () => {
      throw new Error("Request failed with status 500.");
    };
    await app.loadDashboard();
    expect(statusText(app)).toMatch(/status 500/);
    expect(q(app, ".adm-status").dataset.kind).toBe("error");
  });

  it("bounces back to login when a request returns 401 (expired session)", async () => {
    const app = await signedIn();
    client.statsImpl = async () => {
      throw new HttpError(401, "Request ... 401");
    };
    await app.loadDashboard();
    expect(app.authenticated).toBe(false);
    expect(q(app, ".adm-login-form")).toBeTruthy();
    expect(statusText(app)).toMatch(/session expired/i);
  });

  it("clusters then refreshes the dashboard", async () => {
    const app = await signedIn();
    await app.runCluster();
    expect(client.clusterCalls).toBe(1);
    expect(statusText(app)).toMatch(/loaded/i);
  });

  it("clusters via the Cluster button", async () => {
    const app = await signedIn();
    q(app, ".adm-cluster").click();
    await tick();
    expect(client.clusterCalls).toBe(1);
  });

  it("shows an error when clustering fails", async () => {
    const app = await signedIn();
    client.clusterImpl = async () => {
      throw new Error("cluster boom");
    };
    await app.runCluster();
    expect(statusText(app)).toMatch(/cluster boom/);
  });
});

describe("AdminApp tabs & content editing", () => {
  it("switches to the Content tab and back", async () => {
    const app = await signedIn();
    q(app, ".adm-tab-content").click();
    expect(q(app, ".adm-tab-content").getAttribute("aria-selected")).toBe("true");
    expect(q(app, ".adm-content-form")).toBeTruthy();
    q(app, ".adm-tab-dashboard").click();
    expect(q(app, ".adm-tab-dashboard").getAttribute("aria-selected")).toBe("true");
    expect(q(app, ".adm-refresh")).toBeTruthy();
  });

  async function openContent(): Promise<AdminApp> {
    const app = await signedIn();
    q(app, ".adm-tab-content").click();
    return app;
  }

  it("validates that an id is present before loading", async () => {
    const app = await openContent();
    await app.loadContent("   ");
    expect(statusText(app)).toMatch(/document id/i);
  });

  it("loads a document into the editor", async () => {
    const app = await openContent();
    await app.loadContent("fees-2026");
    expect((q(app, ".adm-field-title") as HTMLInputElement).value).toBe("Fees 2026");
    expect((q(app, ".adm-field-body") as HTMLInputElement).value).toBe("Draft body");
    expect(q(app, ".adm-content-editor").hidden).toBe(false);
  });

  it("loads a document via the form submit", async () => {
    const app = await openContent();
    (q(app, ".adm-content-id") as HTMLInputElement).value = "fees-2026";
    q(app, ".adm-content-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await tick();
    expect((q(app, ".adm-field-title") as HTMLInputElement).value).toBe("Fees 2026");
  });

  it("shows an error when loading a document fails", async () => {
    const app = await openContent();
    client.getContentImpl = async () => {
      throw new Error("not found");
    };
    await app.loadContent("missing");
    expect(statusText(app)).toMatch(/not found/);
  });

  it("saves the edited draft, carrying the loaded metadata", async () => {
    const app = await openContent();
    await app.loadContent("fees-2026");
    (q(app, ".adm-field-title") as HTMLInputElement).value = "Fees 2026 (rev)";
    (q(app, ".adm-field-body") as HTMLInputElement).value = "New draft body";
    await app.saveContent();

    expect(client.saved).toHaveLength(1);
    expect(client.saved[0].draft).toEqual({
      topic: "fees",
      title: "Fees 2026 (rev)",
      body: "New draft body",
      metadata: { reviewed: true },
    });
    expect(statusText(app)).toMatch(/draft saved/i);
  });

  it("saves via the Save button", async () => {
    const app = await openContent();
    await app.loadContent("fees-2026");
    q(app, ".adm-save").click();
    await tick();
    expect(client.saved).toHaveLength(1);
  });

  it("does nothing on save when no document is loaded", async () => {
    const app = await openContent();
    await app.saveContent();
    expect(client.saved).toHaveLength(0);
  });

  it("shows an error when saving fails", async () => {
    const app = await openContent();
    await app.loadContent("fees-2026");
    client.saveContentImpl = async () => {
      throw new Error("save boom");
    };
    await app.saveContent();
    expect(statusText(app)).toMatch(/save boom/);
  });

  it("publishes the loaded document and reports the new version", async () => {
    const app = await openContent();
    await app.loadContent("fees-2026");
    await app.publishContent();
    expect(client.published).toEqual(["fees-2026"]);
    expect(statusText(app)).toMatch(/version 2/i);
    expect(q(app, ".adm-published-version").textContent).toContain("2");
  });

  it("publishes via the Publish button", async () => {
    const app = await openContent();
    await app.loadContent("fees-2026");
    q(app, ".adm-publish").click();
    await tick();
    expect(client.published).toEqual(["fees-2026"]);
  });

  it("does nothing on publish when no document is loaded", async () => {
    const app = await openContent();
    await app.publishContent();
    expect(client.published).toHaveLength(0);
  });

  it("shows an error when publishing fails", async () => {
    const app = await openContent();
    await app.loadContent("fees-2026");
    client.publishContentImpl = async () => {
      throw new Error("publish boom");
    };
    await app.publishContent();
    expect(statusText(app)).toMatch(/publish boom/);
  });

  it("clears a loaded document when switching tabs (no stale save)", async () => {
    const app = await openContent();
    await app.loadContent("fees-2026");
    q(app, ".adm-tab-dashboard").click();
    q(app, ".adm-tab-content").click();
    await app.saveContent();
    expect(client.saved).toHaveLength(0);
  });
});

describe("AdminApp default client factory", () => {
  it("logs in and loads the dashboard with the real AdminClient", async () => {
    const original = globalThis.fetch;
    const seen: string[] = [];
    globalThis.fetch = (async (url: string, init: RequestInit) => {
      const path = String(url);
      if (path.endsWith("/admin/login")) {
        return new Response(
          JSON.stringify({ token: "real-sess", username: "admin", expires_in: 3600 }),
          { status: 200 },
        );
      }
      seen.push((init.headers as Record<string, string>).Authorization);
      const body = path.endsWith("/dead-ends")
        ? { dead_ends: [] }
        : path.endsWith("/stats")
          ? { questions_per_day: {}, busiest_topics: [], lead_count: 0, answered_count: 0, dead_end_count: 0 }
          : { leads: [] };
      return new Response(JSON.stringify(body), { status: 200 });
    }) as unknown as typeof fetch;

    try {
      const app = new AdminApp({ container, baseUrl: "http://x" });
      await app.login("admin", "pw");
      expect(app.authenticated).toBe(true);
      // Dashboard calls carried the Bearer token issued by login.
      expect(seen).toContain("Bearer real-sess");
      expect(app.root.querySelector(".adm-stats")).toBeTruthy();
    } finally {
      globalThis.fetch = original;
    }
  });
});

describe("AdminApp non-Error rejections", () => {
  it("stringifies a non-Error thrown value into the status message", async () => {
    const app = await signedIn();
    client.statsImpl = async () => {
      throw "plain string failure";
    };
    await app.loadDashboard();
    expect(statusText(app)).toContain("plain string failure");
  });
});
