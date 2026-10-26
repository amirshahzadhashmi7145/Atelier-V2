import { defineConfig, devices } from "@playwright/test"

const apiPort = process.env.E2E_API_PORT || "8000"
const webPort = process.env.E2E_WEB_PORT || "3000"

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/chat.spec.ts",
  workers: 1,
  // These drive a live run with streamed output on a timer, so a single transient
  // miss (slow CI, a poll landing a beat late) should retry rather than fail the
  // suite. Mirrors the backend's pytest-rerunfailures.
  retries: process.env.CI ? 2 : 0,
  use: { ...devices["Desktop Chrome"], baseURL: `http://127.0.0.1:${webPort}` },
  webServer: [
    {
      command: `uv run --directory ../api uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      url: `http://127.0.0.1:${apiPort}/agents`,
      reuseExistingServer: process.env.E2E_REUSE === "1",
      env: {
        GATEWAY_MOCK: "1",
        FORCE_LOCAL: "1",
        STREAM_PACE_MS: "800",
        DATABASE_URL: "sqlite:////tmp/atelier-chat-e2e.db",
        PROJECTS_DIR: "/tmp/atelier-chat-projects",
      },
    },
    {
      command: `NEXT_PUBLIC_USE_MOCKS=false NEXT_PUBLIC_API_URL=http://127.0.0.1:${apiPort} pnpm dev --hostname 127.0.0.1 --port ${webPort}`,
      url: `http://127.0.0.1:${webPort}`,
      reuseExistingServer: process.env.E2E_REUSE === "1",
    },
  ],
})
