import "@testing-library/jest-dom/vitest"
import { afterAll, afterEach, beforeAll } from "vitest"
import { resetDb } from "@/mocks/db"
import { server } from "@/mocks/server"

beforeAll(() => server.listen({ onUnhandledRequest: "error" }))
afterEach(() => {
  server.resetHandlers()
  resetDb()
})
afterAll(() => server.close())
