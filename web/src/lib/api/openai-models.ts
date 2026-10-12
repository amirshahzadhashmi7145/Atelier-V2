import { isChatModel } from "@/lib/models/schema"

const HOUR = 60 * 60 * 1000

let cache: { at: number; ids: string[] } | null = null

export function clearOpenAIModelCache() {
  cache = null
}

type ModelsResponse = { data?: { id?: string }[]; error?: { message?: string } }

export async function listOpenAIModelIds(
  key: string,
  refresh = false,
  fetchImpl: typeof fetch = fetch,
) {
  if (!refresh && cache && Date.now() - cache.at < HOUR) return cache.ids
  const response = await fetchImpl("https://api.openai.com/v1/models", {
    headers: { authorization: `Bearer ${key}` },
    cache: "no-store",
  })
  const body = (await response.json()) as ModelsResponse
  if (!response.ok) throw new Error(body.error?.message || "OpenAI rejected the key")
  const ids = (body.data ?? []).flatMap((item) => (item.id && isChatModel(item.id) ? [item.id] : []))
  cache = { at: Date.now(), ids }
  return ids
}
