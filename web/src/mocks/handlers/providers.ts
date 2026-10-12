import { bypass, http, HttpResponse } from "msw"
import { providerAuthHeaders } from "@/lib/api/provider-route"
import { isChatModel, modelInfoFromId } from "@/lib/models/schema"
import { db, hasProviderSecret, modelList, now, remember, setProviderSecret } from "@/mocks/db"

function error(status: number, code: string, message: string) {
  return HttpResponse.json({ code, message }, { status })
}

function providerOr404(id: string) {
  return db.providers.find((item) => item.id === id)
}

const FIXTURE_KEY = "atelier-discovered-models"

function fixtureIds() {
  if (typeof sessionStorage === "undefined") return null
  const raw = sessionStorage.getItem(FIXTURE_KEY)
  if (!raw) return null
  try {
    const ids = JSON.parse(raw) as unknown
    return Array.isArray(ids) ? ids.filter((id): id is string => typeof id === "string") : null
  } catch {
    return null
  }
}

export async function discoveredModelIds(): Promise<{ ids: string[]; fromProvider: boolean } | null> {
  try {
    const response = await fetch(bypass(new URL("/api/providers/openai/models", location.origin)), {
      headers: providerAuthHeaders(),
    })
    if (response.ok) {
      const body = (await response.json()) as { ids?: string[] }
      return { ids: body.ids ?? [], fromProvider: true }
    }
  } catch {
    // The provider route is down. A test can leave ids in sessionStorage.
  }
  const fixture = fixtureIds()
  return fixture ? { ids: fixture, fromProvider: false } : null
}

export const providerHandlers = [
  http.get("/providers", () => HttpResponse.json(db.providers)),
  http.put("/providers/:id", async ({ params, request }) => {
    const provider = providerOr404(String(params.id))
    if (!provider) return error(404, "not_found", "Provider not found")
    const body = (await request.json()) as { apiKey?: string }
    if (!body.apiKey) return error(422, "invalid", "apiKey is required")
    setProviderSecret(body.apiKey)
    provider.keyRef = `secret:${provider.id}`
    provider.connected = false
    remember()
    return HttpResponse.json(provider)
  }),
  http.post("/providers/:id/test", ({ params }) => {
    const provider = providerOr404(String(params.id))
    if (!provider) return error(404, "not_found", "Provider not found")
    if (!hasProviderSecret()) return error(422, "invalid", "Save an API key first")
    provider.connected = true
    remember()
    return HttpResponse.json(provider)
  }),
  http.post("/providers/:id/refresh", async ({ params }) => {
    const provider = providerOr404(String(params.id))
    if (!provider) return error(404, "not_found", "Provider not found")
    const found = await discoveredModelIds()
    if (!found) return error(422, "invalid", "Could not reach the provider")
    db.models = found.ids.filter(isChatModel).map((id) => modelInfoFromId(id))
    provider.modelsCachedAt = now()
    provider.connected = found.fromProvider
    remember()
    return HttpResponse.json(modelList())
  }),
]
