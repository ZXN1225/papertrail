import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure" },
  projects: [375, 768, 1440].map((width) => ({
    name: `chromium-${width}`,
    use: { browserName: "chromium", viewport: { width, height: 1000 } },
  })),
  webServer: [
    {
      command:
        "uv run --directory ../backend --frozen uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/api/v1/health/ready",
      reuseExistingServer: !process.env.CI,
      timeout: 30000,
    },
    {
      command: "pnpm start",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 60000,
    },
  ],
});
