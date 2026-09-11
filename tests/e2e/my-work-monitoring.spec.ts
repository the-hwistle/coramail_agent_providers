import crypto from "node:crypto";
import { expect, type Page, test } from "@playwright/test";

const ASSIGNEE_USERNAME = process.env.CORAMAIL_E2E_ASSIGNEE_USERNAME ?? "m.kim@dawonict.co.kr";
const AUTH_USERNAME = process.env.CORAMAIL_AUTH_USERNAME ?? "admin";
const AUTH_PASSWORD = process.env.CORAMAIL_AUTH_PASSWORD ?? "coramail";
const AUTH_COOKIE_NAME = process.env.CORAMAIL_AUTH_COOKIE_NAME ?? "coramail_session";
const AUTH_SECRET =
  process.env.CORAMAIL_AUTH_SECRET ??
  crypto.createHash("sha256").update(`${AUTH_USERNAME}:${AUTH_PASSWORD}:coramail-auth`).digest("hex");

function authCookieValue(username: string): string {
  const expiresAt = Math.floor(Date.now() / 1000) + 8 * 60 * 60;
  const payload = `${username}:${expiresAt}`;
  const signature = crypto.createHmac("sha256", AUTH_SECRET).update(payload).digest("hex");
  return Buffer.from(`${payload}:${signature}`, "utf8").toString("base64url");
}

function isExpectedConsoleError(text: string): boolean {
  if (
    text.startsWith("Blocked script execution in 'about:") &&
    text.includes("frame is sandboxed") &&
    text.includes("allow-scripts")
  ) {
    return true;
  }

  // The smoke environment intentionally has no PostgreSQL/Gmail backing data.
  // Background UI requests can therefore return an expected authorization/degraded response
  // while the page itself still renders its supported empty state.
  return text === "Failed to load resource: the server responded with a status of 403 (Forbidden)";
}

async function loginAsAssignee(page: Page) {
  await page.context().addCookies([
    {
      name: AUTH_COOKIE_NAME,
      value: authCookieValue(ASSIGNEE_USERNAME),
      url: process.env.CORAMAIL_E2E_BASE_URL ?? "http://127.0.0.1:8000",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
  await page.goto("/");
  await expect(page.locator(".current-user")).toBeVisible();
}

test.describe("My Work and Monitoring smoke", () => {
  test("assignee My Work renders and drawer works when data exists", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error" && !isExpectedConsoleError(message.text())) {
        consoleErrors.push(message.text());
      }
    });

    await loginAsAssignee(page);
    await page.getByRole("button", { name: "My Work 탭 열기" }).click();
    await expect(page.locator("#main-panel")).toContainText("현재 할당 업무");
    await expect(page.locator("#main-panel")).not.toContainText("Routing Overview");

    const openButtons = page.locator("#assigneeDetailPreview [data-assignee-detail-open]");
    const emptyState = page.locator("#main-panel").getByText("현재 조건에 맞는 업무 메일이 없습니다.");
    await expect(openButtons.first().or(emptyState).first()).toBeVisible();
    if ((await openButtons.count()) === 0) {
      await expect(emptyState).toBeVisible();
      expect(consoleErrors).toEqual([]);
      return;
    }

    const drawer = page.locator("#assigneeEmailDetailDrawer");
    await expect(drawer).toBeHidden();
    await openButtons.first().click();
    await expect(drawer).toBeVisible();
    await expect(drawer.locator("[data-assignee-detail-close]")).toBeVisible();
    await expect(drawer).toContainText("업무 완료");
    await page.screenshot({ path: "test-results/my-work-drawer-open.png", fullPage: false });

    await drawer.locator("[data-assignee-detail-close]").click();
    await expect(drawer).toBeHidden();

    await openButtons.first().click();
    await expect(drawer).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();

    await openButtons.first().click();
    await expect(drawer).toBeVisible();
    await page.mouse.click(24, 80);
    await expect(drawer).toBeHidden();

    expect(consoleErrors).toEqual([]);
  });

  test("Monitoring renders and inspector works when data exists", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error" && !isExpectedConsoleError(message.text())) {
        consoleErrors.push(message.text());
      }
    });

    await loginAsAssignee(page);
    await page.getByRole("button", { name: "Monitoring 탭 열기" }).click();
    await expect(page.locator("#main-panel")).toContainText("운영 상태 검색");
    await expect(page.locator("body")).not.toContainText("최서연");

    const rows = page.locator(".ops-row");
    if ((await rows.count()) === 0) {
      await expect(page.locator("#main-panel")).toContainText("표시할 운영 상태가 없습니다.");
      expect(consoleErrors).toEqual([]);
      return;
    }

    await expect(rows.first()).toBeVisible();
    await expect(page.locator(".ops-stage-menu").first()).toContainText("완료");

    const inspector = page.locator("#opsInspector");
    await expect(inspector).toBeHidden();
    await page.locator("[data-ops-inspector-open]").first().click();
    await expect(inspector).toBeVisible();
    await expect(inspector.locator("[data-ops-inspector-close]")).toBeVisible();
    await expect(inspector).toContainText("업무 완료");
    await page.screenshot({ path: "test-results/monitoring-inspector-open.png", fullPage: false });

    await inspector.locator("[data-ops-inspector-close]").click();
    await expect(inspector).toBeHidden();

    await page.locator("[data-ops-inspector-open]").first().click();
    await expect(inspector).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(inspector).toBeHidden();

    await page.locator("[data-ops-inspector-open]").first().click();
    await expect(inspector).toBeVisible();
    await page.mouse.click(24, 80);
    await expect(inspector).toBeHidden();

    expect(consoleErrors).toEqual([]);
  });

  test("Monitoring column widths resize from header handles", async ({ page }) => {
    test.skip(test.info().project.name === "mobile-chromium", "Desktop table drag behavior is covered separately from mobile horizontal scrolling.");

    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error" && !isExpectedConsoleError(message.text())) {
        consoleErrors.push(message.text());
      }
    });

    await loginAsAssignee(page);
    await page.getByRole("button", { name: "Monitoring 탭 열기" }).click();
    await expect(page.locator("#main-panel")).toContainText("운영 상태 검색");

    const subjectCol = page.locator("col[data-monitoring-column='subject']");
    const senderCol = page.locator("col[data-monitoring-column='sender']");
    const subjectHandle = page.locator("[data-monitoring-column-resizer='subject']");
    const forwardingHandle = page.locator("[data-monitoring-column-resizer='forwarding']");
    await expect(subjectHandle).toBeVisible();
    await expect(forwardingHandle).toHaveCount(0);
    const before = await subjectCol.evaluate((node) => node.getBoundingClientRect().width);
    const senderBefore = await senderCol.evaluate((node) => node.getBoundingClientRect().width);
    const tableRightBefore = await page.locator(".ops-table").evaluate((node) => node.getBoundingClientRect().right);
    const box = await subjectHandle.boundingBox();
    expect(box).not.toBeNull();
    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await page.mouse.down();
    await page.mouse.move(box!.x + box!.width / 2 - 80, box!.y + box!.height / 2);
    await page.mouse.up();

    const after = await subjectCol.evaluate((node) => node.getBoundingClientRect().width);
    const senderAfter = await senderCol.evaluate((node) => node.getBoundingClientRect().width);
    const tableRightAfter = await page.locator(".ops-table").evaluate((node) => node.getBoundingClientRect().right);
    expect(after).toBeLessThan(before - 50);
    expect(senderAfter).toBeGreaterThan(senderBefore + 50);
    expect(Math.abs(tableRightAfter - tableRightBefore)).toBeLessThan(2);
    await expect.poll(async () => {
      return page.evaluate(() => {
        const raw = window.localStorage.getItem("coramail.monitoring.columnWidths.v1");
        return raw ? JSON.parse(raw).subject : 0;
      });
    }).toBeLessThan(before - 50);
    expect(consoleErrors).toEqual([]);
  });

  test("Monitoring columns reorder by long-pressing headers while status stays fixed", async ({ page }) => {
    test.skip(test.info().project.name === "mobile-chromium", "Desktop table drag behavior is covered separately from mobile horizontal scrolling.");

    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error" && !isExpectedConsoleError(message.text())) {
        consoleErrors.push(message.text());
      }
    });

    await loginAsAssignee(page);
    await page.evaluate(() => window.localStorage.removeItem("coramail.monitoring.columnOrder.v1"));
    await page.getByRole("button", { name: "Monitoring 탭 열기" }).click();
    await expect(page.locator("#main-panel")).toContainText("운영 상태 검색");

    const subjectHeader = page.locator("th[data-monitoring-column='subject']");
    const assigneeHeader = page.locator("th[data-monitoring-column='assignee']");
    await expect(subjectHeader).toBeVisible();
    await expect(assigneeHeader).toBeVisible();

    const subjectBox = await subjectHeader.boundingBox();
    const assigneeBox = await assigneeHeader.boundingBox();
    expect(subjectBox).not.toBeNull();
    expect(assigneeBox).not.toBeNull();
    await page.mouse.move(subjectBox!.x + subjectBox!.width / 2, subjectBox!.y + subjectBox!.height / 2);
    await page.mouse.down();
    await page.waitForTimeout(380);
    await page.mouse.move(assigneeBox!.x + assigneeBox!.width / 2, assigneeBox!.y + assigneeBox!.height / 2);
    await page.mouse.up();

    const headerOrder = await page.locator("th[data-monitoring-column]").evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute("data-monitoring-column")),
    );
    expect(headerOrder.slice(0, 5)).toEqual(["health", "sender", "business", "assignee", "subject"]);

    const colOrder = await page.locator("col[data-monitoring-column]").evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute("data-monitoring-column")),
    );
    expect(colOrder.slice(0, 5)).toEqual(["health", "sender", "business", "assignee", "subject"]);

    const firstDataRow = page.locator("#opsRows tr[data-email-uid]").first();
    if ((await firstDataRow.count()) > 0) {
      const cellOrder = await firstDataRow.locator("td[data-monitoring-column]").evaluateAll((nodes) =>
        nodes.map((node) => node.getAttribute("data-monitoring-column")),
      );
      expect(cellOrder.slice(0, 5)).toEqual(["health", "sender", "business", "assignee", "subject"]);
    }

    await expect.poll(async () => {
      return page.evaluate(() => {
        const raw = window.localStorage.getItem("coramail.monitoring.columnOrder.v1");
        return raw ? JSON.parse(raw).slice(0, 5) : [];
      });
    }).toEqual(["health", "sender", "business", "assignee", "subject"]);
    expect(consoleErrors).toEqual([]);
  });

  test("Monitoring visible terminal column touches the table frame", async ({ page }) => {
    test.skip(test.info().project.name === "mobile-chromium", "Desktop table frame geometry is covered here.");

    await loginAsAssignee(page);
    await page.getByRole("button", { name: "Monitoring 탭 열기" }).click();
    await expect(page.locator("#main-panel")).toContainText("운영 상태 검색");

    await page.locator(".ops-column-menu > summary").click();
    for (const key of ["business", "assignee", "received", "attachment", "summary", "classification", "decision", "routing", "forwarding"]) {
      await page.locator(`[data-monitoring-column-toggle='${key}']`).uncheck();
    }

    const tableRight = await page.locator(".ops-table").evaluate((node) => node.getBoundingClientRect().right);
    const frameRight = await page.locator(".ops-table-wrap").evaluate((node) => node.getBoundingClientRect().right);
    expect(Math.abs(tableRight - frameRight)).toBeLessThan(2);
  });
});
