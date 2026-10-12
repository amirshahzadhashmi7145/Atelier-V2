import { http, HttpResponse } from "msw"
import { isChatModel, modelInfoFromId } from "@/lib/models/schema"
import { db, modelList, nid, now, remember } from "@/mocks/db"
import { discoveredModelIds } from "@/mocks/handlers/providers"

function error(status: number, code: string, message: string) {
  return HttpResponse.json({ code, message }, { status })
}

export const toolHandlers = [
  http.get("/tools", () => HttpResponse.json(db.tools.filter((tool) => tool.kind !== "control"))),
  http.post("/tools/mcp/discover", async ({ request }) => {
    const body = (await request.json()) as { serverUrl?: string }
    if (!body.serverUrl) return error(400, "invalid", "serverUrl is required")
    const schema = { type: "object", properties: { query: { type: "string" } }, required: ["query"] }
    return HttpResponse.json({
      tools: [
        { name: "repo.search", description: "Search the connected repository.", schema, permission: "read" },
        { name: "repo.read", description: "Read a file from the connected repository.", schema, permission: "read" },
        { name: "repo.write", description: "Write a file in the connected repository.", schema, permission: "write" },
        { name: "repo.web", description: "Fetch a page from the web.", schema, permission: "external" },
      ],
    })
  }),
  http.post("/tools/api/import", async ({ request }) => {
    const body = (await request.json()) as { spec?: string; specUrl?: string }
    if (!body.spec && !body.specUrl) return error(400, "invalid", "spec or specUrl is required")
    // ponytail: any spec returns the same five operations until the API parses the document
    return HttpResponse.json({
      operations: [
        { method: "GET", path: "/users", operationId: "listUsers", summary: "List users" },
        { method: "POST", path: "/users", operationId: "createUser", summary: "Create a user" },
        { method: "GET", path: "/users/{id}", operationId: "getUser", summary: "Get a user" },
        { method: "PATCH", path: "/users/{id}", operationId: "updateUser", summary: "Update a user" },
        { method: "DELETE", path: "/users/{id}", operationId: "deleteUser", summary: "Delete a user" },
      ],
    })
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
    db.tools.push({
      id: nid("tool"),
      kind: "data",
      name: "search_data",
      description: `Search ${created.name}`,
      schema: { type: "object", additionalProperties: false, properties: { query: { type: "string" } }, required: ["query"] },
      permission: "read",
      config: { dataSourceId: created.id },
      source: created.ref,
      enabled: true,
    })
    remember()
    return HttpResponse.json(created, { status: 201 })
  }),
  http.post("/data-sources/:id/refresh", ({ params }) => {
    const source = db.dataSources.find((item) => item.id === String(params.id))
    if (!source) return error(404, "not_found", "Data source not found")
    source.lastPulledAt = now()
    source.pagesChanged = (source.pagesChanged ?? 0) + 1
    remember()
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
  http.get("/models", async () => {
    const found = await discoveredModelIds()
    const provider = db.providers.find((item) => item.id === "openai")
    if (found) {
      db.models = found.ids.filter(isChatModel).map((id) => modelInfoFromId(id))
      if (provider) {
        provider.modelsCachedAt = now()
        provider.connected = found.fromProvider
      }
    } else if (provider) {
      db.models = []
      provider.connected = false
      provider.modelsCachedAt = null
    }
    remember()
    return HttpResponse.json(modelList())
  }),
]
