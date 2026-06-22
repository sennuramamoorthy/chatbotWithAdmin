import { describe, expect, it } from "vitest";

import type { DeadEnd, Lead, StatsResponse } from "../src/api";
import { renderDeadEnds, renderLeads, renderStats } from "../src/render";

const STATS: StatsResponse = {
  questions_per_day: { "2026-06-14": 5, "2026-06-15": 8 },
  busiest_topics: [
    ["fees", 12],
    ["hostel", 5],
  ],
  lead_count: 4,
  answered_count: 9,
  dead_end_count: 4,
};

describe("renderStats KPIs", () => {
  it("renders the four KPI cards with derived values", () => {
    const el = renderStats(STATS);
    const kpis = el.querySelectorAll(".adm-kpis .adm-kpi");
    expect(kpis.length).toBe(4);

    const values = Array.from(el.querySelectorAll(".adm-kpi-value")).map((n) => n.textContent);
    expect(values).toContain("13"); // total questions = 5 + 8
    expect(values).toContain("69%"); // coverage = 9 / (9 + 4)
    expect(values).toContain("4"); // leads captured (and also unanswered)
  });

  it("flags low coverage with a warning accent and high coverage with ok", () => {
    const low = renderStats({ ...STATS, answered_count: 1, dead_end_count: 9 });
    const cov = (s: HTMLElement) =>
      Array.from(s.querySelectorAll<HTMLElement>(".adm-kpi")).find((c) =>
        c.textContent?.includes("Answer coverage"),
      );
    expect(cov(low)?.dataset.accent).toBe("warn");
    const high = renderStats({ ...STATS, answered_count: 9, dead_end_count: 1 });
    expect(cov(high)?.dataset.accent).toBe("ok");
  });

  it("shows an em dash for coverage when there are no outcomes yet", () => {
    const el = renderStats({
      questions_per_day: {},
      busiest_topics: [],
      lead_count: 0,
      answered_count: 0,
      dead_end_count: 0,
    });
    const values = Array.from(el.querySelectorAll(".adm-kpi-value")).map((n) => n.textContent);
    expect(values).toContain("—");
  });
});

describe("renderStats charts", () => {
  it("draws an SVG volume area with one point per day and a coverage donut", () => {
    const el = renderStats(STATS);
    expect(el.querySelector(".adm-chart-volume svg")).not.toBeNull();
    expect(el.querySelectorAll(".adm-chart-volume .adm-area-dot").length).toBe(2);
    const donut = el.querySelector(".adm-chart-coverage svg");
    expect(donut).not.toBeNull();
    expect(donut?.getAttribute("aria-label")).toMatch(/69 percent/);
  });

  it("renders a proportional bar per busiest topic", () => {
    const el = renderStats(STATS);
    const bars = el.querySelectorAll(".adm-chart-topics .adm-bar-row");
    expect(bars.length).toBe(2);
    expect(el.querySelector(".adm-chart-topics")?.textContent).toContain("fees");
    // The biggest topic fills the track fully; the smaller one is narrower.
    const fills = el.querySelectorAll<HTMLElement>(".adm-chart-topics .adm-bar-fill");
    expect(parseFloat(fills[0].style.width)).toBeGreaterThan(parseFloat(fills[1].style.width));
  });

  it("shows empty states for charts when there is no data", () => {
    const el = renderStats({
      questions_per_day: {},
      busiest_topics: [],
      lead_count: 0,
      answered_count: 0,
      dead_end_count: 0,
    });
    expect(el.querySelector(".adm-chart-volume .adm-empty")).not.toBeNull();
    expect(el.querySelector(".adm-chart-topics .adm-empty")).not.toBeNull();
  });
});

describe("renderDeadEnds", () => {
  it("renders a ranked row per question with a frequency bar", () => {
    const deadEnds: DeadEnd[] = [
      { question: "What is the hostel fee?", frequency: 8 },
      { question: "Is there a sports quota?", frequency: 2 },
    ];
    const el = renderDeadEnds(deadEnds);
    expect(el.querySelectorAll("tbody tr").length).toBe(2);
    expect(el.querySelector(".adm-badge")?.textContent).toBe("2"); // gap count
    expect(el.textContent).toContain("What is the hostel fee?");
    expect(el.querySelector(".adm-rank")?.textContent).toBe("#1");
    const fills = el.querySelectorAll<HTMLElement>(".adm-bar-fill");
    expect(parseFloat(fills[0].style.width)).toBeGreaterThan(parseFloat(fills[1].style.width));
  });

  it("escapes question text via textContent (no HTML injection)", () => {
    const el = renderDeadEnds([{ question: "<img src=x onerror=alert(1)>", frequency: 1 }]);
    expect(el.querySelector("img")).toBeNull();
    expect(el.textContent).toContain("<img src=x onerror=alert(1)>");
  });

  it("shows an empty state when there are no dead-ends", () => {
    const el = renderDeadEnds([]);
    expect(el.querySelector("table")).toBeNull();
    expect(el.querySelector(".adm-empty")?.textContent).toMatch(/no unanswered/i);
  });
});

describe("renderLeads", () => {
  const lead: Lead = {
    id: "lead-1",
    name: "Asha",
    email: "a@b.co",
    phone: "9876543210",
    program: "B.Tech CSE",
    message: "Please call",
    dead_end_question: "scholarship?",
    created_at: "2026-06-15T10:00:00Z",
    delivery_status: "delivered",
  };

  it("renders one row per lead with a delivery-status pill", () => {
    const el = renderLeads([lead]);
    expect(el.textContent).toContain("Asha");
    expect(el.textContent).toContain("a@b.co");
    expect(el.textContent).toContain("scholarship?");
    const pill = el.querySelector<HTMLElement>(".adm-pill");
    expect(pill?.textContent).toBe("delivered");
    expect(pill?.dataset.status).toBe("ok");
  });

  it("maps pending and failed deliveries to warn and danger pills", () => {
    expect(
      renderLeads([{ ...lead, delivery_status: "pending" }]).querySelector<HTMLElement>(".adm-pill")
        ?.dataset.status,
    ).toBe("warn");
    expect(
      renderLeads([{ ...lead, delivery_status: "failed" }]).querySelector<HTMLElement>(".adm-pill")
        ?.dataset.status,
    ).toBe("danger");
  });

  it("formats the captured timestamp and renders a program tag", () => {
    const el = renderLeads([lead]);
    expect(el.textContent).toContain("15 Jun 2026");
    expect(el.querySelector(".adm-tag")?.textContent).toBe("B.Tech CSE");
  });

  it("shows a non-ISO timestamp verbatim", () => {
    const el = renderLeads([{ ...lead, created_at: "just now" }]);
    expect(el.textContent).toContain("just now");
  });

  it("renders a dash when there is no originating dead-end question", () => {
    const el = renderLeads([{ ...lead, dead_end_question: null }]);
    expect(el.textContent).toContain("—");
  });

  it("renders a dash instead of a program tag when there is no program", () => {
    const el = renderLeads([{ ...lead, program: "" }]);
    expect(el.querySelector(".adm-tag")).toBeNull();
    expect(el.textContent).toContain("—");
  });

  it("falls back to a neutral pill for an unrecognised delivery status", () => {
    const el = renderLeads([{ ...lead, delivery_status: "archived" }]);
    expect(el.querySelector<HTMLElement>(".adm-pill")?.dataset.status).toBe("neutral");
  });

  it("shows an empty state when there are no leads", () => {
    const el = renderLeads([]);
    expect(el.querySelector("table")).toBeNull();
    expect(el.querySelector(".adm-empty")?.textContent).toMatch(/no leads/i);
  });
});
