import { bypass, http, HttpResponse } from "msw"
import { isChatModel, isRetiredModel, modelInfoFromId } from "@/lib/models/schema"
import { db, modelList, now, remember, setProviderSecret } from "@/mocks/db"

function error(status: number, code: string, message: string) {
  return HttpResponse.json({ code, message }, { status })
}

function providerOr404(id: string) {
  return db.providers.find((item) => item.id === id)
}

function markConnected(provider: NonNullable<ReturnType<typeof providerOr404>>) {
  provider.connected = true
  if (!provider.keyRef) {
    provider.keyRef = `env:${provider.id}`
    provider.keyHint = provider.keyHint ?? "••••"
  }
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
    const response = await fetch(bypass(new URL("/api/providers/openai/models", location.origin)))
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
    setProviderSecret(provider.id, body.apiKey)
    provider.keyRef = `secret:${provider.id}`
    provider.keyHint = "••••"
    provider.connected = false
    remember()
    return HttpResponse.json(provider)
  }),
  http.delete("/providers/:id/key", ({ params }) => {
    const provider = providerOr404(String(params.id))
    if (!provider) return error(404, "not_found", "Provider not found")
    setProviderSecret(provider.id, null)
    provider.keyRef = null
    provider.keyHint = null
    provider.connected = false
    remember()
    return HttpResponse.json(provider)
  }),
  http.post("/providers/:id/test", ({ params }) => {
    const provider = providerOr404(String(params.id))
    if (!provider) return error(404, "not_found", "Provider not found")
    markConnected(provider)
    remember()
    return HttpResponse.json(provider)
  }),
  http.post("/providers/:id/refresh", async ({ params }) => {
    const provider = providerOr404(String(params.id))
    if (!provider) return error(404, "not_found", "Provider not found")
    const found = await discoveredModelIds()
    if (!found) return error(422, "invalid", "Could not reach the provider")
    db.models = found.ids.filter((id) => isChatModel(id) && !isRetiredModel(id)).map((id) => modelInfoFromId(id))
    provider.modelsCachedAt = now()
    if (found.fromProvider) markConnected(provider)
    else provider.connected = false
    remember()
    return HttpResponse.json(modelList())
  }),
  http.get("/settings/runs", () => HttpResponse.json(db.runSettings)),
  http.put("/settings/runs", async ({ request }) => {
    const body = (await request.json()) as typeof db.runSettings
    if (body.maxSpendPerRunUsd == null || !body.maxIterations || !body.maxMinutes || body.loopDetection == null) {
      return error(422, "invalid", "Run settings are incomplete")
    }
    db.runSettings = body
    remember()
    return HttpResponse.json(db.runSettings)
  }),
  http.get("/model-tags", () => HttpResponse.json(db.modelTags)),
  http.put("/model-tags", async ({ request }) => {
    const body = (await request.json()) as { name?: string; tags?: string[]; note?: string }
    if (!body.name) return error(400, "invalid", "name is required")
    db.modelTags[body.name] = { tags: body.tags ?? [], note: body.note ?? "", heuristic: false }
    remember()
    return HttpResponse.json(db.modelTags[body.name])
  }),
]
