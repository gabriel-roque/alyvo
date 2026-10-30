import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  fullyParallel: true,
  workers: process.env.E2E_EXTERNAL ? 1 : undefined,
  use: { baseURL: process.env.WEB_URL ?? "http://127.0.0.1:3100", trace: "on-first-retry" },
  webServer: process.env.E2E_EXTERNAL ? undefined : {
    command: "npm run build && npm run start -- --hostname 127.0.0.1 --port 3100",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: true,
    timeout: 120_000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});

