import { defineConfig, devices } from "@playwright/test"

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/chat.spec.ts",
  workers: 1,
  use: { ...devices["Desktop Chrome"], baseURL: "http://127.0.0.1:3000" },
  webServer: [
    {
      command: "uv run --directory ../api uvicorn app.main:app --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/agents",
      reuseExistingServer: false,
      env: {
        GATEWAY_MOCK: "1",
        FORCE_LOCAL: "1",
        STREAM_PACE_MS: "800",
        DATABASE_URL: "sqlite:////tmp/atelier-chat-e2e.db",
        PROJECTS_DIR: "/tmp/atelier-chat-projects",
      },
    },
    {
      command: "NEXT_PUBLIC_USE_MOCKS=false NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 pnpm dev --hostname 127.0.0.1 --port 3000",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: false,
    },
  ],
})
