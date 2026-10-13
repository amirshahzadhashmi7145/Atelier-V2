import { defineConfig, devices } from "@playwright/test"

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  use: { ...devices["Desktop Chrome"], baseURL: "http://127.0.0.1:3000" },
  testIgnore: "**/chat.spec.ts",
  webServer: {
    command: "NEXT_PUBLIC_USE_MOCKS=true pnpm dev --hostname 127.0.0.1 --port 3000",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: false,
  },
})
