const KEY = "atelier-openai-key"

export function readProviderKey() {
  if (typeof sessionStorage === "undefined") return ""
  return sessionStorage.getItem(KEY) ?? ""
}

export function writeProviderKey(value: string) {
  sessionStorage.setItem(KEY, value)
}

export function providerAuthHeaders(): HeadersInit {
  const key = readProviderKey()
  return key ? { authorization: `Bearer ${key}` } : {}
}

export async function fetchProviderModels(refresh = false) {
  const response = await fetch(`/api/providers/openai/models${refresh ? "?refresh=1" : ""}`, {
    headers: providerAuthHeaders(),
  })
  const body = (await response.json()) as { ids?: string[]; error?: string }
  if (!response.ok) throw new Error(body.error || "Provider request failed")
  const ids = body.ids ?? []
  if (typeof sessionStorage !== "undefined") sessionStorage.setItem("atelier-discovered-models", JSON.stringify(ids))
  return ids
}
