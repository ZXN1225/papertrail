import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: "http://127.0.0.1:3001", trace: "retain-on-failure" },
  projects: [375, 768, 1440].map((width) => ({
    name: `chromium-${width}`,
    use: { browserName: "chromium", viewport: { width, height: 1000 } },
  })),
  webServer: [
    {
      command:
        "uv run --directory ../backend --frozen python -m tools.serve_e2e",
      url: "http://127.0.0.1:8001/api/v1/health/ready",
      reuseExistingServer: false,
      timeout: 30000,
    },
    {
      command: "pnpm start --port 3001",
      url: "http://127.0.0.1:3001",
      env: { API_BASE_URL: "http://127.0.0.1:8001" },
      reuseExistingServer: false,
      timeout: 60000,
    },
  ],
});
