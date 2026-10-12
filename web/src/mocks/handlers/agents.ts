import { http, HttpResponse } from "msw"
import { compilePrompt } from "@/features/agents/compile"
import { asSchema, validateConfig } from "@/features/agents/config-schema"
import { isChatModel, modelInfoFromId } from "@/lib/models/schema"
import { db, nid, now, orderedById } from "@/mocks/db"

function error(status: number, code: string, message: string) {
  return HttpResponse.json({ code, message }, { status })
}

function agentOr404(id: string) {
  return db.agents.find((agent) => agent.id === id)
}

function modelError(model: { provider: string; name: string; config: Record<string, unknown> }) {
  if (!isChatModel(model.name)) return "Unknown model. Refresh models in Settings."
  return validateConfig(asSchema(modelInfoFromId(model.name).configSchema), model.config)
}

function compileFor(
  sections: (typeof db.versions)[number]["sections"],
  toolIds: string[],
  skillIds: string[],
  stackIds: string[],
) {
  const controlIds = db.tools.filter((tool) => tool.kind === "control").map((tool) => tool.id)
  const ids = [...toolIds, ...controlIds.filter((id) => !toolIds.includes(id))]
  return compilePrompt({
    sections,
    stacks: orderedById(db.stacks, stackIds).map((stack) => ({ name: stack.name, version: stack.version })),
    tools: orderedById(db.tools, ids).map((item) => ({ name: item.name, description: item.description })),
    skills: orderedById(db.skills, skillIds).map((skill) => ({ name: skill.name, description: skill.description })),
  })
}

function pendingResults(agentId: string) {
  const agent = agentOr404(agentId)
  return (agent?.evals ?? []).map((item) => ({ evalId: item.id, status: "not_run" as const, evidence: null }))
}

export const agentHandlers = [
  http.get("/agents", () => HttpResponse.json(db.agents)),
  http.post("/agents", async ({ request }) => {
    const body = (await request.json()) as {
      name?: string
      roleKey?: string
      description?: string
      model?: { provider: string; name: string; config: Record<string, unknown> }
      budgets?: { maxIterations: number; maxMinutes: number; maxTokens: number }
      toolIds?: string[]
      skillIds?: string[]
      stackIds?: string[]
      zones?: string[]
    }
    if (!body.name || !body.roleKey || !body.description || !body.model || !body.budgets) {
      return error(422, "invalid", "name, roleKey, description, model, and budgets are required")
    }
    const invalid = modelError(body.model)
    if (invalid) return error(422, "invalid_config", invalid)
    const timestamp = now()
    const agent = {
      id: nid("agt"),
      name: body.name,
      roleKey: body.roleKey,
      description: body.description,
      model: body.model,
      budgets: body.budgets,
      activePromptVersionId: null,
      toolIds: body.toolIds ?? [],
      skillIds: body.skillIds ?? [],
      stackIds: body.stackIds ?? [],
      zones: body.zones ?? [],
      evals: [],
      createdAt: timestamp,
      updatedAt: timestamp,
    }
    db.agents.push(agent)
    return HttpResponse.json(agent, { status: 201 })
  }),
  http.get("/agents/:id/versions/:v/diff", ({ params, request }) => {
    const agent = agentOr404(String(params.id))
    if (!agent) return error(404, "not_found", "Agent not found")
    const version = Number(params.v)
    const against = Number(new URL(request.url).searchParams.get("against"))
    const left = db.versions.find((item) => item.agentId === agent.id && item.version === version)
    const right = db.versions.find((item) => item.agentId === agent.id && item.version === against)
    if (!left || !right) return error(404, "not_found", "Version not found")
    const keys = ["role", "goal", "instructions", "constraints", "output"] as const
    return HttpResponse.json({
      againstVersion: against,
      sections: keys.map((key) => ({
        path: key,
        before: right.sections[key],
        after: left.sections[key],
      })),
    })
  }),
  http.post("/agents/:id/versions/:v/activate", ({ params }) => {
    const agent = agentOr404(String(params.id))
    if (!agent) return error(404, "not_found", "Agent not found")
    const version = db.versions.find(
      (item) => item.agentId === agent.id && item.version === Number(params.v),
    )
    if (!version) return error(404, "not_found", "Version not found")
    const passed = agent.evals.every((item) =>
      version.evalResults.some((result) => result.evalId === item.id && result.status === "pass"),
    )
    if (agent.evals.length === 0 || !passed) {
      return error(409, "evals_required", "Every eval must pass before this version can be active")
    }
    agent.activePromptVersionId = version.id
    agent.updatedAt = now()
    return HttpResponse.json(version)
  }),
  http.get("/agents/:id/versions", ({ params }) => {
    const agent = agentOr404(String(params.id))
    if (!agent) return error(404, "not_found", "Agent not found")
    return HttpResponse.json(
      db.versions.filter((item) => item.agentId === agent.id).sort((a, b) => a.version - b.version),
    )
  }),
  http.post("/agents/:id/versions", async ({ params, request }) => {
    const agent = agentOr404(String(params.id))
    if (!agent) return error(404, "not_found", "Agent not found")
    const body = (await request.json()) as { sections?: (typeof db.versions)[number]["sections"] }
    if (!body.sections) return error(422, "invalid", "sections are required")
    const compiled = compileFor(body.sections, agent.toolIds, agent.skillIds, agent.stackIds)
    const previous = db.versions.filter((item) => item.agentId === agent.id)
    const version = {
      id: nid("pv"),
      agentId: agent.id,
      version: previous.reduce((max, item) => Math.max(max, item.version), 0) + 1,
      sections: body.sections,
      compiled: compiled.compiled,
      tokenCount: compiled.tokenCount,
      evalResults: pendingResults(agent.id),
      createdAt: now(),
    }
    db.versions.push(version)
    agent.updatedAt = now()
    return HttpResponse.json(version, { status: 201 })
  }),
  http.post("/agents/:id/compile-preview", async ({ params, request }) => {
    const agent = agentOr404(String(params.id))
    if (!agent) return error(404, "not_found", "Agent not found")
    const body = (await request.json()) as {
      sections?: (typeof db.versions)[number]["sections"]
      toolIds?: string[]
      skillIds?: string[]
      stackIds?: string[]
    }
    if (!body.sections || !body.toolIds || !body.skillIds || !body.stackIds) {
      return error(422, "invalid", "sections, toolIds, skillIds, and stackIds are required")
    }
    return HttpResponse.json(compileFor(body.sections, body.toolIds, body.skillIds, body.stackIds))
  }),
  http.get("/agents/:id", ({ params }) => {
    const agent = agentOr404(String(params.id))
    if (!agent) return error(404, "not_found", "Agent not found")
    return HttpResponse.json(agent)
  }),
  http.patch("/agents/:id", async ({ params, request }) => {
    const agent = agentOr404(String(params.id))
    if (!agent) return error(404, "not_found", "Agent not found")
    const body = (await request.json()) as Partial<typeof agent>
    if (body.model) {
      const invalid = modelError(body.model)
      if (invalid) return error(422, "invalid_config", invalid)
    }
    Object.assign(agent, body, { id: agent.id, updatedAt: now() })
    return HttpResponse.json(agent)
  }),
  http.delete("/agents/:id", ({ params }) => {
    const index = db.agents.findIndex((agent) => agent.id === String(params.id))
    if (index < 0) return error(404, "not_found", "Agent not found")
    const [removed] = db.agents.splice(index, 1)
    db.versions = db.versions.filter((item) => item.agentId !== removed.id)
    return new HttpResponse(null, { status: 204 })
  }),
  http.post("/agents/:id/versions/:v/evals/run", ({ params }) => {
    const agent = agentOr404(String(params.id))
    if (!agent) return error(404, "not_found", "Agent not found")
    const version = db.versions.find((item) => item.agentId === agent.id && item.version === Number(params.v))
    if (!version) return error(404, "not_found", "Version not found")
    if (agent.evals.length === 0) return error(422, "invalid", "Add an eval first")
    version.evalResults = agent.evals.map((item) => ({
      evalId: item.id,
      status: "pass" as const,
      evidence: "Mock eval passed.",
    }))
    return HttpResponse.json(version)
  }),
  http.post("/agents/:id/evals", async ({ params, request }) => {
    const agent = agentOr404(String(params.id))
    if (!agent) return error(404, "not_found", "Agent not found")
    const body = (await request.json()) as { name?: string; task?: string; criteria?: string[]; passRule?: string }
    if (!body.name || !body.task || !body.criteria?.length || !body.passRule) {
      return error(422, "invalid", "name, task, criteria, and passRule are required")
    }
    agent.evals.push({
      id: nid("eval"),
      name: body.name,
      task: body.task,
      criteria: body.criteria,
      passRule: body.passRule,
    })
    agent.updatedAt = now()
    return HttpResponse.json(agent, { status: 201 })
  }),
  http.delete("/agents/:id/evals/:evalId", ({ params }) => {
    const agent = agentOr404(String(params.id))
    if (!agent) return error(404, "not_found", "Agent not found")
    const index = agent.evals.findIndex((item) => item.id === String(params.evalId))
    if (index < 0) return error(404, "not_found", "Eval not found")
    agent.evals.splice(index, 1)
    agent.updatedAt = now()
    return HttpResponse.json(agent)
  }),
]
