import { describe, expect, it } from "vitest"
import { mcpToolsToCreate, operationsFromSpec, operationsToTools } from "@/features/tools/import-map"

describe("MCP discover mapper", () => {
  it("creates one untrusted tool per descriptor and keeps permission", () => {
    const created = mcpToolsToCreate(
      { name: "Repo", url: "https://mcp.example", auth: "header" },
      [
        { name: "repo.search", description: "Search", schema: { type: "object" }, permission: "read" },
        { name: "repo.web", description: "Fetch", schema: { type: "object" }, permission: "external" },
      ],
    )
    expect(created).toHaveLength(2)
    expect(created[1]).toMatchObject({
      kind: "mcp",
      permission: "external",
      source: "https://mcp.example",
      config: { server: "Repo", auth: "header", trust: "untrusted" },
    })
  })
})

describe("API import mapper", () => {
  it("reads operations and stores auth by reference", () => {
    const operations = operationsFromSpec(`
paths:
  /users:
    get:
      operationId: listUsers
      summary: List users
`)
    expect(operations).toEqual([
      { method: "GET", path: "/users", operationId: "listUsers", summary: "List users", description: undefined },
    ])
    expect(operationsToTools("secret:docs", operations)[0]).toMatchObject({
      kind: "api",
      name: "listUsers",
      description: "List users",
      config: { authRef: "secret:docs", trust: "untrusted" },
    })
  })
})
