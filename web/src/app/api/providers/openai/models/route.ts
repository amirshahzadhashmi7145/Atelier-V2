import { clearOpenAIModelCache, listOpenAIModelIds } from "@/lib/api/openai-models"

export async function GET(request: Request) {
  const header = request.headers.get("authorization") ?? ""
  const key = header.toLowerCase().startsWith("bearer ") ? header.slice(7).trim() : ""
  if (!key) return Response.json({ error: "Enter an API key" }, { status: 503 })
  const refresh = new URL(request.url).searchParams.get("refresh") === "1"
  if (refresh) clearOpenAIModelCache()
  try {
    const ids = await listOpenAIModelIds(key, refresh)
    return Response.json({ ids })
  } catch (error) {
    const message = error instanceof Error ? error.message : "OpenAI request failed"
    return Response.json({ error: message }, { status: 502 })
  }
}
