import type { ModelTag, TagRecord } from "@/lib/models/tags"

export async function listModelTags() {
  const response = await fetch("/api/model-tags")
  if (!response.ok) throw new Error("Could not load model tags")
  return (await response.json()) as Record<string, TagRecord>
}

export async function saveModelTag(name: string, tags: ModelTag[], note: string) {
  const response = await fetch("/api/model-tags", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ name, tags, note }),
  })
  if (!response.ok) throw new Error("Could not save the tag")
}
