import { clearOpenAIModelCache, listOpenAIModelIds } from "@/lib/api/openai-models"

export async function GET(request: Request) {
  const key = process.env.OPENAI_API_KEY
  if (!key) return Response.json({ error: "OPENAI_API_KEY is not set" }, { status: 503 })
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
