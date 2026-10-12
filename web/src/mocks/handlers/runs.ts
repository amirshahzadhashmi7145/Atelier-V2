import { http, HttpResponse } from "msw"
import { appendEvent, db, formatSse, nid, now, startLiveRun } from "@/mocks/db"

function error(status: number, code: string, message: string) {
  return HttpResponse.json({ code, message }, { status })
}

const terminal = new Set(["completed", "failed", "cancelled"])
const pageSize = 20

export const runHandlers = [
  http.get("/runs", ({ request }) => {
    const url = new URL(request.url)
    const agentId = url.searchParams.get("agentId")
    const status = url.searchParams.get("status")
    const page = Math.max(1, Number(url.searchParams.get("page") ?? "1") || 1)
    const filtered = db.runs.filter((run) => {
      if (agentId && run.agentId !== agentId) return false
      if (status && run.status !== status) return false
      return true
    })
    const start = (page - 1) * pageSize
    return HttpResponse.json({
      items: filtered.slice(start, start + pageSize),
      page,
      total: filtered.length,
    })
  }),
  http.post("/runs", async ({ request }) => {
    const body = (await request.json()) as {
      agentId?: string
      promptVersionId?: string
      model?: { provider: string; name: string }
      workspace?: { kind: "repo"; url: string } | { kind: "scaffold"; template: string }
      task?: string
      criteria?: string[]
      attachmentIds?: string[]
      budget?: (typeof db.runs)[number]["budget"]
    }
    const agent = db.agents.find((item) => item.id === body.agentId)
    if (!agent) return error(404, "not_found", "Agent not found")
    if (!body.workspace || !body.task) return error(422, "invalid", "workspace and task are required")
    const version = body.promptVersionId
      ? db.versions.find((item) => item.id === body.promptVersionId)
      : db.versions.find((item) => item.id === agent.activePromptVersionId) ??
        db.versions.find((item) => item.agentId === agent.id)
    if (!version) return error(422, "invalid", "Agent has no prompt version")
    const run = {
      id: nid("run"),
      agentId: agent.id,
      promptVersionId: version.id,
      model: body.model ?? { provider: agent.model.provider, name: agent.model.name },
      workspace: body.workspace,
      task: body.task,
      criteria: body.criteria ?? [],
      attachmentIds: body.attachmentIds ?? [],
      budget: body.budget ?? {
        maxIterations: db.runSettings.maxIterations,
        maxMinutes: db.runSettings.maxMinutes,
        // ponytail: token ceiling stays on the run record; the visible cap is spend
        maxTokens: 400000,
      },
      status: "queued" as const,
      iterations: 0,
      tokensIn: 0,
      tokensOut: 0,
      costUsd: 0,
      startedAt: now(),
    }
    db.runs.push(run)
    db.diffs[run.id] = []
    db.artifacts[run.id] = []
    startLiveRun(run.id)
    return HttpResponse.json(run, { status: 201 })
  }),
  http.get("/runs/:id/events", ({ params, request }) => {
    const run = db.runs.find((item) => item.id === String(params.id))
    if (!run) return error(404, "not_found", "Run not found")
    const after = Number(new URL(request.url).searchParams.get("after") ?? "0") || 0
    const pending = () => db.events.filter((item) => item.runId === run.id && item.seq > after)
    if (terminal.has(run.status)) {
      return new HttpResponse(pending().map(formatSse).join(""), {
        headers: { "Content-Type": "text/event-stream" },
      })
    }
    let sent = after
    let timer: ReturnType<typeof setInterval> | undefined
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      start(controller) {
        const push = () => {
          const fresh = db.events.filter((item) => item.runId === run.id && item.seq > sent)
          for (const item of fresh) {
            controller.enqueue(encoder.encode(formatSse(item)))
            sent = item.seq
          }
          const current = db.runs.find((item) => item.id === run.id)
          if (current && terminal.has(current.status) && fresh.length === 0) {
            if (timer) clearInterval(timer)
            controller.close()
          }
        }
        push()
        timer = setInterval(push, 200)
      },
      cancel() {
        if (timer) clearInterval(timer)
      },
    })
    return new HttpResponse(stream, {
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
    })
  }),
  http.post("/runs/:id/stop", ({ params }) => {
    const run = db.runs.find((item) => item.id === String(params.id))
    if (!run) return error(404, "not_found", "Run not found")
    if (terminal.has(run.status)) return error(409, "already_terminal", "Run is already finished")
    run.status = "cancelled"
    run.endedAt = now()
    appendEvent(run.id, "STATE_CHANGED", { status: "cancelled" })
    return HttpResponse.json(run)
  }),
  http.post("/runs/:id/client-tool-result", async ({ params, request }) => {
    const run = db.runs.find((item) => item.id === String(params.id))
    if (!run) return error(404, "not_found", "Run not found")
    if (run.status !== "waiting_client") return error(409, "not_waiting", "Run is not waiting on a client tool")
    const body = (await request.json()) as { requestId?: string; output?: Record<string, unknown>; error?: string | null }
    if (!body.requestId) return error(422, "invalid", "requestId is required")
    appendEvent(run.id, "TOOL_RESULT", { requestId: body.requestId, output: body.output ?? {}, error: body.error ?? null })
    run.status = "running"
    return HttpResponse.json(run)
  }),
  http.post("/runs/:id/answer", async ({ params, request }) => {
    const run = db.runs.find((item) => item.id === String(params.id))
    if (!run) return error(404, "not_found", "Run not found")
    if (run.status !== "waiting_user") return error(409, "not_waiting", "Run is not waiting on the user")
    const body = (await request.json()) as { text?: string }
    if (!body.text) return error(422, "invalid", "text is required")
    appendEvent(run.id, "STATE_CHANGED", { status: "running", answer: body.text })
    run.status = "running"
    return HttpResponse.json(run)
  }),
  http.get("/runs/:id/diff", ({ params }) => {
    const run = db.runs.find((item) => item.id === String(params.id))
    if (!run) return error(404, "not_found", "Run not found")
    return HttpResponse.json({ files: db.diffs[run.id] ?? [] })
  }),
  http.get("/runs/:id/artifacts", ({ params }) => {
    const run = db.runs.find((item) => item.id === String(params.id))
    if (!run) return error(404, "not_found", "Run not found")
    return HttpResponse.json(db.artifacts[run.id] ?? [])
  }),
  http.get("/runs/:id", ({ params }) => {
    const run = db.runs.find((item) => item.id === String(params.id))
    if (!run) return error(404, "not_found", "Run not found")
    return HttpResponse.json(run)
  }),
]
