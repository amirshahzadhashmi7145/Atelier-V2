import { describe, expect, it } from "vitest"

describe("mock contract", () => {
  it("seeds the frontend engineer and refuses activation before a smoke eval", async () => {
    const agents = (await (await fetch("http://localhost/agents")).json()) as { name: string; stackIds: string[] }[]
    expect(agents.map((agent) => agent.name)).toContain("Frontend Engineer")
    expect(agents[0]?.stackIds).toEqual(["react"])

    const tools = (await (await fetch("http://localhost/tools")).json()) as { id: string }[]
    expect(tools).toHaveLength(11)
    expect(tools.map((tool) => tool.id)).toContain("escalate")

    const skills = (await (await fetch("http://localhost/skills")).json()) as unknown[]
    expect(skills).toHaveLength(4)

    const denied = await fetch("http://localhost/agents/frontend-engineer/versions/1/activate", {
      method: "POST",
    })
    expect(denied.status).toBe(409)
    const body = (await denied.json()) as { code: string }
    expect(body.code).toBe("smoke_eval_required")
  })
})
