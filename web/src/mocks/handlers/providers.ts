import { http, HttpResponse } from "msw"
import { db, hasProviderSecret, modelCatalog, modelList, now, remember, setProviderSecret } from "@/mocks/db"

function error(status: number, code: string, message: string) {
  return HttpResponse.json({ code, message }, { status })
}

function providerOr404(id: string) {
  return db.providers.find((item) => item.id === id)
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
  http.post("/providers/:id/refresh", ({ params }) => {
    const provider = providerOr404(String(params.id))
    if (!provider) return error(404, "not_found", "Provider not found")
    if (!hasProviderSecret()) return error(422, "invalid", "Save an API key first")
    db.models = structuredClone(modelCatalog)
    provider.modelsCachedAt = now()
    return HttpResponse.json(modelList())
  }),
]
