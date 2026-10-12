import { describe, expect, it } from "vitest"

describe("mock contract", () => {
  it("starts empty, hides control tools, and blocks activation until evals pass", async () => {
    expect(await (await fetch("http://localhost/agents")).json()).toEqual([])
    expect(await (await fetch("http://localhost/skills")).json()).toEqual([])
    expect(await (await fetch("http://localhost/stacks")).json()).toEqual([])

    const tools = (await (await fetch("http://localhost/tools")).json()) as { id: string; kind: string }[]
    expect(tools.map((tool) => tool.id)).toContain("shell")
    expect(tools.map((tool) => tool.id)).not.toContain("escalate")
    expect(tools.every((tool) => tool.kind !== "control")).toBe(true)

    const imported = await fetch("http://localhost/library/frontend-engineer/import", { method: "POST" })
    expect(imported.status).toBe(201)
    const created = (await imported.json()) as { id: string }
    const agents = (await (await fetch("http://localhost/agents")).json()) as {
      id: string
      name: string
      evals: unknown[]
      stackIds: string[]
    }[]
    expect(agents.map((agent) => agent.name)).toContain("Frontend Engineer")
    expect(agents[0]?.evals.length).toBeGreaterThan(0)
    expect(agents[0]?.stackIds).toEqual(["react"])

    const denied = await fetch(`http://localhost/agents/${created.id}/versions/1/activate`, { method: "POST" })
    expect(denied.status).toBe(409)
    expect(((await denied.json()) as { code: string }).code).toBe("evals_required")
  })

  it("caches provider models only after a key is stored", async () => {
    expect(await (await fetch("http://localhost/models")).json()).toEqual([])
    const refused = await fetch("http://localhost/providers/openai/refresh", { method: "POST" })
    expect(refused.status).toBe(422)

    const saved = await fetch("http://localhost/providers/openai", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ apiKey: "sk-test" }),
    })
    const status = (await saved.json()) as { keyRef: string; connected: boolean }
    expect(status.keyRef).toBe("secret:openai")
    expect(JSON.stringify(status)).not.toContain("sk-test")

    await fetch("http://localhost/providers/openai/test", { method: "POST" })
    const models = (await (await fetch("http://localhost/providers/openai/refresh", { method: "POST" })).json()) as {
      name: string
      configSchema: { properties: Record<string, unknown> }
      benchmarks: unknown[]
      priceInPerM: number | null
    }[]
    expect(models).toHaveLength(6)
    expect(models.find((model) => model.name === "gpt-5")?.configSchema.properties).toHaveProperty("webSearch")
    expect(models.find((model) => model.name === "o3")?.configSchema.properties).not.toHaveProperty("temperature")
    expect(models.every((model) => model.benchmarks.length === 0 && model.priceInPerM === null)).toBe(true)
  })
})
