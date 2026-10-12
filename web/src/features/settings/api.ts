import { api, unwrap } from "@/lib/api/client"
import { fetchProviderModels } from "@/lib/api/provider-route"

export async function listProviders() {
  return unwrap(await api.GET("/providers"))
}

export async function listModels() {
  return unwrap(await api.GET("/models"))
}

export async function testProviderConnection() {
  const ids = await fetchProviderModels(false)
  return ids
}

export async function refreshProviderModels() {
  await fetchProviderModels(true)
  return listModels()
}
