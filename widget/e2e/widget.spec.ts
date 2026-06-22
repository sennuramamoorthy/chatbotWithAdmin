import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Browser E2E for the embeddable widget (US-10). These drive the *real* esbuild
// bundle (dist/widget.js) mounted via the single <script> snippet on the demo
// host page, against the in-memory demo backend started by playwright.config.ts.
//
// Requirement coverage:
//   TC-035 / AC-10.1  single-snippet embed, collapsed bubble, opens on click,
//                     host page not hijacked
//   AC-10.2           responsive on mobile + desktop viewports
//   TC-001            in-scope question streams the grounded fee answer
//   TC-036 / NFR-7    no serious/critical axe violations
//   TC-029 / AC-10.3  backend down -> static Admissions contact, not a broken state
//
// The widget renders inside an open shadow root; Playwright CSS locators pierce
// open shadow DOM automatically, so `.tk-*` selectors resolve normally.

const BUBBLE = ".tk-bubble";
const PANEL = ".tk-panel";
const MESSAGES = ".tk-messages";
const INPUT = ".tk-input";
const SEND = ".tk-send";

/** Open the widget by clicking the collapsed bubble and wait for the dialog. */
async function openWidget(page: Page) {
  const bubble = page.locator(BUBBLE);
  await expect(bubble).toBeVisible();
  await bubble.click();
  const panel = page.getByRole("dialog");
  await expect(panel).toBeVisible();
  return panel;
}

test.describe("Embed & layout (TC-035 / AC-10.1)", () => {
  test("loads collapsed, opens the dialog on click, and does not hijack the host page", async ({
    page,
  }) => {
    await page.goto("/");

    // The host page's own content is intact — the widget did not take over.
    await expect(page.getByRole("heading", { name: "Takshashila University" })).toBeVisible();

    // Collapsed bubble present and labelled; panel hidden until opened.
    const bubble = page.locator(BUBBLE);
    await expect(bubble).toBeVisible();
    await expect(bubble).toHaveAttribute("aria-label", /open chat/i);
    await expect(bubble).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator(PANEL)).toBeHidden();

    // Clicking opens the panel as a dialog and flips aria-expanded.
    await bubble.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(bubble).toHaveAttribute("aria-expanded", "true");

    // Host document still owns the page (single root <h1>, body not replaced).
    await expect(page.locator("body > h1")).toHaveText("Takshashila University");
  });

  test("is usable on mobile and desktop viewports (AC-10.2)", async ({ page }) => {
    // Mobile viewport: bubble visible, panel opens and is usable.
    await page.setViewportSize({ width: 375, height: 700 });
    await page.goto("/");
    await expect(page.locator(BUBBLE)).toBeVisible();
    let panel = await openWidget(page);
    await expect(panel.locator(INPUT)).toBeVisible();
    await expect(panel.locator(INPUT)).toBeEditable();
    // Panel must fit within the mobile viewport (CSS caps it at 100vw - 40px).
    const mobileBox = await panel.boundingBox();
    expect(mobileBox).not.toBeNull();
    expect(mobileBox!.width).toBeLessThanOrEqual(375);

    // Desktop viewport: same affordances.
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await expect(page.locator(BUBBLE)).toBeVisible();
    panel = await openWidget(page);
    await expect(panel.locator(INPUT)).toBeVisible();
    await expect(panel.locator(SEND)).toBeVisible();
  });
});

test.describe("Streaming answer (TC-001)", () => {
  test('answers "What is the B.Tech CSE fee?" with the grounded fee, streamed', async ({
    page,
  }) => {
    await page.goto("/");
    const panel = await openWidget(page);

    await panel.locator(INPUT).fill("What is the B.Tech CSE fee?");
    await panel.locator(SEND).click();

    // The visitor's message is echoed, and the streamed bot answer carries the
    // KB fact. Assert on the live log text containing the grounded fee figure.
    const messages = panel.locator(MESSAGES);
    await expect(messages).toContainText("What is the B.Tech CSE fee?");
    await expect(messages.locator(".tk-msg-bot")).toContainText("1,50,000", {
      timeout: 15_000,
    });
  });
});

test.describe("Accessibility (TC-036 / NFR-7)", () => {
  test("the open widget has no serious or critical axe violations", async ({ page }) => {
    await page.goto("/");
    await openWidget(page);

    // Scan the whole page (host + widget shadow DOM). axe-core pierces shadow DOM.
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    const blocking = results.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );

    // Surface a readable summary if anything fails.
    const summary = blocking
      .map((v) => `${v.id} (${v.impact}): ${v.help} [${v.nodes.length} node(s)]`)
      .join("\n");
    expect(blocking, `Serious/critical a11y violations:\n${summary}`).toEqual([]);
  });
});

test.describe("Soft-fail when backend is down (TC-029 / AC-10.3)", () => {
  test("shows the static Admissions contact instead of a broken state", async ({ page }) => {
    // This fixture page embeds the widget pointed at a dead backend port, so the
    // chat fetch fails and the widget must degrade to static contact info.
    await page.goto("/dead-backend.html");

    const panel = await openWidget(page);
    await panel.locator(INPUT).fill("What is the B.Tech CSE fee?");
    await panel.locator(SEND).click();

    const messages = panel.locator(MESSAGES);
    // A user-friendly unavailable message, not a blank/broken panel.
    await expect(messages).toContainText(/unavailable/i, { timeout: 15_000 });
    // The static Admissions contact is surfaced (email from the embed snippet).
    await expect(messages.locator(".tk-contact")).toContainText(
      "admissions@takshashila.example",
    );
    // And the panel is still a healthy, interactive dialog.
    await expect(panel).toBeVisible();
    await expect(panel.locator(INPUT)).toBeEditable();
  });
});
