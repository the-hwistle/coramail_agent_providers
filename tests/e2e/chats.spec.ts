import { expect, type Page, test } from "@playwright/test";

const AUTH_USERNAME = process.env.CORAMAIL_AUTH_USERNAME ?? "admin";
const AUTH_PASSWORD = process.env.CORAMAIL_AUTH_PASSWORD ?? "coramail";

async function login(page: Page) {
  const baseUrl = process.env.CORAMAIL_E2E_BASE_URL ?? "http://127.0.0.1:8000";
  const response = await page.request.post("/login?next=/", {
    headers: { Origin: new URL(baseUrl).origin },
    form: { username: AUTH_USERNAME, password: AUTH_PASSWORD },
  });
  expect(response.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.locator(".current-user")).toBeVisible();
}

test("Chats submits click and Korean IME Enter queries through the React shell", async ({ page }) => {
  test.setTimeout(60_000);
  await login(page);
  await page.request.post("/ui/display-mode/toggle?display_mode=demo");
  await page.reload();
  await page.getByRole("button", { name: "Chats 탭 열기" }).click();

  const composer = page.locator("[data-chat-composer]");
  const input = composer.locator("[name='q']");
  const firstResponse = page.waitForResponse((response) => response.url().includes("/ui/chats-results"));
  await input.fill("가장 최신 메일이 뭐야");
  await composer.getByRole("button", { name: "전송" }).click();
  await expect(input).toHaveValue("");
  await expect(page.locator("#chat-results-body")).toContainText("답변 생성 중");
  await expect((await firstResponse).ok()).toBeTruthy();
  await expect(page.locator("#chat-results-body")).toContainText("가장 최신 메일이 뭐야");
  const firstAnswerBox = await page.locator(".chat-answer-bubble").first().boundingBox();
  expect(firstAnswerBox?.height).toBeLessThan(300);

  const secondResponse = page.waitForResponse((response) => response.url().includes("/ui/chats-results"));
  await input.fill("그 견적서의 납기와 총액");
  await input.dispatchEvent("keydown", { key: "Enter", code: "Enter", keyCode: 229, isComposing: true });
  await input.dispatchEvent("compositionend", { data: "액" });
  await expect((await secondResponse).ok()).toBeTruthy();
  await expect(page.locator("#chat-results-body")).toContainText("그 견적서의 납기와 총액");
  await expect(page.locator("#chat-results-body")).toContainText("가장 최신 메일이 뭐야");
  await expect(composer.locator("#chatSessionInput")).toHaveValue(/^[0-9a-f]{32}$/);
  await expect(composer.locator("#chatHistoryInput")).not.toHaveValue("[]");
  await page.screenshot({ path: "test-results/chats-current.png", fullPage: false });
});

test("Chats retry appends the same query in the existing session", async ({ page }) => {
  test.setTimeout(60_000);
  await login(page);
  await page.request.post("/ui/display-mode/toggle?display_mode=demo");
  await page.reload();
  await page.getByRole("button", { name: "Chats 탭 열기" }).click();

  const composer = page.locator("[data-chat-composer]");
  const response = page.waitForResponse((item) => item.url().includes("/ui/chats-results"));
  await composer.locator("[name='q']").fill("가장 최신 메일이 뭐야");
  await composer.getByRole("button", { name: "전송" }).click();
  await expect((await response).ok()).toBeTruthy();
  await expect(page.locator(".chat-message-user")).toHaveCount(1);

  const retryResponse = page.waitForResponse((item) => item.url().includes("/ui/chats-results"));
  await page.getByRole("button", { name: "같은 질문 다시 요청" }).click();
  await expect(page.locator("#chat-results-body")).toContainText("답변 생성 중");
  await expect((await retryResponse).ok()).toBeTruthy();
  await expect(page.locator(".chat-message-user")).toHaveCount(2);
  await expect(page.locator(".chat-message-user").last()).toContainText("가장 최신 메일이 뭐야");
});
