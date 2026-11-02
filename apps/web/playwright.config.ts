import { defineConfig } from "@playwright/test";

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
    { name: "mobile-375", use: { browserName: "chromium", viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true } },
    { name: "tablet-768", use: { browserName: "chromium", viewport: { width: 768, height: 1024 }, hasTouch: true } },
    { name: "desktop-1024", use: { browserName: "chromium", viewport: { width: 1024, height: 768 } } },
    { name: "desktop-1440", use: { browserName: "chromium", viewport: { width: 1440, height: 900 } } },
  ],
});

