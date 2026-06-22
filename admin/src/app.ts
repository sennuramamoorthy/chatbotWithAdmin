// The admin single-page app. Gates a username/password login screen in front of two
// tabs (Dashboard / Content); on success it stores the issued session token (in
// sessionStorage, so a reload stays signed in) and drives the AdminClient with it.
// The AdminClient is injected so tests can pass a fake; main.ts constructs the real
// one. All async failures are caught and shown as a message rather than thrown, so a
// down backend never leaves a blank UI; a 401 mid-session bounces back to login.

import { AdminClient, HttpError, type ContentDocument, type ContentDraft } from "./api";
import { renderDeadEnds, renderLeads, renderStats } from "./render";

export type Tab = "dashboard" | "content";

export interface AdminAppConfig {
  container: HTMLElement;
  baseUrl: string;
  /** Build a client from the current token. Injectable for tests. */
  clientFactory?: (baseUrl: string, token: string) => AdminClient;
}

const STYLE = `
  .adm {
    --adm-bg: #eef1f6; --adm-surface: #ffffff; --adm-surface-2: #f7f9fc;
    --adm-border: #e6eaf1; --adm-border-strong: #cbd5e1;
    --adm-text: #0f172a; --adm-muted: #64748b; --adm-faint: #94a3b8;
    --adm-primary: #1f4e8c; --adm-primary-700: #173d6e; --adm-primary-50: #eaf1fa;
    --adm-accent: #0d9488;
    --adm-ok: #15803d; --adm-ok-bg: #dcfce7;
    --adm-warn: #b45309; --adm-warn-bg: #fef3c7;
    --adm-danger: #b91c1c; --adm-danger-bg: #fee2e2;
    --adm-radius: 14px; --adm-radius-sm: 9px;
    --adm-shadow-sm: 0 1px 2px rgba(15,23,42,.06);
    --adm-shadow: 0 1px 2px rgba(15,23,42,.04), 0 8px 24px rgba(15,23,42,.06);
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    color: var(--adm-text); max-width: 1180px; margin: 0 auto; font-size: 14px; line-height: 1.5;
  }
  .adm * { box-sizing: border-box; }

  /* Header */
  .adm-header { display: flex; align-items: center; justify-content: space-between; gap: 16px;
    flex-wrap: wrap; padding: 18px 20px; background: var(--adm-surface);
    border: 1px solid var(--adm-border); border-radius: var(--adm-radius); box-shadow: var(--adm-shadow-sm); }
  .adm-brand { display: flex; align-items: center; gap: 14px; }
  .adm-logo { width: 46px; height: 46px; border-radius: 12px; display: grid; place-items: center;
    color: #fff; font-weight: 800; letter-spacing: .04em; font-size: 16px;
    background: linear-gradient(135deg, var(--adm-primary), var(--adm-accent)); box-shadow: var(--adm-shadow-sm); }
  .adm-title { margin: 0; font-size: 19px; font-weight: 700; letter-spacing: -.01em; }
  .adm-subtitle { margin: 2px 0 0; font-size: 12.5px; color: var(--adm-muted); }
  .adm-token-field { display: flex; flex-direction: column; gap: 5px; min-width: 260px; flex: 0 1 320px; }
  .adm-token-field > span { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--adm-muted); }

  /* Inputs */
  .adm input, .adm textarea { width: 100%; padding: 9px 11px; font: inherit; color: var(--adm-text);
    background: var(--adm-surface); border: 1px solid var(--adm-border-strong); border-radius: var(--adm-radius-sm); }
  .adm textarea { resize: vertical; min-height: 120px; line-height: 1.5; }
  .adm input::placeholder { color: var(--adm-faint); }
  .adm :focus-visible { outline: 2px solid var(--adm-primary); outline-offset: 2px; }
  .adm input:focus, .adm textarea:focus { outline: none; border-color: var(--adm-primary);
    box-shadow: 0 0 0 3px var(--adm-primary-50); }

  /* Buttons */
  .adm button { font: inherit; font-weight: 600; cursor: pointer; border: 1px solid transparent;
    border-radius: var(--adm-radius-sm); padding: 9px 15px; transition: background .15s, border-color .15s, box-shadow .15s; }
  .adm-refresh, .adm-load, .adm-publish { background: var(--adm-primary); color: #fff; }
  .adm-refresh:hover, .adm-load:hover, .adm-publish:hover { background: var(--adm-primary-700); }
  .adm-cluster, .adm-save { background: var(--adm-surface); color: var(--adm-primary); border-color: var(--adm-border-strong); }
  .adm-cluster:hover, .adm-save:hover { background: var(--adm-primary-50); }

  /* Toolbar + tabs + status */
  .adm-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px;
    flex-wrap: wrap; margin: 16px 0; }
  .adm-tabs { display: inline-flex; gap: 2px; padding: 3px; background: var(--adm-surface);
    border: 1px solid var(--adm-border); border-radius: var(--adm-radius-sm); box-shadow: var(--adm-shadow-sm); }
  .adm-tab { background: transparent; color: var(--adm-muted); border: none; padding: 7px 18px; border-radius: 6px; }
  .adm-tab:hover { color: var(--adm-text); }
  .adm-tab[aria-selected="true"] { background: var(--adm-primary); color: #fff; }
  .adm-status { margin: 0; font-size: 13px; font-weight: 500; padding: 6px 12px; border-radius: 999px;
    display: inline-flex; align-items: center; gap: 7px; background: var(--adm-surface);
    color: var(--adm-muted); border: 1px solid var(--adm-border); }
  .adm-status:empty { display: none; }
  .adm-status::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: currentColor; opacity: .75; }
  .adm-status[data-kind="ok"] { background: var(--adm-ok-bg); color: var(--adm-ok); border-color: transparent; }
  .adm-status[data-kind="error"] { background: var(--adm-danger-bg); color: var(--adm-danger); border-color: transparent; }

  /* Panel layout */
  .adm-panel { display: grid; gap: 16px; }
  .adm-actions { display: flex; gap: 10px; flex-wrap: wrap; }

  /* Cards */
  .adm-card { background: var(--adm-surface); border: 1px solid var(--adm-border);
    border-radius: var(--adm-radius); padding: 16px 18px; box-shadow: var(--adm-shadow-sm); }
  .adm-card-head { margin-bottom: 12px; }
  .adm-card-title-row { display: flex; align-items: center; gap: 10px; }
  .adm-card-title { margin: 0; font-size: 15px; font-weight: 700; }
  .adm-card-sub { margin: 3px 0 0; font-size: 12.5px; color: var(--adm-muted); }
  .adm-badge { font-size: 12px; font-weight: 700; padding: 1px 9px; border-radius: 999px;
    background: var(--adm-primary-50); color: var(--adm-primary); }

  /* KPI cards */
  .adm-kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
  .adm-kpi { position: relative; background: var(--adm-surface); border: 1px solid var(--adm-border);
    border-radius: var(--adm-radius); padding: 16px 18px 18px; box-shadow: var(--adm-shadow-sm); overflow: hidden; }
  .adm-kpi::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 4px; background: var(--k, var(--adm-primary)); }
  .adm-kpi[data-accent="brand"] { --k: var(--adm-primary); }
  .adm-kpi[data-accent="ok"] { --k: var(--adm-ok); }
  .adm-kpi[data-accent="warn"] { --k: var(--adm-warn); }
  .adm-kpi[data-accent="accent"] { --k: var(--adm-accent); }
  .adm-kpi-label { margin: 0; font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: .06em; color: var(--adm-muted); }
  .adm-kpi-value { margin: 8px 0 4px; font-size: 30px; font-weight: 750; letter-spacing: -.02em;
    font-variant-numeric: tabular-nums; line-height: 1; }
  .adm-kpi-sub { margin: 0; font-size: 12px; color: var(--adm-muted); }

  /* Charts */
  .adm-charts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
  .adm-chart-body { padding-top: 4px; }
  .adm-area-wrap { display: flex; flex-direction: column; gap: 6px; }
  .adm-area { width: 100%; height: 120px; display: block; }
  .adm-area-axis { stroke: var(--adm-border); stroke-width: 1; }
  .adm-area-line { stroke: var(--adm-primary); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
  .adm-area-bar { fill: var(--adm-primary); opacity: .9; }
  .adm-area-bar-label { fill: var(--adm-muted); font-size: 11px; font-weight: 700; }
  .adm-area-dot { fill: var(--adm-surface); stroke: var(--adm-primary); stroke-width: 1.5; }
  .adm-area-labels { display: flex; justify-content: space-between; font-size: 11px; color: var(--adm-faint); }
  .adm-area-labels span:only-child { margin: 0 auto; }

  .adm-bars { display: flex; flex-direction: column; gap: 10px; }
  .adm-bar-row { display: grid; grid-template-columns: 76px 1fr 34px; align-items: center; gap: 10px; }
  .adm-bar-label { font-size: 12.5px; color: var(--adm-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-transform: capitalize; }
  .adm-bar-track { height: 10px; background: var(--adm-surface-2); border: 1px solid var(--adm-border); border-radius: 999px; overflow: hidden; }
  .adm-bar-track--sm { height: 8px; }
  .adm-bar-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--adm-primary), var(--adm-accent)); }
  .adm-bar-value { font-size: 12.5px; font-weight: 600; color: var(--adm-muted); text-align: right; font-variant-numeric: tabular-nums; }

  .adm-donut-wrap { display: flex; flex-direction: column; align-items: center; gap: 10px; }
  .adm-donut { width: 130px; height: 130px; }
  .adm-donut-track { stroke: var(--adm-border); }
  .adm-donut-value { stroke: var(--adm-ok); }
  .adm-donut-pct { fill: var(--adm-text); font-size: 27px; font-weight: 750; font-variant-numeric: tabular-nums; }
  .adm-donut-cap { fill: var(--adm-muted); font-size: 10px; letter-spacing: .12em; text-transform: uppercase; }
  .adm-donut-legend { display: flex; gap: 16px; flex-wrap: wrap; justify-content: center; }
  .adm-legend-item { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--adm-muted); }
  .adm-legend-dot { width: 9px; height: 9px; border-radius: 50%; }
  .adm-dot-ok { background: var(--adm-ok); }
  .adm-dot-warn { background: var(--adm-border-strong); }

  /* Tables */
  .adm-table { border-collapse: collapse; width: 100%; }
  .adm-table thead th { text-align: left; font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: .05em; color: var(--adm-muted); padding: 8px 12px; border-bottom: 1px solid var(--adm-border); }
  .adm-table tbody td { padding: 11px 12px; font-size: 13px; border-bottom: 1px solid var(--adm-border); vertical-align: middle; }
  .adm-table tbody tr:last-child td { border-bottom: none; }
  .adm-table tbody tr:hover { background: var(--adm-surface-2); }
  .adm-rank { color: var(--adm-faint); font-weight: 700; font-variant-numeric: tabular-nums; width: 44px; }
  .adm-freq-cell { display: flex; align-items: center; gap: 10px; min-width: 120px; }
  .adm-freq-cell .adm-bar-track { flex: 1; }
  .adm-freq-val { font-weight: 700; font-variant-numeric: tabular-nums; min-width: 20px; text-align: right; }
  .adm-contact-email { font-weight: 500; }
  .adm-contact-phone { font-size: 12px; color: var(--adm-muted); }
  .adm-tag { display: inline-block; font-size: 12px; font-weight: 600; padding: 2px 9px; border-radius: 999px;
    background: var(--adm-primary-50); color: var(--adm-primary-700); }
  .adm-pill { display: inline-flex; align-items: center; font-size: 11px; font-weight: 700; padding: 3px 10px;
    border-radius: 999px; text-transform: capitalize; background: var(--adm-surface-2); color: var(--adm-muted); }
  .adm-pill[data-status="ok"] { background: var(--adm-ok-bg); color: var(--adm-ok); }
  .adm-pill[data-status="warn"] { background: var(--adm-warn-bg); color: var(--adm-warn); }
  .adm-pill[data-status="danger"] { background: var(--adm-danger-bg); color: var(--adm-danger); }

  /* Empty states */
  .adm-empty { margin: 4px 0 0; color: var(--adm-muted); font-size: 13px; padding: 18px;
    text-align: center; background: var(--adm-surface-2); border: 1px dashed var(--adm-border-strong); border-radius: var(--adm-radius-sm); }

  /* Content editor */
  .adm-content-row { display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; }
  .adm-content-row .adm-field { flex: 1; min-width: 220px; }
  .adm-field { display: flex; flex-direction: column; gap: 5px; font-size: 12px; font-weight: 600;
    text-transform: uppercase; letter-spacing: .05em; color: var(--adm-muted); margin-top: 14px; }
  .adm-content-row .adm-field { margin-top: 0; }
  .adm-field input, .adm-field textarea { text-transform: none; font-weight: 400; letter-spacing: normal; color: var(--adm-text); }
  .adm-field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .adm-published-version { margin: 14px 0 0; font-size: 12.5px; color: var(--adm-muted); }
  .adm-content-editor .adm-actions { margin-top: 16px; }

  /* Responsive */
  @media (max-width: 900px) {
    .adm-kpis { grid-template-columns: repeat(2, 1fr); }
    .adm-charts { grid-template-columns: 1fr; }
    .adm-field-grid { grid-template-columns: 1fr; }
  }
  @media (max-width: 520px) {
    .adm-kpis { grid-template-columns: 1fr; }
  }

  /* Login screen */
  .adm-login { display: flex; justify-content: center; padding: 24px 0 48px; }
  .adm-login-card { width: 100%; max-width: 384px; background: var(--adm-surface);
    border: 1px solid var(--adm-border); border-radius: var(--adm-radius); padding: 26px; box-shadow: var(--adm-shadow); }
  .adm-login-brand { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
  .adm-login-form { display: flex; flex-direction: column; gap: 14px; }
  .adm-login-form .adm-field { margin-top: 0; }
  .adm-login-submit { width: 100%; background: var(--adm-primary); color: #fff; padding: 11px; margin-top: 2px; }
  .adm-login-submit:hover { background: var(--adm-primary-700); }
  .adm-login .adm-status { align-self: flex-start; }

  /* Signed-in user box (shell header) */
  .adm-userbox { display: flex; align-items: center; gap: 12px; }
  .adm-user { font-size: 13px; color: var(--adm-muted); }
  .adm-logout { background: var(--adm-surface); color: var(--adm-primary); border-color: var(--adm-border-strong); }
  .adm-logout:hover { background: var(--adm-primary-50); }

  /* Dark mode — token remap only; components inherit. */
  @media (prefers-color-scheme: dark) {
    .adm {
      --adm-bg: #0b1220; --adm-surface: #131c2e; --adm-surface-2: #0f1726;
      --adm-border: #243149; --adm-border-strong: #33425e;
      --adm-text: #e8edf5; --adm-muted: #93a1b8; --adm-faint: #64748b;
      --adm-primary: #5b8dd6; --adm-primary-700: #7aa6e3; --adm-primary-50: #1b2a44;
      --adm-accent: #2dd4bf;
      --adm-ok: #4ade80; --adm-ok-bg: #14321f;
      --adm-warn: #fbbf24; --adm-warn-bg: #3a2c0a;
      --adm-danger: #f87171; --adm-danger-bg: #3a1414;
      --adm-shadow-sm: 0 1px 2px rgba(0,0,0,.4);
    }
    .adm-refresh, .adm-load, .adm-publish, .adm-login-submit { color: #0b1220; }
  }
`;

const LOGIN_VIEW = `
  <div class="adm-login">
    <div class="adm-login-card">
      <div class="adm-login-brand">
        <div class="adm-logo" aria-hidden="true">TU</div>
        <div>
          <h1 class="adm-title">Admissions Console</h1>
          <p class="adm-subtitle">Sign in to continue</p>
        </div>
      </div>
      <form class="adm-login-form">
        <label class="adm-field">Username
          <input class="adm-login-username" name="username" type="text" autocomplete="username" />
        </label>
        <label class="adm-field">Password
          <input class="adm-login-password" name="password" type="password" autocomplete="current-password" />
        </label>
        <button class="adm-login-submit" type="submit">Sign in</button>
        <p class="adm-status" role="status" aria-live="polite"></p>
      </form>
    </div>
  </div>
`;

const SHELL = `
  <header class="adm-header">
    <div class="adm-brand">
      <div class="adm-logo" aria-hidden="true">TU</div>
      <div>
        <h1 class="adm-title">Admissions Console</h1>
        <p class="adm-subtitle">Takshashila University · chatbot operations</p>
      </div>
    </div>
    <div class="adm-userbox">
      <span class="adm-user"></span>
      <button class="adm-logout" type="button">Log out</button>
    </div>
  </header>
  <div class="adm-toolbar">
    <div class="adm-tabs" role="tablist" aria-label="Admin sections">
      <button class="adm-tab adm-tab-dashboard" type="button" role="tab" aria-selected="true" aria-controls="adm-panel">Dashboard</button>
      <button class="adm-tab adm-tab-content" type="button" role="tab" aria-selected="false" aria-controls="adm-panel">Content</button>
    </div>
    <p class="adm-status" role="status" aria-live="polite"></p>
  </div>
  <div class="adm-panel" id="adm-panel" role="tabpanel"></div>
`;

const CONTENT_FORM = `
  <section class="adm-card adm-content">
    <div class="adm-card-head">
      <h3 class="adm-card-title">Content editor</h3>
      <p class="adm-card-sub">Load a document, edit its draft, then publish to re-index it so the bot can answer it.</p>
    </div>
    <form class="adm-content-form">
      <div class="adm-content-row">
        <label class="adm-field">Document ID
          <input class="adm-content-id" name="id" type="text" autocomplete="off" placeholder="e.g. fees-2026" />
        </label>
        <button class="adm-load" type="submit">Load</button>
      </div>
      <div class="adm-content-editor" hidden>
        <div class="adm-field-grid">
          <label class="adm-field">Topic<input class="adm-field-topic" name="topic" type="text" /></label>
          <label class="adm-field">Title<input class="adm-field-title" name="title" type="text" /></label>
        </div>
        <label class="adm-field">Draft body<textarea class="adm-field-body" name="body" rows="10"></textarea></label>
        <p class="adm-published-version"></p>
        <div class="adm-actions">
          <button class="adm-save" type="button">Save draft</button>
          <button class="adm-publish" type="button">Publish</button>
        </div>
      </div>
    </form>
  </section>
`;

interface Session {
  token: string;
  username: string;
}

const SESSION_KEY = "adm.session";

export class AdminApp {
  readonly root: HTMLElement;
  private readonly container: HTMLElement;
  private readonly baseUrl: string;
  private readonly clientFactory: (baseUrl: string, token: string) => AdminClient;
  private readonly view: HTMLElement;

  private session: Session | null;
  private activeTab: Tab = "dashboard";
  private loadedDoc: ContentDocument | null = null;
  private panel!: HTMLElement; // assigned whenever the authenticated shell renders

  constructor(config: AdminAppConfig) {
    this.container = config.container;
    this.baseUrl = config.baseUrl;
    this.clientFactory =
      config.clientFactory ?? ((baseUrl, token) => new AdminClient(baseUrl, token));

    this.root = document.createElement("div");
    this.root.className = "adm";
    this.root.innerHTML = `<style>${STYLE}</style><div class="adm-view"></div>`;
    this.container.appendChild(this.root);
    this.view = this.root.querySelector(".adm-view")!;

    this.session = readStoredSession();
    this.render();
  }

  get authenticated(): boolean {
    return this.session !== null;
  }

  /** Authenticate with username + password, then reveal the shell and load data. */
  async login(username: string, password: string): Promise<void> {
    const user = username.trim();
    if (!user || !password) {
      this.setStatus("Enter your username and password.", "error");
      return;
    }
    this.setStatus("Signing in…");
    try {
      const result = await this.clientFactory(this.baseUrl, "").login(user, password);
      this.session = { token: result.token, username: result.username };
      storeSession(this.session);
      this.activeTab = "dashboard";
      this.render();
      await this.loadDashboard();
    } catch (error) {
      this.setStatus(loginErrorMessage(error), "error");
    }
  }

  /** Clear the session and return to the login screen. */
  logout(): void {
    this.session = null;
    clearSession();
    this.loadedDoc = null;
    this.activeTab = "dashboard";
    this.render();
  }

  selectTab(tab: Tab): void {
    this.activeTab = tab;
    this.tab("dashboard").setAttribute("aria-selected", String(tab === "dashboard"));
    this.tab("content").setAttribute("aria-selected", String(tab === "content"));
    this.setStatus("");
    this.renderTab();
  }

  /** Loads dead-ends, stats and leads for the Dashboard tab. */
  async loadDashboard(): Promise<void> {
    const client = this.requireClient();
    if (!client) return;

    this.setStatus("Loading dashboard…");
    try {
      const [deadEnds, stats, leads] = await Promise.all([
        client.deadEnds(),
        client.stats(),
        client.leads(),
      ]);
      this.panel.innerHTML = "";
      this.panel.appendChild(this.dashboardControls());
      this.panel.appendChild(renderStats(stats));
      this.panel.appendChild(renderDeadEnds(deadEnds.dead_ends));
      this.panel.appendChild(renderLeads(leads.leads));
      this.setStatus("Dashboard loaded.", "ok");
    } catch (error) {
      this.handleError(error);
    }
  }

  /** Triggers server-side clustering of unanswered questions, then refreshes. */
  async runCluster(): Promise<void> {
    const client = this.requireClient();
    if (!client) return;

    this.setStatus("Clustering…");
    try {
      const result = await client.cluster();
      this.setStatus(`Clustered ${result.clustered} question(s).`, "ok");
      await this.loadDashboard();
    } catch (error) {
      this.handleError(error);
    }
  }

  /** Loads a single content document into the editor. */
  async loadContent(id: string): Promise<void> {
    const client = this.requireClient();
    if (!client) return;
    if (!id.trim()) {
      this.setStatus("Enter a document ID to load.", "error");
      return;
    }

    this.setStatus("Loading document…");
    try {
      const doc = await client.getContent(id.trim());
      this.loadedDoc = doc;
      this.fillEditor(doc);
      this.setStatus(`Loaded "${doc.title}".`, "ok");
    } catch (error) {
      this.handleError(error);
    }
  }

  /** Saves the editor's current values as the document's draft. */
  async saveContent(): Promise<void> {
    const client = this.requireClient();
    if (!client || !this.loadedDoc) return;

    this.setStatus("Saving draft…");
    try {
      const doc = await client.saveContent(this.loadedDoc.id, this.draftFromEditor(this.loadedDoc));
      this.loadedDoc = doc;
      this.fillEditor(doc);
      this.setStatus("Draft saved.", "ok");
    } catch (error) {
      this.handleError(error);
    }
  }

  /** Publishes the loaded document's current draft. */
  async publishContent(): Promise<void> {
    const client = this.requireClient();
    if (!client || !this.loadedDoc) return;

    this.setStatus("Publishing…");
    try {
      const doc = await client.publishContent(this.loadedDoc.id);
      this.loadedDoc = doc;
      this.fillEditor(doc);
      this.setStatus(`Published version ${doc.published_version}.`, "ok");
    } catch (error) {
      this.handleError(error);
    }
  }

  private render(): void {
    if (this.session) this.renderShell();
    else this.renderLogin();
  }

  private renderLogin(): void {
    this.view.innerHTML = LOGIN_VIEW;
    this.view.querySelector(".adm-login-form")!.addEventListener("submit", (e) => {
      e.preventDefault();
      const username = (this.view.querySelector(".adm-login-username") as HTMLInputElement).value;
      const password = (this.view.querySelector(".adm-login-password") as HTMLInputElement).value;
      void this.login(username, password);
    });
  }

  private renderShell(): void {
    this.view.innerHTML = SHELL;
    this.panel = this.view.querySelector(".adm-panel")!;
    (this.view.querySelector(".adm-user") as HTMLElement).textContent =
      `Signed in as ${this.session!.username}`;
    this.view.querySelector(".adm-logout")!.addEventListener("click", () => this.logout());
    this.tab("dashboard").addEventListener("click", () => this.selectTab("dashboard"));
    this.tab("content").addEventListener("click", () => this.selectTab("content"));
    this.renderTab();
  }

  private tab(which: Tab): HTMLButtonElement {
    return this.view.querySelector(`.adm-tab-${which}`) as HTMLButtonElement;
  }

  private renderTab(): void {
    this.panel.innerHTML = "";
    this.loadedDoc = null;
    if (this.activeTab === "dashboard") {
      this.panel.appendChild(this.dashboardControls());
    } else {
      this.renderContentForm();
    }
  }

  private dashboardControls(): HTMLElement {
    const bar = document.createElement("div");
    bar.className = "adm-actions";

    const refresh = document.createElement("button");
    refresh.type = "button";
    refresh.className = "adm-refresh";
    refresh.textContent = "Load dashboard";
    refresh.addEventListener("click", () => void this.loadDashboard());

    const cluster = document.createElement("button");
    cluster.type = "button";
    cluster.className = "adm-cluster";
    cluster.textContent = "Cluster unanswered";
    cluster.addEventListener("click", () => void this.runCluster());

    bar.appendChild(refresh);
    bar.appendChild(cluster);
    return bar;
  }

  private renderContentForm(): void {
    this.panel.innerHTML = CONTENT_FORM;
    this.panel.querySelector(".adm-content-form")!.addEventListener("submit", (e) => {
      e.preventDefault();
      void this.loadContent(this.contentField("id").value);
    });
    this.panel
      .querySelector(".adm-save")!
      .addEventListener("click", () => void this.saveContent());
    this.panel
      .querySelector(".adm-publish")!
      .addEventListener("click", () => void this.publishContent());
  }

  private fillEditor(doc: ContentDocument): void {
    const editor = this.panel.querySelector(".adm-content-editor") as HTMLElement;
    editor.hidden = false;
    this.contentField("id").value = doc.id;
    this.contentField("topic").value = doc.topic;
    this.contentField("title").value = doc.title;
    this.contentField("body").value = doc.draft_body;
    (this.panel.querySelector(".adm-published-version") as HTMLElement).textContent =
      `Published version: ${doc.published_version} (last updated ${doc.last_updated})`;
  }

  private draftFromEditor(doc: ContentDocument): ContentDraft {
    return {
      topic: this.contentField("topic").value,
      title: this.contentField("title").value,
      body: this.contentField("body").value,
      metadata: doc.metadata,
    };
  }

  private contentField(name: string): HTMLInputElement {
    return this.panel.querySelector(`[name=${name}]`) as HTMLInputElement;
  }

  private requireClient(): AdminClient | null {
    if (!this.session) {
      this.render(); // not signed in -> show login
      return null;
    }
    return this.clientFactory(this.baseUrl, this.session.token);
  }

  /** A 401 means the session token is gone/expired -> bounce back to login. */
  private handleError(error: unknown): void {
    if (error instanceof HttpError && error.status === 401) {
      this.logout();
      this.setStatus("Your session expired — please sign in again.", "error");
      return;
    }
    this.setStatus(messageOf(error), "error");
  }

  private setStatus(message: string, kind: "error" | "ok" | "" = ""): void {
    // Both the login screen and the shell always contain a single .adm-status.
    const status = this.view.querySelector(".adm-status") as HTMLElement;
    status.textContent = message;
    if (kind) {
      status.dataset.kind = kind;
    } else {
      delete status.dataset.kind;
    }
  }
}

function readStoredSession(): Session | null {
  const raw = sessionStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    const { token, username } = JSON.parse(raw) as Session;
    if (token) return { token, username };
  } catch {
    // corrupt value -> treat as signed out
  }
  return null;
}

function storeSession(session: Session): void {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

function clearSession(): void {
  sessionStorage.removeItem(SESSION_KEY);
}

function loginErrorMessage(error: unknown): string {
  if (error instanceof HttpError && error.status === 401) {
    return "Invalid username or password.";
  }
  return messageOf(error);
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
