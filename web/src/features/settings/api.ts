import { api, unwrap } from "@/lib/api/client"
import type { components } from "@/lib/api/generated/types"

export async function listProviders() {
  return unwrap(await api.GET("/providers"))
}

export async function listModels() {
  return unwrap(await api.GET("/models"))
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
