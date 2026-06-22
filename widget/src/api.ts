// Thin client over the chatbot HTTP API. All failures degrade softly (AC-10.3):
// streamChat invokes onError, submitLead/health return a not-ok result.

import { createSSEParser } from "./sse";

export interface ChatCallbacks {
  onToken: (text: string) => void;
  onDone: (meta: { outcome: string; offer_lead: boolean }) => void;
  onError: () => void;
}

export interface LeadPayload {
  name: string;
  email?: string;
  phone?: string;
  program?: string;
  message?: string;
  consent: boolean;
  dead_end_question?: string | null;
  session_id?: string;
}

export interface LeadResult {
  ok: boolean;
  lead_id?: string;
  errors?: Array<{ field: string; code: string; message: string }>;
}

export class ChatClient {
  private readonly baseUrl: string;
  private readonly fetchFn: typeof fetch;

  constructor(baseUrl: string, fetchFn: typeof fetch = fetch) {
    this.baseUrl = baseUrl;
    // Bind to the global scope: calling `this.fetchFn(...)` would otherwise invoke
    // the global fetch with `this === ChatClient`, which throws "Illegal invocation"
    // in real browsers (jsdom's fake fetch doesn't care, so unit tests can't catch it).
    this.fetchFn = fetchFn.bind(globalThis) as typeof fetch;
  }

  async streamChat(message: string, sessionId: string, cb: ChatCallbacks): Promise<void> {
    let response: Response;
    try {
      response = await this.fetchFn(`${this.baseUrl}/api/v1/chat`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId }),
      });
    } catch {
      cb.onError();
      return;
    }

    if (!response.ok || !response.body) {
      cb.onError();
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const feed = createSSEParser((event) => {
      if (event.type === "token") {
        cb.onToken(event.text);
      } else {
        cb.onDone({ outcome: event.outcome, offer_lead: event.offer_lead ?? false });
      }
    });

    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        feed(decoder.decode(value, { stream: true }));
      }
    } catch {
      // A mid-stream read/parse failure must still soft-fail gracefully (AC-10.3).
      cb.onError();
    }
  }

  async submitLead(payload: LeadPayload): Promise<LeadResult> {
    try {
      const response = await this.fetchFn(`${this.baseUrl}/api/v1/leads`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (response.status === 201) {
        return { ok: true, lead_id: (await response.json()).lead_id };
      }
      if (response.status === 422) {
        return { ok: false, errors: (await response.json()).errors };
      }
      return { ok: false, errors: [] };
    } catch {
      return { ok: false, errors: [] };
    }
  }

  async health(): Promise<boolean> {
    try {
      const response = await this.fetchFn(`${this.baseUrl}/api/v1/health`);
      return response.ok;
    } catch {
      return false;
    }
  }
}
