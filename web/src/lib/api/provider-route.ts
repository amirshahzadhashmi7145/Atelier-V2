export async function fetchProviderModels(refresh = false) {
  const response = await fetch(`/api/providers/openai/models${refresh ? "?refresh=1" : ""}`)
  const body = (await response.json()) as { ids?: string[]; error?: string }
  if (!response.ok) throw new Error(body.error || "Provider request failed")
  const ids = body.ids ?? []
  if (typeof sessionStorage !== "undefined") sessionStorage.setItem("atelier-discovered-models", JSON.stringify(ids))
  return ids
}
