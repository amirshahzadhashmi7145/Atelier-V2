import { api, unwrap } from "@/lib/api/client"
import type { components } from "@/lib/api/generated/types"

export type Project = components["schemas"]["Project"]
export type ChatMessage = components["schemas"]["ChatMessage"]
export type Run = components["schemas"]["Run"]

export async function listProjects() {
  return unwrap(await api.GET("/projects"))
}

export async function createProject(body: { name: string; agentId: string; repoUrl?: string; githubToken?: string }) {
  return unwrap(await api.POST("/projects", { body }))
}

export async function getProject(id: string) {
  return unwrap(await api.GET("/projects/{id}", { params: { path: { id } } }))
}

export async function listMessages(id: string) {
  return unwrap(await api.GET("/projects/{id}/messages", { params: { path: { id } } }))
}

export async function postMessage(id: string, text: string) {
  return unwrap(await api.POST("/projects/{id}/messages", { params: { path: { id } }, body: { text } }))
}

export async function stopChatRun(runId: string) {
  return unwrap(await api.POST("/runs/{id}/stop", { params: { path: { id: runId } } }))
}

export async function closeProject(id: string) {
  return unwrap(await api.POST("/projects/{id}/close", { params: { path: { id } } }))
}

export async function deleteProject(id: string) {
  const result = await api.DELETE("/projects/{id}", { params: { path: { id } } })
  if (result.response.status === 204) return
  return unwrap(result)
}

export async function listChatAgents() {
  return unwrap(await api.GET("/agents"))
}

export async function getChatRun(id: string) {
  return unwrap(await api.GET("/runs/{id}", { params: { path: { id } } }))
}

export async function answerChat(id: string, text: string) {
  return unwrap(await api.POST("/runs/{id}/answer", { params: { path: { id } }, body: { text } }))
}
