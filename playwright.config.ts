import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command:
      "pnpm --filter @b2-speaking/web dev --hostname 127.0.0.1 --port 3100",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      NEXT_DIST_DIR: ".next-e2e",
      NEXT_PUBLIC_API_URL: "http://localhost:8000",
      NEXT_PUBLIC_PRACTICE_DURATION_MS: "1000",
      NEXT_PUBLIC_PART1_ANSWER_DURATION_MS: "200",
      NEXT_PUBLIC_PART3_REFERENCE_MS: "140",
      NEXT_PUBLIC_PART3_DISCUSSION_MS: "260",
      NEXT_PUBLIC_PART3_DECISION_MS: "180",
      NEXT_PUBLIC_POLL_INTERVAL_MS: "20",
      NEXT_PUBLIC_MICROPHONE_TEST_DURATION_MS: "600",
    },
  },
  projects: process.env.CI
    ? [{ name: "Chromium CI", use: { ...devices["Desktop Chrome"] } }]
    : [
        {
          name: "Google Chrome desktop",
          use: { ...devices["Desktop Chrome"], channel: "chrome" },
        },
        {
          name: "Microsoft Edge desktop",
          use: { ...devices["Desktop Edge"], channel: "msedge" },
        },
      ],
});
