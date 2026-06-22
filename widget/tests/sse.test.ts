import { describe, expect, it } from "vitest";

import { createSSEParser, type SSEEvent } from "../src/sse";

describe("createSSEParser", () => {
  it("parses complete events", () => {
    const events: SSEEvent[] = [];
    const feed = createSSEParser((e) => events.push(e));
    feed('data: {"type":"token","text":"Hello"}\n\n');
    feed('data: {"type":"done","outcome":"answered","offer_lead":false}\n\n');
    expect(events).toEqual([
      { type: "token", text: "Hello" },
      { type: "done", outcome: "answered", offer_lead: false },
    ]);
  });

  it("handles events split across chunks", () => {
    const events: SSEEvent[] = [];
    const feed = createSSEParser((e) => events.push(e));
    feed('data: {"type":"to');
    feed('ken","text":"Hi"}\n');
    feed('\ndata: {"type":"done","outcome":"dead_end","offer_lead":true}\n\n');
    expect(events[0]).toEqual({ type: "token", text: "Hi" });
    expect(events[1]).toMatchObject({ type: "done", outcome: "dead_end", offer_lead: true });
  });

  it("ignores blank and non-data blocks", () => {
    const events: SSEEvent[] = [];
    const feed = createSSEParser((e) => events.push(e));
    feed('\n\n: comment\n\ndata: {"type":"token","text":"x"}\n\n');
    expect(events).toEqual([{ type: "token", text: "x" }]);
  });
});
