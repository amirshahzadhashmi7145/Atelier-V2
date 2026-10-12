import { parse } from "yaml"

const METHODS = ["get", "post", "put", "patch", "delete"]

export type McpDescriptor = {
  name: string
  description: string
  schema: Record<string, unknown>
  permission?: "read" | "write" | "external"
}

export function mcpToolsToCreate(
  server: { name: string; url: string; auth: "none" | "header" | "oauth" },
  tools: McpDescriptor[],
) {
  return tools.map((tool) => ({
    kind: "mcp" as const,
    name: tool.name,
    description: tool.description,
    schema: tool.schema,
    permission: tool.permission ?? "read",
    source: server.url,
    config: { server: server.name, auth: server.auth, trust: "untrusted" },
    enabled: true,
  }))
}

type Operation = { method: string; path: string; operationId: string; summary?: string; description?: string }

export function operationsFromSpec(text: string): Operation[] {
  const doc = parse(text) as {
    paths?: Record<string, Record<string, { operationId?: string; summary?: string; description?: string }>>
  }
  const operations: Operation[] = []
  for (const [path, methods] of Object.entries(doc.paths ?? {})) {
    for (const [method, operation] of Object.entries(methods ?? {})) {
      if (!METHODS.includes(method)) continue
      operations.push({
        method: method.toUpperCase(),
        path,
        operationId: operation.operationId ?? `${method}_${path}`,
        summary: operation.summary,
        description: operation.description,
      })
    }
  }
  return operations
}

export function operationsToTools(authRef: string, operations: Operation[]) {
  return operations.map((operation) => ({
    kind: "api" as const,
    name: operation.operationId,
    description: operation.summary || operation.description || `${operation.method} ${operation.path}`,
    schema: { type: "object", additionalProperties: true },
    permission: "external" as const,
    source: `${operation.method} ${operation.path}`,
    config: { authRef, method: operation.method, path: operation.path, trust: "untrusted" },
    enabled: true,
  }))
}
