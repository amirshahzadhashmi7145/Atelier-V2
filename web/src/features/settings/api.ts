import { api, unwrap } from "@/lib/api/client"

export async function listProviders() {
  return unwrap(await api.GET("/providers"))
}

export async function listModels() {
  return unwrap(await api.GET("/models"))
}

export async function saveProviderKey(id: string, apiKey: string) {
  return unwrap(await api.PUT("/providers/{id}", { params: { path: { id } }, body: { apiKey } }))
}

export async function testProvider(id: string) {
  return unwrap(await api.POST("/providers/{id}/test", { params: { path: { id } } }))
}

export async function refreshModels(id: string) {
  return unwrap(await api.POST("/providers/{id}/refresh", { params: { path: { id } } }))
}
