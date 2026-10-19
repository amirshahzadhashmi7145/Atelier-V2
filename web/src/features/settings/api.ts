import { api, unwrap } from "@/lib/api/client"
import type { components } from "@/lib/api/generated/types"

export async function listProviders() {
  return unwrap(await api.GET("/providers"))
}

export async function listModels() {
  return unwrap(await api.GET("/models"))
}

export async function saveProviderKey(id: string, apiKey: string) {
  return unwrap(await api.PUT("/providers/{id}", { params: { path: { id } }, body: { apiKey } }))
}

export async function deleteProviderKey(id: string) {
  return unwrap(await api.DELETE("/providers/{id}/key", { params: { path: { id } } }))
}

export async function testProviderConnection(id: string) {
  return unwrap(await api.POST("/providers/{id}/test", { params: { path: { id } } }))
}

export async function refreshProviderModels(id: string) {
  return unwrap(await api.POST("/providers/{id}/refresh", { params: { path: { id } } }))
}

export async function getRunSettings() {
  return unwrap(await api.GET("/settings/runs"))
}

export async function saveRunSettings(body: components["schemas"]["RunSettings"]) {
  return unwrap(await api.PUT("/settings/runs", { body }))
}

export async function listSettingsAgents() {
  return unwrap(await api.GET("/agents"))
}

export async function compareEvalModels(id: string, version: number, models: string[]) {
  return unwrap(
    await api.POST("/agents/{id}/versions/{v}/evals/compare", {
      params: { path: { id, v: version } },
      body: { models },
    }),
  )
}

export async function listAgentVersions(id: string) {
  return unwrap(await api.GET("/agents/{id}/versions", { params: { path: { id } } }))
}

export async function listRoles() {
  return unwrap(await api.GET("/roles"))
}

export async function createRole(body: components["schemas"]["RoleWrite"]) {
  return unwrap(await api.POST("/roles", { body }))
}

export async function updateRole(id: string, body: components["schemas"]["RoleWrite"]) {
  return unwrap(await api.PATCH("/roles/{id}", { params: { path: { id } }, body }))
}

export async function listRoleTags() {
  const result = await unwrap(await api.GET("/tags"))
  return result.tags
}
