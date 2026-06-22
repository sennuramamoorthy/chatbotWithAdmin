import { describe, expect, it } from "vitest";

import { AdminClient, HttpError } from "../src/api";

interface Captured {
  url: string;
  init: RequestInit;
}

/** A fake fetch that records the call and returns a canned JSON Response. */
function recordingFetch(body: unknown, status = 200): { fetch: typeof fetch; calls: Captured[] } {
  const calls: Captured[] = [];
  const fetchFn = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(JSON.stringify(body), { status });
  }) as unknown as typeof fetch;
  return { fetch: fetchFn, calls };
}

const TOKEN = "secret-token";

describe("AdminClient request wiring", () => {
  it("sends the Bearer header on a GET and parses JSON", async () => {
    const { fetch, calls } = recordingFetch({ dead_ends: [{ question: "fees?", frequency: 3 }] });
    const result = await new AdminClient("http://x", TOKEN, fetch).deadEnds();

    expect(result.dead_ends[0]).toEqual({ question: "fees?", frequency: 3 });
    expect(calls[0].url).toBe("http://x/api/v1/admin/dashboard/dead-ends");
    expect(calls[0].init.method).toBe("GET");
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBe(
      "Bearer secret-token",
    );
    // GET has no JSON body / content-type.
    expect(calls[0].init.body).toBeUndefined();
    expect((calls[0].init.headers as Record<string, string>)["content-type"]).toBeUndefined();
  });

  it("fetches stats", async () => {
    const stats = { questions_per_day: { "2026-06-15": 4 }, busiest_topics: [["fees", 9]], lead_count: 2 };
    const { fetch, calls } = recordingFetch(stats);
    const result = await new AdminClient("http://x", TOKEN, fetch).stats();
    expect(result.lead_count).toBe(2);
    expect(calls[0].url).toBe("http://x/api/v1/admin/dashboard/stats");
  });

  it("invokes fetch bound to the global scope (guards against illegal invocation)", async () => {
    let boundToGlobal = false;
    const fetchFn = (async function (this: unknown) {
      boundToGlobal = this === globalThis;
      return new Response(JSON.stringify({ dead_ends: [] }), { status: 200 });
    }) as unknown as typeof fetch;
    await new AdminClient("http://x", TOKEN, fetchFn).deadEnds();
    expect(boundToGlobal).toBe(true); // not bound to the AdminClient instance
  });

  it("fetches leads", async () => {
    const { fetch, calls } = recordingFetch({ leads: [] });
    const result = await new AdminClient("http://x", TOKEN, fetch).leads();
    expect(result.leads).toEqual([]);
    expect(calls[0].url).toBe("http://x/api/v1/admin/leads");
  });

  it("POSTs to cluster with the Bearer header and no body", async () => {
    const { fetch, calls } = recordingFetch({ clustered: 5 });
    const result = await new AdminClient("http://x", TOKEN, fetch).cluster();
    expect(result.clustered).toBe(5);
    expect(calls[0].url).toBe("http://x/api/v1/admin/cluster");
    expect(calls[0].init.method).toBe("POST");
    expect(calls[0].init.body).toBeUndefined();
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBe(
      "Bearer secret-token",
    );
  });

  it("fetches a content document by id", async () => {
    const doc = {
      id: "fees-2026",
      topic: "fees",
      title: "Fees",
      draft_body: "draft",
      published_body: "pub",
      published_version: 2,
      last_updated: "2026-06-15",
      metadata: {},
    };
    const { fetch, calls } = recordingFetch(doc);
    const result = await new AdminClient("http://x", TOKEN, fetch).getContent("fees-2026");
    expect(result.title).toBe("Fees");
    expect(calls[0].url).toBe("http://x/api/v1/admin/content/fees-2026");
    expect(calls[0].init.method).toBe("GET");
  });

  it("PUTs a content draft with a JSON body and content-type", async () => {
    const { fetch, calls } = recordingFetch({ id: "fees-2026", title: "New" });
    await new AdminClient("http://x", TOKEN, fetch).saveContent("fees-2026", {
      topic: "fees",
      title: "New",
      body: "Updated body",
      metadata: { a: 1 },
    });
    expect(calls[0].url).toBe("http://x/api/v1/admin/content/fees-2026");
    expect(calls[0].init.method).toBe("PUT");
    expect((calls[0].init.headers as Record<string, string>)["content-type"]).toBe(
      "application/json",
    );
    expect(JSON.parse(calls[0].init.body as string)).toEqual({
      topic: "fees",
      title: "New",
      body: "Updated body",
      metadata: { a: 1 },
    });
  });

  it("POSTs credentials to login and returns the issued token", async () => {
    const { fetch, calls } = recordingFetch({ token: "sess.tok", username: "admin", expires_in: 3600 });
    const result = await new AdminClient("http://x", "", fetch).login("admin", "pw");
    expect(result.token).toBe("sess.tok");
    expect(result.username).toBe("admin");
    expect(calls[0].url).toBe("http://x/api/v1/admin/login");
    expect(calls[0].init.method).toBe("POST");
    expect(JSON.parse(calls[0].init.body as string)).toEqual({ username: "admin", password: "pw" });
  });

  it("POSTs to publish a content document", async () => {
    const { fetch, calls } = recordingFetch({ id: "fees-2026", published_version: 3 });
    const result = await new AdminClient("http://x", TOKEN, fetch).publishContent("fees-2026");
    expect(result.published_version).toBe(3);
    expect(calls[0].url).toBe("http://x/api/v1/admin/content/fees-2026/publish");
    expect(calls[0].init.method).toBe("POST");
    expect(calls[0].init.body).toBeUndefined();
  });
});

describe("AdminClient error handling", () => {
  it("throws an HttpError carrying the status on a non-ok response", async () => {
    const fetchFn = (async () => new Response("nope", { status: 401 })) as unknown as typeof fetch;
    const promise = new AdminClient("http://x", TOKEN, fetchFn).deadEnds();
    await expect(promise).rejects.toThrow(/401/);
    await expect(promise).rejects.toBeInstanceOf(HttpError);
    await expect(promise).rejects.toHaveProperty("status", 401);
  });

  it("throws a clear error when fetch throws an Error", async () => {
    const fetchFn = (async () => {
      throw new Error("network down");
    }) as unknown as typeof fetch;
    await expect(new AdminClient("http://x", TOKEN, fetchFn).stats()).rejects.toThrow(
      /network down/,
    );
  });

  it("throws a clear error when fetch throws a non-Error value", async () => {
    const fetchFn = (async () => {
      throw "boom";
    }) as unknown as typeof fetch;
    await expect(new AdminClient("http://x", TOKEN, fetchFn).leads()).rejects.toThrow(/boom/);
  });

  it("defaults to the real global fetch when none is injected", () => {
    // Just constructs without a fetchFn; exercises the default parameter binding.
    const client = new AdminClient("http://x", TOKEN);
    expect(client).toBeInstanceOf(AdminClient);
  });
});
