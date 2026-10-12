import { api, unwrap } from "@/lib/api/client"
import { postSkillZip } from "@/lib/api/skill-import"
import type { components } from "@/lib/api/generated/types"

type SkillCreate = components["schemas"]["SkillCreate"]
type SkillPatch = components["schemas"]["SkillPatch"]

export async function listSkills() {
  return unwrap(await api.GET("/skills"))
}

export async function getSkill(id: string) {
  return unwrap(await api.GET("/skills/{id}", { params: { path: { id } } }))
}

export async function createSkill(body: SkillCreate) {
  return unwrap(await api.POST("/skills", { body }))
}

export async function updateSkill(id: string, body: SkillPatch) {
  return unwrap(await api.PATCH("/skills/{id}", { params: { path: { id } }, body }))
}

export async function listSkillAgents() {
  return unwrap(await api.GET("/agents"))
}

export async function importSkillRepo(repoUrl: string, path: string, preview: boolean) {
  return unwrap(await api.POST("/skills/import", { body: { repoUrl, path, preview } }))
}

export { postSkillZip }
