import { apiBaseUrl, ApiError } from "@/lib/api/client"
import type { components } from "@/lib/api/generated/types"

export async function postSkillZip(file: File, preview: boolean) {
  const form = new FormData()
  form.set("file", file)
  form.set("preview", preview ? "true" : "false")
  const response = await fetch(`${apiBaseUrl()}/skills/import`, { method: "POST", body: form })
  const body = (await response.json()) as components["schemas"]["SkillImportResult"] & { message?: string; code?: string }
  if (!response.ok) throw new ApiError(body.message || "Import failed", response.status, body.code)
  return body
}
