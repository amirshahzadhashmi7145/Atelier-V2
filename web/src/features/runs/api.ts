import type { components } from "@/lib/api/generated/types"
import { api, unwrap } from "@/lib/api/client"

export async function listRuns(query: {
  page?: number
  agentId?: string
  status?: components["schemas"]["RunStatus"]
}) {
  return unwrap(await api.GET("/runs", { params: { query } }))
}

export async function getRun(id: string) {
  return unwrap(await api.GET("/runs/{id}", { params: { path: { id } } }))
}

export async function createRun(body: components["schemas"]["RunCreate"]) {
  return unwrap(await api.POST("/runs", { body }))
}

export async function stopRun(id: string) {
  return unwrap(await api.POST("/runs/{id}/stop", { params: { path: { id } } }))
}

export async function answerRun(id: string, text: string) {
  return unwrap(await api.POST("/runs/{id}/answer", { params: { path: { id } }, body: { text } }))
}

export async function respondToClientTool(id: string, requestId: string) {
  return unwrap(
    await api.POST("/runs/{id}/client-tool-result", {
      params: { path: { id } },
      body: { requestId, output: { accepted: true }, error: null },
    }),
  )
}

export async function getRunDiff(id: string) {
  return unwrap(await api.GET("/runs/{id}/diff", { params: { path: { id } } }))
}

export async function listRunArtifacts(id: string) {
  return unwrap(await api.GET("/runs/{id}/artifacts", { params: { path: { id } } }))
}

export async function listRunAgents() {
  return unwrap(await api.GET("/agents"))
}

export async function listRunVersions(id: string) {
  return unwrap(await api.GET("/agents/{id}/versions", { params: { path: { id } } }))
}

export async function listRunStacks() {
  return unwrap(await api.GET("/stacks"))
}

export async function getSpendCap() {
  return unwrap(await api.GET("/settings/runs"))
}
