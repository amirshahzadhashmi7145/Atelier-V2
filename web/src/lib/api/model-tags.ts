import { api, unwrap } from "@/lib/api/client"
import type { ModelTag, TagRecord } from "@/lib/models/tags"

export async function listModelTags() {
  const tags = await unwrap(await api.GET("/model-tags"))
  return tags as unknown as Record<string, TagRecord>
}

export async function saveModelTag(name: string, tags: ModelTag[], note: string) {
  await unwrap(await api.PUT("/model-tags", { body: { name, tags, note } }))
}
