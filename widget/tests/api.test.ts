import { describe, expect, it } from "vitest";

import { ChatClient } from "../src/api";

function streamResponse(chunks: string[], status = 200): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(stream, { status });
}

const noop = () => {};

describe("ChatClient.streamChat", () => {
  it("streams tokens then a done event", async () => {
    const tokens: string[] = [];
    let done: { outcome: string; offer_lead: boolean } | null = null;
    const fetchFn = async () =>
      streamResponse([
        'data: {"type":"token","text":"Hello "}\n\n',
        'data: {"type":"token","text":"world"}\n\n',
        'data: {"type":"done","outcome":"answered"}\n\n',
      ]);

    await new ChatClient("http://x", fetchFn as typeof fetch).streamChat("hi", "s", {
      onToken: (t) => tokens.push(t),
      onDone: (d) => (done = d),
      onError: noop,
    });

    expect(tokens.join("")).toBe("Hello world");
    expect(done).toEqual({ outcome: "answered", offer_lead: false });
  });

  it("soft-fails on a non-ok response", async () => {
    let errored = false;
    const fetchFn = async () => new Response("nope", { status: 503 });
    await new ChatClient("http://x", fetchFn as typeof fetch).streamChat("hi", "s", {
      onToken: noop,
      onDone: noop,
      onError: () => (errored = true),
    });
    expect(errored).toBe(true);
  });

  it("soft-fails when the response has no body", async () => {
    let errored = false;
    const fetchFn = async () => new Response(null, { status: 200 });
    await new ChatClient("http://x", fetchFn as typeof fetch).streamChat("hi", "s", {
      onToken: noop,
      onDone: noop,
      onError: () => (errored = true),
    });
    expect(errored).toBe(true);
  });

  it("soft-fails when fetch throws", async () => {
    let errored = false;
    const fetchFn = async () => {
      throw new Error("network");
    };
    await new ChatClient("http://x", fetchFn as typeof fetch).streamChat("hi", "s", {
      onToken: noop,
      onDone: noop,
      onError: () => (errored = true),
    });
    expect(errored).toBe(true);
  });

  it("invokes fetch bound to the global scope (guards against illegal invocation)", async () => {
    let boundToGlobal = false;
    function fakeFetch(this: unknown) {
      boundToGlobal = this === globalThis;
      return Promise.resolve(streamResponse(['data: {"type":"done","outcome":"answered"}\n\n']));
    }
    await new ChatClient("http://x", fakeFetch as typeof fetch).streamChat("hi", "s", {
      onToken: noop,
      onDone: noop,
      onError: noop,
    });
    expect(boundToGlobal).toBe(true); // not bound to the ChatClient instance
  });

  it("soft-fails when the stream errors mid-read", async () => {
    let errored = false;
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.error(new Error("stream broke"));
      },
    });
    const fetchFn = async () => new Response(stream, { status: 200 });
    await new ChatClient("http://x", fetchFn as typeof fetch).streamChat("hi", "s", {
      onToken: noop,
      onDone: noop,
      onError: () => (errored = true),
    });
    expect(errored).toBe(true);
  });
});

describe("ChatClient.submitLead", () => {
  it("returns the lead id on 201", async () => {
    const fetchFn = async () => new Response(JSON.stringify({ lead_id: "lead-1" }), { status: 201 });
    const result = await new ChatClient("http://x", fetchFn as typeof fetch).submitLead({} as never);
    expect(result).toEqual({ ok: true, lead_id: "lead-1" });
  });

  it("returns field errors on 422", async () => {
    const body = JSON.stringify({ errors: [{ field: "name", code: "required", message: "x" }] });
    const fetchFn = async () => new Response(body, { status: 422 });
    const result = await new ChatClient("http://x", fetchFn as typeof fetch).submitLead({} as never);
    expect(result.ok).toBe(false);
    expect(result.errors?.[0].field).toBe("name");
  });

  it("returns not-ok on unexpected status", async () => {
    const fetchFn = async () => new Response("boom", { status: 500 });
    const result = await new ChatClient("http://x", fetchFn as typeof fetch).submitLead({} as never);
    expect(result.ok).toBe(false);
  });

  it("soft-fails when fetch throws", async () => {
    const fetchFn = async () => {
      throw new Error("network");
    };
    const result = await new ChatClient("http://x", fetchFn as typeof fetch).submitLead({} as never);
    expect(result.ok).toBe(false);
  });
});

describe("ChatClient.health", () => {
  it("is true when the endpoint is ok", async () => {
    const fetchFn = async () => new Response("", { status: 200 });
    expect(await new ChatClient("http://x", fetchFn as typeof fetch).health()).toBe(true);
  });

  it("is false when fetch throws", async () => {
    const fetchFn = async () => {
      throw new Error("down");
    };
    expect(await new ChatClient("http://x", fetchFn as typeof fetch).health()).toBe(false);
  });
});
