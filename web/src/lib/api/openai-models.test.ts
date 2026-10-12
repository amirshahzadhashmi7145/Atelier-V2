import { afterEach, describe, expect, it, vi } from "vitest"
import { clearOpenAIModelCache, listOpenAIModelIds } from "@/lib/api/openai-models"

afterEach(() => clearOpenAIModelCache())

function jsonResponse(body: unknown, ok = true) {
  return Promise.resolve({ ok, json: async () => body } as Response)
}

describe("listOpenAIModelIds", () => {
  it("filters non-chat ids and caches for the hour", async () => {
    const fetchImpl = vi.fn(() =>
      jsonResponse({
        data: [{ id: "gpt-4.1" }, { id: "whisper-1" }, { id: "o3" }],
      }),
    )
    const first = await listOpenAIModelIds("sk-test", false, fetchImpl)
    const second = await listOpenAIModelIds("sk-test", false, fetchImpl)
    expect(first).toEqual(["gpt-4.1", "o3"])
    expect(second).toEqual(first)
    expect(fetchImpl).toHaveBeenCalledTimes(1)
  })

  it("refetches when refresh is set and surfaces the provider error", async () => {
    const fetchImpl = vi
      .fn()
      .mockImplementationOnce(() => jsonResponse({ data: [{ id: "gpt-4.1" }] }))
      .mockImplementationOnce(() => jsonResponse({ error: { message: "Incorrect API key provided" } }, false))
    await listOpenAIModelIds("sk-test", false, fetchImpl)
    await expect(listOpenAIModelIds("sk-test", true, fetchImpl)).rejects.toThrow("Incorrect API key provided")
    expect(fetchImpl).toHaveBeenCalledTimes(2)
  })
})
