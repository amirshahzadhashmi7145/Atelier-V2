import { http, HttpResponse } from "msw"
import { compilePrompt } from "@/features/agents/compile"
import { db, library, nid, now, orderedById } from "@/mocks/db"

function error(status: number, code: string, message: string) {
  return HttpResponse.json({ code, message }, { status })
}

function importSkill(id: string) {
  if (db.skills.some((skill) => skill.id === id)) return
  const skill = library.skills.find((item) => item.id === id)
  if (skill) db.skills.push(structuredClone(skill))
}

function importStack(id: string) {
  if (db.stacks.some((stack) => stack.id === id)) return
  const stack = library.stacks.find((item) => item.id === id)
  if (!stack) return
  db.stacks.push(structuredClone(stack))
  for (const sourceId of stack.dataSourceIds) {
    if (db.dataSources.some((source) => source.id === sourceId)) continue
    const source = library.dataSources.find((item) => item.id === sourceId)
    if (source) db.dataSources.push(structuredClone(source))
  }
}

export const libraryHandlers = [
  http.get("/library", ({ request }) => {
    const kind = new URL(request.url).searchParams.get("kind")
    if (kind !== "agent" && kind !== "skill" && kind !== "stack") {
      return error(400, "invalid", "kind must be agent, skill, or stack")
    }
    const items = kind === "agent" ? library.agents : kind === "skill" ? library.skills : library.stacks
    return HttpResponse.json(
      items.map((item) => ({
        id: item.id,
        kind,
        name: item.name,
        description: "description" in item ? item.description : `${item.name} ${"version" in item ? item.version : ""}`.trim(),
      })),
    )
  }),
  http.post("/library/:id/import", ({ params }) => {
    const id = String(params.id)
    const template = library.agents.find((item) => item.id === id)
    if (template) {
      for (const skillId of template.skillIds) importSkill(skillId)
      for (const stackId of template.stackIds) importStack(stackId)
      const timestamp = now()
      const agent = {
        id: nid("agt"),
        name: template.name,
        roleKey: template.roleKey,
        description: template.description,
        model: structuredClone(template.model),
        activePromptVersionId: null,
        toolIds: [...template.toolIds],
        skillIds: [...template.skillIds],
        stackIds: [...template.stackIds],
        zones: [...template.zones],
        evals: structuredClone(template.evals),
        reportsTo: null,
        capabilities: { stacks: [...template.stackIds], skills: [...template.skillIds], tags: [] },
        createdAt: timestamp,
        updatedAt: timestamp,
      }
      const controlIds = db.tools.filter((tool) => tool.kind === "control").map((tool) => tool.id)
      const toolIds = [...agent.toolIds, ...controlIds]
      const compiled = compilePrompt({
        sections: template.sections,
        stacks: orderedById(db.stacks, agent.stackIds).map((stack) => ({ name: stack.name, version: stack.version })),
        tools: orderedById(db.tools, toolIds).map((tool) => ({ name: tool.name, description: tool.description })),
        skills: orderedById(db.skills, agent.skillIds).map((skill) => ({ name: skill.name, description: skill.description })),
      })
      db.agents.push(agent)
      db.versions.push({
        id: nid("pv"),
        agentId: agent.id,
        version: 1,
        sections: structuredClone(template.sections),
        compiled: compiled.compiled,
        tokenCount: compiled.tokenCount,
        evalResults: agent.evals.map((item) => ({ evalId: item.id, status: "not_run" as const, evidence: null })),
        createdAt: timestamp,
      })
      return HttpResponse.json({ kind: "agent" as const, id: agent.id }, { status: 201 })
    }
    if (library.skills.some((item) => item.id === id)) {
      importSkill(id)
      return HttpResponse.json({ kind: "skill" as const, id }, { status: 201 })
    }
    if (library.stacks.some((item) => item.id === id)) {
      importStack(id)
      return HttpResponse.json({ kind: "stack" as const, id }, { status: 201 })
    }
    return error(404, "not_found", "Library item not found")
  }),
]
