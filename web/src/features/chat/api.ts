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

export async function patchProject(
  id: string,
  body: { notesPath?: string; notesMaxBytes?: number; repoUrl?: string | null; githubToken?: string },
) {
  return unwrap(await api.PATCH("/projects/{id}", { params: { path: { id } }, body }))
}

export async function openProjectFolder(id: string) {
  return unwrap(await api.POST("/projects/{id}/open-folder", { params: { path: { id } } }))
}

export async function pushProjectToGithub(id: string, message?: string) {
  return unwrap(await api.POST("/projects/{id}/push", { params: { path: { id } }, body: message ? { message } : {} }))
}

export async function addProjectMember(id: string, agentId: string) {
  return unwrap(await api.POST("/projects/{id}/members", { params: { path: { id } }, body: { agentId } }))
}

export async function approveProjectPlan(id: string, planId: string, items?: components["schemas"]["PlanItem"][]) {
  return unwrap(await api.POST("/projects/{id}/plans/{planId}/approve", { params: { path: { id, planId } }, body: items ? { items } : {} }))
}

export async function editProjectPlan(id: string, planId: string, items: components["schemas"]["PlanItem"][]) {
  return unwrap(await api.POST("/projects/{id}/plans/{planId}/edit", { params: { path: { id, planId } }, body: { items } }))
}

export async function listMessages(id: string) {
  return unwrap(await api.GET("/projects/{id}/messages", { params: { path: { id } } }))
}

export async function getProjectTask(id: string, taskId: string) {
  return unwrap(await api.GET("/projects/{id}/tasks/{taskId}", { params: { path: { id, taskId } } }))
}

export async function listProjectTasks(id: string) {
  return unwrap(await api.GET("/projects/{id}/tasks", { params: { path: { id } } }))
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

export async function listProjectNeeds(id: string) {
  return unwrap(await api.GET("/projects/{id}/needs", { params: { path: { id } } }))
}

export async function answerNeed(id: string, text: string) {
  return unwrap(await api.POST("/needs/{id}/answer", { params: { path: { id } }, body: { text } }))
}
