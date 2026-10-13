import { api, unwrap } from "@/lib/api/client"
import type { components } from "@/lib/api/generated/types"

export async function listProviders() {
  return unwrap(await api.GET("/providers"))
}

export async function listModels() {
  return unwrap(await api.GET("/models"))
}

export async function testProviderConnection() {
  return unwrap(await api.POST("/providers/{id}/test", { params: { path: { id: "openai" } } }))
}

export async function refreshProviderModels() {
  return unwrap(await api.POST("/providers/{id}/refresh", { params: { path: { id: "openai" } } }))
}

export async function getRunSettings() {
  return unwrap(await api.GET("/settings/runs"))
}

export async function saveRunSettings(body: components["schemas"]["RunSettings"]) {
  return unwrap(await api.PUT("/settings/runs", { body }))
}
