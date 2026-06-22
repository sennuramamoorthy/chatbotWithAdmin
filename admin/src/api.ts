// Thin client over the chatbot's authenticated admin HTTP API. Every request sends
// `Authorization: Bearer <token>`. Unlike the public widget client (which degrades
// softly), admin calls throw a clear Error on a non-ok response or a thrown fetch,
// so the admin UI can surface the failure to the operator.

/** Error thrown on a non-ok response, carrying the HTTP status so callers can
 * distinguish auth failures (401 → re-login) from other errors. */
export class HttpError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "HttpError";
    this.status = status;
  }
}

export interface LoginResponse {
  token: string;
  username: string;
  expires_in: number;
}

export interface DeadEnd {
  question: string;
  frequency: number;
}

export interface DeadEndsResponse {
  dead_ends: DeadEnd[];
}

export interface StatsResponse {
  questions_per_day: Record<string, number>;
  busiest_topics: Array<[string, number]>;
  lead_count: number;
  /** Turns the bot answered from the KB (drives the answer-coverage KPI). */
  answered_count: number;
  /** Turns the bot could not ground — the raw unanswered volume. */
  dead_end_count: number;
}

export interface Lead {
  id: string;
  name: string;
  email: string;
  phone: string;
  program: string;
  message: string;
  dead_end_question: string | null;
  created_at: string;
  delivery_status: string;
}

export interface LeadsResponse {
  leads: Lead[];
}

export interface ClusterResponse {
  clustered: number;
}

export interface ContentDocument {
  id: string;
  topic: string;
  title: string;
  draft_body: string;
  published_body: string;
  published_version: number;
  last_updated: string;
  metadata: Record<string, unknown>;
}

export interface ContentDraft {
  topic: string;
  title: string;
  body: string;
  metadata: Record<string, unknown>;
}

export class AdminClient {
  private readonly baseUrl: string;
  private readonly token: string;
  private readonly fetchFn: typeof fetch;

  constructor(baseUrl: string, token: string, fetchFn: typeof fetch = fetch) {
    this.baseUrl = baseUrl;
    this.token = token;
    // Bind to the global scope: `this.fetchFn(...)` would otherwise call the global
    // fetch with `this === AdminClient` → "Illegal invocation" in real browsers
    // (jsdom's fake fetch doesn't care, so unit tests can't catch it).
    this.fetchFn = fetchFn.bind(globalThis) as typeof fetch;
  }

  /** Exchange username + password for a session token (no auth header needed). */
  login(username: string, password: string): Promise<LoginResponse> {
    return this.send<LoginResponse>("POST", "/api/v1/admin/login", { username, password });
  }

  deadEnds(): Promise<DeadEndsResponse> {
    return this.get<DeadEndsResponse>("/api/v1/admin/dashboard/dead-ends");
  }

  stats(): Promise<StatsResponse> {
    return this.get<StatsResponse>("/api/v1/admin/dashboard/stats");
  }

  leads(): Promise<LeadsResponse> {
    return this.get<LeadsResponse>("/api/v1/admin/leads");
  }

  cluster(): Promise<ClusterResponse> {
    return this.send<ClusterResponse>("POST", "/api/v1/admin/cluster");
  }

  getContent(id: string): Promise<ContentDocument> {
    return this.get<ContentDocument>(`/api/v1/admin/content/${id}`);
  }

  saveContent(id: string, draft: ContentDraft): Promise<ContentDocument> {
    return this.send<ContentDocument>("PUT", `/api/v1/admin/content/${id}`, draft);
  }

  publishContent(id: string): Promise<ContentDocument> {
    return this.send<ContentDocument>("POST", `/api/v1/admin/content/${id}/publish`);
  }

  private get<T>(path: string): Promise<T> {
    return this.request<T>("GET", path);
  }

  private send<T>(method: string, path: string, body?: unknown): Promise<T> {
    return this.request<T>(method, path, body);
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.token}`,
    };
    const init: RequestInit = { method, headers };
    if (body !== undefined) {
      headers["content-type"] = "application/json";
      init.body = JSON.stringify(body);
    }

    let response: Response;
    try {
      response = await this.fetchFn(`${this.baseUrl}${path}`, init);
    } catch (cause) {
      throw new Error(`Request to ${path} failed: ${describe(cause)}`);
    }

    if (!response.ok) {
      throw new HttpError(response.status, `Request to ${path} failed with status ${response.status}.`);
    }

    return (await response.json()) as T;
  }
}

function describe(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}
