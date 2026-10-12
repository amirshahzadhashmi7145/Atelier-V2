import { api, unwrap } from "@/lib/api/client"
import type { components } from "@/lib/api/generated/types"

type ToolCreate = components["schemas"]["ToolCreate"]
type ToolPatch = components["schemas"]["ToolPatch"]

export async function listTools() {
  return unwrap(await api.GET("/tools"))
}

export async function createTool(body: ToolCreate) {
  return unwrap(await api.POST("/tools", { body }))
}

export async function updateTool(id: string, body: ToolPatch) {
  return unwrap(await api.PATCH("/tools/{id}", { params: { path: { id } }, body }))
}

export async function discoverMcp(body: components["schemas"]["McpDiscoverRequest"]) {
  return unwrap(await api.POST("/tools/mcp/discover", { body }))
}

export async function importApiSpec(body: components["schemas"]["ApiImportRequest"]) {
  return unwrap(await api.POST("/tools/api/import", { body }))
}

export async function listDataSources() {
  return unwrap(await api.GET("/data-sources"))
}

export async function createDataSource(body: components["schemas"]["DataSourceCreate"]) {
  return unwrap(await api.POST("/data-sources", { body }))
}

export async function refreshDataSource(id: string) {
  return unwrap(await api.POST("/data-sources/{id}/refresh", { params: { path: { id } } }))
}

export async function listToolAgents() {
  return unwrap(await api.GET("/agents"))
}
