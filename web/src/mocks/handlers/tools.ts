import { http, HttpResponse } from "msw"
import { parse } from "yaml"
import { db, modelList, nid, now } from "@/mocks/db"

function error(status: number, code: string, message: string) {
  return HttpResponse.json({ code, message }, { status })
}

export const toolHandlers = [
  http.get("/tools", () => HttpResponse.json(db.tools.filter((tool) => tool.kind !== "control"))),
  http.post("/tools/mcp/discover", async ({ request }) => {
    const body = (await request.json()) as { serverUrl?: string }
    if (!body.serverUrl) return error(400, "invalid", "serverUrl is required")
    return HttpResponse.json({
      tools: [
        {
          name: "repo.search",
          description: "Search the connected repository.",
          schema: { type: "object", properties: { query: { type: "string" } }, required: ["query"] },
        },
        {
          name: "repo.read",
          description: "Read a file from the connected repository.",
          schema: { type: "object", properties: { path: { type: "string" } }, required: ["path"] },
        },
      ],
    })
  }),
  http.post("/tools/api/import", async ({ request }) => {
    const body = (await request.json()) as { spec?: string; specUrl?: string }
    if (!body.spec && !body.specUrl) return error(400, "invalid", "spec or specUrl is required")
    if (!body.spec) {
      return HttpResponse.json({
        operations: [
          { method: "GET", path: "/status", operationId: "getStatus", description: body.specUrl },
        ],
      })
    }
    let doc: { paths?: Record<string, Record<string, { operationId?: string; description?: string }>> }
    try {
      doc = parse(body.spec) as typeof doc
    } catch {
      return error(400, "invalid", "spec is not valid YAML or JSON")
    }
    const operations = []
    for (const [path, methods] of Object.entries(doc.paths ?? {})) {
      for (const [method, operation] of Object.entries(methods ?? {})) {
        if (!["get", "post", "put", "patch", "delete"].includes(method)) continue
        operations.push({
          method: method.toUpperCase(),
          path,
          operationId: operation.operationId ?? `${method}_${path}`,
          description: operation.description ?? "",
        })
      }
    }
    return HttpResponse.json({ operations })
  }),
  http.post("/tools", async ({ request }) => {
    const body = (await request.json()) as {
      kind?: (typeof db.tools)[number]["kind"]
      name?: string
      description?: string
      schema?: Record<string, unknown>
      permission?: (typeof db.tools)[number]["permission"]
      config?: Record<string, unknown>
      source?: string
      enabled?: boolean
    }
    if (!body.kind || !body.name || !body.description || !body.schema || !body.permission) {
      return error(422, "invalid", "kind, name, description, schema, and permission are required")
    }
    const created = {
      id: nid("tool"),
      kind: body.kind,
      name: body.name,
      description: body.description,
      schema: body.schema,
      permission: body.permission,
      config: body.config ?? {},
      source: body.source ?? body.kind,
      enabled: body.enabled ?? true,
    }
    db.tools.push(created)
    return HttpResponse.json(created, { status: 201 })
  }),
  http.patch("/tools/:id", async ({ params, request }) => {
    const tool = db.tools.find((item) => item.id === String(params.id))
    if (!tool) return error(404, "not_found", "Tool not found")
    Object.assign(tool, await request.json())
    return HttpResponse.json(tool)
  }),
  http.get("/data-sources", () => HttpResponse.json(db.dataSources)),
  http.post("/data-sources", async ({ request }) => {
    const body = (await request.json()) as {
      name?: string
      kind?: (typeof db.dataSources)[number]["kind"]
      ref?: string
      refreshPolicy?: (typeof db.dataSources)[number]["refreshPolicy"]
    }
    if (!body.name || !body.kind || !body.ref || !body.refreshPolicy) {
      return error(422, "invalid", "name, kind, ref, and refreshPolicy are required")
    }
    const created = {
      id: nid("ds"),
      name: body.name,
      kind: body.kind,
      ref: body.ref,
      refreshPolicy: body.refreshPolicy,
      lastPulledAt: null,
      pagesChanged: null,
      versionTag: null,
    }
    db.dataSources.push(created)
    return HttpResponse.json(created, { status: 201 })
  }),
  http.post("/data-sources/:id/refresh", ({ params }) => {
    const source = db.dataSources.find((item) => item.id === String(params.id))
    if (!source) return error(404, "not_found", "Data source not found")
    source.lastPulledAt = now()
    source.pagesChanged = 0
    return HttpResponse.json(source)
  }),
  http.get("/stacks", () => HttpResponse.json(db.stacks)),
  http.patch("/stacks/:id", async ({ params, request }) => {
    const stack = db.stacks.find((item) => item.id === String(params.id))
    if (!stack) return error(404, "not_found", "Stack not found")
    const body = (await request.json()) as Partial<Pick<typeof stack, "packageAllowList" | "skillIds" | "dataSourceIds">>
    if (body.packageAllowList) stack.packageAllowList = body.packageAllowList
    if (body.skillIds) stack.skillIds = body.skillIds
    if (body.dataSourceIds) stack.dataSourceIds = body.dataSourceIds
    return HttpResponse.json(stack)
  }),
  http.get("/models", () => HttpResponse.json(modelList())),
]
