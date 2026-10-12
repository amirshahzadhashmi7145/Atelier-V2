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

  it("does not echo a provider key and leaves models empty until the provider route answers", async () => {
    expect(await (await fetch("http://localhost/models")).json()).toEqual([])
    const saved = await fetch("http://localhost/providers/openai", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ apiKey: "sk-test" }),
    })
    const status = (await saved.json()) as { keyRef: string }
    expect(status.keyRef).toBe("secret:openai")
    expect(JSON.stringify(status)).not.toContain("sk-test")
    const refused = await fetch("http://localhost/providers/openai/refresh", { method: "POST" })
    expect(refused.status).toBe(422)
    expect(await (await fetch("http://localhost/models")).json()).toEqual([])
  })

  it("discovers four mcp tools and five api operations", async () => {
    const mcp = (await (
      await fetch("http://localhost/tools/mcp/discover", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ serverUrl: "https://mcp.example", auth: "none" }),
      })
    ).json()) as { tools: { permission?: string }[] }
    expect(mcp.tools).toHaveLength(4)
    expect(mcp.tools.filter((tool) => tool.permission === "external")).toHaveLength(1)

    const api = (await (
      await fetch("http://localhost/tools/api/import", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
        spec: `paths:\n  /users:\n    get:\n      operationId: listUsers\n    post:\n      operationId: createUser\n  /users/{id}:\n    get:\n      operationId: getUser\n    patch:\n      operationId: updateUser\n    delete:\n      operationId: deleteUser\n`,
      }),
      })
    ).json()) as { operations: unknown[] }
    expect(api.operations).toHaveLength(5)
  })
})
