export const MODEL_TAGS = ["frontend", "backend", "qa", "review", "planning", "cheap", "fast"] as const

export type ModelTag = (typeof MODEL_TAGS)[number]

export type TagRecord = { tags: ModelTag[]; note: string; heuristic: boolean }

const HEURISTIC = "heuristic, edit me"

function isReasoning(id: string) {
  if (/chat/i.test(id)) return false
  return /^(o\d|gpt-5)([-.]|$)/i.test(id)
}

export function seedTags(id: string): TagRecord {
  if (/mini|nano|fast/i.test(id)) return { tags: ["cheap", "fast"], note: HEURISTIC, heuristic: true }
  if (isReasoning(id)) return { tags: ["planning", "review"], note: HEURISTIC, heuristic: true }
  return { tags: [], note: "", heuristic: false }
}

export function tagsFor(id: string, saved: TagRecord | undefined): TagRecord {
  return saved ?? seedTags(id)
}
