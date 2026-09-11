import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.CORAMAIL_E2E_BASE_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  webServer: process.env.CORAMAIL_E2E_BASE_URL
    ? undefined
    : {
        command: "uv run uvicorn app.server:app --host 127.0.0.1 --port 8000",
        url: `${baseURL}/api/health`,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        env: {
          CORAMAIL_DEMO_MODE: "true",
          CORAMAIL_AUTH_ENABLED: "true",
          CORAMAIL_AUTH_USERNAME: process.env.CORAMAIL_AUTH_USERNAME ?? "admin",
          CORAMAIL_AUTH_PASSWORD: process.env.CORAMAIL_AUTH_PASSWORD ?? "coramail",
        },
      },
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  reporter: [["list"]],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 960 } },
    },
    {
      name: "mobile-chromium",
      use: { ...devices["Pixel 7"], viewport: { width: 412, height: 915 } },
    },
  ],
});
