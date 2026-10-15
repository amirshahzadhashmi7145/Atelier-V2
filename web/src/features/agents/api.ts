import type { components } from "@/lib/api/generated/types"
import { api, unwrap } from "@/lib/api/client"

type Sections = components["schemas"]["PromptSections"]

export async function listAgents() {
  return unwrap(await api.GET("/agents"))
}

export async function getAgent(id: string) {
  return unwrap(await api.GET("/agents/{id}", { params: { path: { id } } }))
}

export async function createAgent(body: components["schemas"]["AgentCreate"]) {
  return unwrap(await api.POST("/agents", { body }))
}

export async function updateAgent(id: string, body: components["schemas"]["AgentPatch"]) {
  return unwrap(await api.PATCH("/agents/{id}", { params: { path: { id } }, body }))
}

export function latestVersion<T extends { version: number }>(versions: T[]): T | undefined {
  if (versions.length === 0) return undefined
  return versions.reduce((best, item) => (item.version > best.version ? item : best))
}

export async function listVersions(id: string) {
  const rows = unwrap(await api.GET("/agents/{id}/versions", { params: { path: { id } } }))
  return [...rows].sort((a, b) => a.version - b.version)
}

export async function createVersion(id: string, sections: Sections) {
  return unwrap(await api.POST("/agents/{id}/versions", { params: { path: { id } }, body: { sections } }))
}

export async function activateVersion(id: string, version: number) {
  return unwrap(await api.POST("/agents/{id}/versions/{v}/activate", { params: { path: { id, v: version } } }))
}

export async function diffVersions(id: string, version: number, against: number) {
  return unwrap(
    await api.GET("/agents/{id}/versions/{v}/diff", {
      params: { path: { id, v: version }, query: { against } },
    }),
  )
}

export async function teachAgent(id: string, body: components["schemas"]["TeachRequest"]) {
  return unwrap(await api.POST("/agents/{id}/teach", { params: { path: { id } }, body }))
}

export async function draftTeachRules(id: string, repoUrl: string) {
  return unwrap(await api.POST("/agents/{id}/teach/draft", { params: { path: { id } }, body: { repoUrl } }))
}

export async function compilePreview(id: string, body: components["schemas"]["CompilePreviewRequest"]) {
  return unwrap(await api.POST("/agents/{id}/compile-preview", { params: { path: { id } }, body }))
}

export async function listLibrary(kind: "agent" | "skill" | "stack") {
  return unwrap(await api.GET("/library", { params: { query: { kind } } }))
}

export async function importLibraryItem(id: string) {
  return unwrap(await api.POST("/library/{id}/import", { params: { path: { id } } }))
}

export async function createEval(id: string, body: components["schemas"]["EvalCreate"]) {
  return unwrap(await api.POST("/agents/{id}/evals", { params: { path: { id } }, body }))
}

export async function deleteEval(id: string, evalId: string) {
  return unwrap(await api.DELETE("/agents/{id}/evals/{evalId}", { params: { path: { id, evalId } } }))
}

export async function runEvals(id: string, version: number) {
  return unwrap(await api.POST("/agents/{id}/versions/{v}/evals/run", { params: { path: { id, v: version } } }))
}

export async function listEditorTools() {
  return unwrap(await api.GET("/tools"))
}

export async function listEditorSkills() {
  return unwrap(await api.GET("/skills"))
}

export async function listEditorStacks() {
  return unwrap(await api.GET("/stacks"))
}

export async function createStack(body: components["schemas"]["StackCreate"]) {
  return unwrap(await api.POST("/stacks", { body }))
}

export async function createDataSource(body: components["schemas"]["DataSourceCreate"]) {
  return unwrap(await api.POST("/data-sources", { body }))
}

export async function listEditorModels() {
  return unwrap(await api.GET("/models"))
}

export function activeBlockReason(
  evals: { id: string }[],
  version: { evalResults: { evalId: string; status: string }[] } | undefined,
) {
  if (!version) return "Save a version first"
  if (evals.length === 0) return "Add an eval and run it"
  const pending = evals.some((item) => version.evalResults.find((result) => result.evalId === item.id)?.status !== "pass")
  return pending ? "Evals have not all passed" : null
}
