// Pure rendering helpers: turn admin API data into DOM elements. No network, no
// global state (bar a monotonic id counter for gradient ids) — every function takes
// data and returns a fresh element, which keeps them trivially unit-testable.
// User-controlled text is set via textContent (never innerHTML) so visitor-supplied
// questions/leads can't inject markup. Charts are hand-rolled SVG/CSS — no chart
// library — to keep the bundle tiny and dependency-free, matching the widget.

import type { DeadEnd, Lead, StatsResponse } from "./api";

const SVG_NS = "http://www.w3.org/2000/svg";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

let idSeq = 0;
const nextId = (): number => (idSeq += 1);

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function svg(tag: string, attrs: Record<string, string | number> = {}): SVGElement {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node as SVGElement;
}

function cell(row: HTMLTableRowElement, text: string, header = false): void {
  const c = el(header ? "th" : "td");
  c.textContent = text;
  if (header) c.scope = "col";
  row.appendChild(c);
}

function tableHead(labels: string[]): HTMLTableSectionElement {
  const head = el("thead");
  const row = el("tr");
  for (const label of labels) cell(row, label, true);
  head.appendChild(row);
  return head;
}

// --- formatting -------------------------------------------------------------

const fmtInt = (n: number): string => n.toLocaleString("en-US");
const fmtPct = (frac: number): string => `${Math.round(frac * 100)}%`;
const fmtAvg = (n: number): string => n.toFixed(1).replace(/\.0$/, "");

/** Deterministic, timezone-stable timestamp derived straight from the ISO string. */
function formatTimestamp(raw: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(raw);
  if (!m) return raw;
  const [, year, month, day, hh, mm] = m;
  const date = `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}`;
  return hh ? `${date}, ${hh}:${mm}` : date;
}

// --- KPI cards --------------------------------------------------------------

type Accent = "brand" | "ok" | "warn" | "accent";

function kpiCard(opts: { label: string; value: string; sub: string; accent: Accent }): HTMLElement {
  const card = el("article", "adm-kpi");
  card.dataset.accent = opts.accent;
  card.appendChild(el("p", "adm-kpi-label", opts.label));
  card.appendChild(el("p", "adm-kpi-value", opts.value));
  card.appendChild(el("p", "adm-kpi-sub", opts.sub));
  return card;
}

function chartCard(title: string, subtitle: string, body: Node, className: string): HTMLElement {
  const card = el("section", `adm-card adm-chart ${className}`);
  const head = el("div", "adm-card-head");
  head.appendChild(el("h3", "adm-card-title", title));
  head.appendChild(el("p", "adm-card-sub", subtitle));
  card.appendChild(head);
  const wrap = el("div", "adm-chart-body");
  wrap.appendChild(body);
  card.appendChild(wrap);
  return card;
}

// --- charts -----------------------------------------------------------------

/** An SVG area chart of questions per day, with a point marker per day. */
function volumeChart(perDay: Record<string, number>): HTMLElement {
  const dates = Object.keys(perDay).sort();
  if (dates.length === 0) return el("p", "adm-empty", "No activity recorded yet.");

  const values = dates.map((d) => perDay[d]);
  const total = values.reduce((a, b) => a + b, 0);
  const max = Math.max(...values, 1);
  const W = 320;
  const H = 120;
  const padX = 8;
  const padTop = 12;
  const padBottom = 12;
  const innerW = W - padX * 2;
  const innerH = H - padTop - padBottom;
  const n = values.length;
  const baseline = padTop + innerH;
  const x = (i: number): number => (n === 1 ? W / 2 : padX + (i / (n - 1)) * innerW);
  const y = (v: number): number => padTop + innerH * (1 - v / max);
  const pts = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
  const gradId = `adm-grad-${nextId()}`;

  const root = svg("svg", {
    viewBox: `0 0 ${W} ${H}`,
    class: "adm-area",
    preserveAspectRatio: "none",
    role: "img",
    "aria-label": `Question volume: ${total} questions over ${n} day${n === 1 ? "" : "s"}, peak ${max} in a day.`,
  });

  const defs = svg("defs");
  const grad = svg("linearGradient", { id: gradId, x1: 0, y1: 0, x2: 0, y2: 1 });
  grad.appendChild(svg("stop", { offset: "0%", "stop-color": "var(--adm-primary)", "stop-opacity": "0.32" }));
  grad.appendChild(svg("stop", { offset: "100%", "stop-color": "var(--adm-primary)", "stop-opacity": "0.02" }));
  defs.appendChild(grad);
  root.appendChild(defs);

  root.appendChild(
    svg("line", { x1: padX, y1: baseline, x2: W - padX, y2: baseline, class: "adm-area-axis" }),
  );

  if (n === 1) {
    // A lone point reads better as a single centered column with its value above it.
    const barW = 44;
    const top = y(values[0]);
    root.appendChild(
      svg("rect", {
        x: (x(0) - barW / 2).toFixed(1),
        y: top.toFixed(1),
        width: barW,
        height: Math.max(2, baseline - top).toFixed(1),
        rx: 7,
        class: "adm-area-bar",
      }),
    );
    const label = svg("text", { x: x(0), y: Math.max(10, top - 6), class: "adm-area-bar-label", "text-anchor": "middle" });
    label.textContent = fmtInt(values[0]);
    root.appendChild(label);
  } else {
    root.appendChild(
      svg("path", {
        d: `M ${x(0).toFixed(1)},${baseline} L ${pts.join(" L ")} L ${x(n - 1).toFixed(1)},${baseline} Z`,
        fill: `url(#${gradId})`,
      }),
    );
    root.appendChild(svg("polyline", { points: pts.join(" "), class: "adm-area-line", fill: "none" }));
    values.forEach((v, i) => root.appendChild(svg("circle", { cx: x(i), cy: y(v), r: 2.6, class: "adm-area-dot" })));
  }

  const wrap = el("div", "adm-area-wrap");
  wrap.appendChild(root);
  const labels = el("div", "adm-area-labels");
  labels.appendChild(el("span", undefined, formatTimestamp(dates[0])));
  if (dates.length > 1) labels.appendChild(el("span", undefined, formatTimestamp(dates[dates.length - 1])));
  wrap.appendChild(labels);
  return wrap;
}

/** Horizontal proportional bars for the busiest topics. */
function topicBars(topics: Array<[string, number]>): HTMLElement {
  if (topics.length === 0) return el("p", "adm-empty", "No topics recorded yet.");

  const max = Math.max(...topics.map(([, c]) => c), 1);
  const list = el("div", "adm-bars");
  for (const [topic, count] of topics.slice(0, 8)) {
    const row = el("div", "adm-bar-row");
    row.appendChild(el("span", "adm-bar-label", topic));
    const track = el("div", "adm-bar-track");
    const fill = el("div", "adm-bar-fill");
    fill.style.width = `${Math.max(4, (count / max) * 100)}%`;
    track.appendChild(fill);
    row.appendChild(track);
    row.appendChild(el("span", "adm-bar-value", fmtInt(count)));
    list.appendChild(row);
  }
  return list;
}

/** A donut showing the answered fraction, with a legend. */
function coverageDonut(answered: number, unanswered: number): HTMLElement {
  const total = answered + unanswered;
  const frac = total > 0 ? answered / total : 0;
  const r = 52;
  const cx = 60;
  const cy = 60;
  const circumference = 2 * Math.PI * r;

  const root = svg("svg", {
    viewBox: "0 0 120 120",
    class: "adm-donut",
    role: "img",
    "aria-label": total > 0
      ? `Answer coverage ${Math.round(frac * 100)} percent: ${answered} answered, ${unanswered} unanswered.`
      : "No questions answered yet.",
  });
  root.appendChild(svg("circle", { cx, cy, r, class: "adm-donut-track", fill: "none", "stroke-width": 13 }));
  if (total > 0) {
    root.appendChild(
      svg("circle", {
        cx,
        cy,
        r,
        class: "adm-donut-value",
        fill: "none",
        "stroke-width": 13,
        "stroke-linecap": "round",
        "stroke-dasharray": `${(frac * circumference).toFixed(2)} ${circumference.toFixed(2)}`,
        transform: `rotate(-90 ${cx} ${cy})`,
      }),
    );
  }
  const big = svg("text", { x: cx, y: cy - 3, class: "adm-donut-pct", "text-anchor": "middle", "dominant-baseline": "central" });
  big.textContent = total > 0 ? `${Math.round(frac * 100)}%` : "—";
  root.appendChild(big);
  const cap = svg("text", { x: cx, y: cy + 18, class: "adm-donut-cap", "text-anchor": "middle", "dominant-baseline": "central" });
  cap.textContent = "answered";
  root.appendChild(cap);

  const wrap = el("div", "adm-donut-wrap");
  wrap.appendChild(root);
  const legend = el("div", "adm-donut-legend");
  legend.appendChild(legendItem("adm-dot-ok", `Answered (${fmtInt(answered)})`));
  legend.appendChild(legendItem("adm-dot-warn", `Unanswered (${fmtInt(unanswered)})`));
  wrap.appendChild(legend);
  return wrap;
}

function legendItem(dotClass: string, label: string): HTMLElement {
  const item = el("span", "adm-legend-item");
  item.appendChild(el("span", `adm-legend-dot ${dotClass}`));
  item.appendChild(el("span", undefined, label));
  return item;
}

// --- public sections --------------------------------------------------------

/** The dashboard overview: a KPI row plus the charts grid. */
export function renderStats(stats: StatsResponse): HTMLElement {
  const section = el("section", "adm-stats");

  const answered = stats.answered_count;
  const unanswered = stats.dead_end_count;
  const outcomes = answered + unanswered;
  const totalQuestions = Object.values(stats.questions_per_day).reduce((a, b) => a + b, 0);
  const days = Object.keys(stats.questions_per_day).length;
  const coverage = outcomes > 0 ? answered / outcomes : null;
  const leadRate = totalQuestions > 0 ? stats.lead_count / totalQuestions : 0;
  const avgPerDay = days > 0 ? totalQuestions / days : 0;
  const topTopic = stats.busiest_topics[0];

  const kpis = el("div", "adm-kpis");
  kpis.appendChild(
    kpiCard({
      label: "Total questions",
      value: fmtInt(totalQuestions),
      sub: days > 0 ? `${fmtAvg(avgPerDay)} per day · ${days} day${days === 1 ? "" : "s"}` : "No activity yet",
      accent: "brand",
    }),
  );
  kpis.appendChild(
    kpiCard({
      label: "Answer coverage",
      value: coverage === null ? "—" : fmtPct(coverage),
      sub: outcomes > 0 ? `${fmtInt(answered)} of ${fmtInt(outcomes)} answered` : "Awaiting questions",
      accent: coverage !== null && coverage >= 0.8 ? "ok" : "warn",
    }),
  );
  kpis.appendChild(
    kpiCard({
      label: "Unanswered",
      value: fmtInt(unanswered),
      sub: topTopic ? `Top topic: ${topTopic[0]}` : "No gaps logged",
      accent: unanswered > 0 ? "warn" : "ok",
    }),
  );
  kpis.appendChild(
    kpiCard({
      label: "Leads captured",
      value: fmtInt(stats.lead_count),
      sub: totalQuestions > 0 ? `${fmtPct(leadRate)} lead rate` : "—",
      accent: "accent",
    }),
  );
  section.appendChild(kpis);

  const charts = el("div", "adm-charts");
  charts.appendChild(
    chartCard("Question volume", "Questions handled per day", volumeChart(stats.questions_per_day), "adm-chart-volume"),
  );
  charts.appendChild(
    chartCard("Top topics", "Most-asked subject areas", topicBars(stats.busiest_topics), "adm-chart-topics"),
  );
  charts.appendChild(
    chartCard("Answer coverage", "Answered vs unanswered", coverageDonut(answered, unanswered), "adm-chart-coverage"),
  );
  section.appendChild(charts);

  return section;
}

/** Ranked unanswered-question clusters, each with a frequency bar (US-9). */
export function renderDeadEnds(deadEnds: DeadEnd[]): HTMLElement {
  const section = el("section", "adm-card adm-dead-ends");
  const head = el("div", "adm-card-head");
  const titleRow = el("div", "adm-card-title-row");
  titleRow.appendChild(el("h3", "adm-card-title", "Knowledge gaps"));
  titleRow.appendChild(el("span", "adm-badge", fmtInt(deadEnds.length)));
  head.appendChild(titleRow);
  head.appendChild(
    el("p", "adm-card-sub", "Unanswered questions, ranked by frequency — curate these first to close the gap."),
  );
  section.appendChild(head);

  if (deadEnds.length === 0) {
    section.appendChild(el("p", "adm-empty", "No unanswered questions yet."));
    return section;
  }

  const maxFreq = Math.max(...deadEnds.map((d) => d.frequency), 1);
  const table = el("table", "adm-table");
  table.appendChild(tableHead(["#", "Question", "Frequency"]));
  const body = el("tbody");
  deadEnds.forEach((item, i) => {
    const row = el("tr");
    const rank = el("td", "adm-rank");
    rank.textContent = `#${i + 1}`;
    row.appendChild(rank);
    cell(row, item.question);

    const freq = el("td", "adm-freq-cell");
    const track = el("div", "adm-bar-track adm-bar-track--sm");
    const fill = el("div", "adm-bar-fill");
    fill.style.width = `${Math.max(6, (item.frequency / maxFreq) * 100)}%`;
    track.appendChild(fill);
    freq.appendChild(track);
    freq.appendChild(el("span", "adm-freq-val", fmtInt(item.frequency)));
    row.appendChild(freq);

    body.appendChild(row);
  });
  table.appendChild(body);
  section.appendChild(table);
  return section;
}

/** Captured consented leads, with delivery-status pills. */
export function renderLeads(leads: Lead[]): HTMLElement {
  const section = el("section", "adm-card adm-leads");
  const head = el("div", "adm-card-head");
  const titleRow = el("div", "adm-card-title-row");
  titleRow.appendChild(el("h3", "adm-card-title", "Leads"));
  titleRow.appendChild(el("span", "adm-badge", fmtInt(leads.length)));
  head.appendChild(titleRow);
  head.appendChild(el("p", "adm-card-sub", "Consented admissions enquiries captured by the assistant."));
  section.appendChild(head);

  if (leads.length === 0) {
    section.appendChild(el("p", "adm-empty", "No leads captured yet."));
    return section;
  }

  const table = el("table", "adm-table");
  table.appendChild(tableHead(["Name", "Contact", "Program", "From question", "Captured", "Delivery"]));
  const body = el("tbody");
  for (const lead of leads) {
    const row = el("tr");
    cell(row, lead.name);

    const contact = el("td", "adm-contact");
    contact.appendChild(el("div", "adm-contact-email", lead.email));
    if (lead.phone) contact.appendChild(el("div", "adm-contact-phone", lead.phone));
    row.appendChild(contact);

    const program = el("td");
    if (lead.program) program.appendChild(el("span", "adm-tag", lead.program));
    else program.textContent = "—";
    row.appendChild(program);

    cell(row, lead.dead_end_question ?? "—");
    cell(row, formatTimestamp(lead.created_at));

    const delivery = el("td");
    delivery.appendChild(deliveryPill(lead.delivery_status));
    row.appendChild(delivery);

    body.appendChild(row);
  }
  table.appendChild(body);
  section.appendChild(table);
  return section;
}

function deliveryPill(status: string): HTMLElement {
  const pill = el("span", "adm-pill", status);
  pill.dataset.status = deliveryKind(status);
  return pill;
}

function deliveryKind(status: string): "ok" | "warn" | "danger" | "neutral" {
  const s = status.toLowerCase();
  if (s.includes("deliver") || s === "sent") return "ok";
  if (s.includes("fail") || s.includes("error")) return "danger";
  if (s.includes("pend") || s.includes("queue") || s.includes("retry")) return "warn";
  return "neutral";
}
