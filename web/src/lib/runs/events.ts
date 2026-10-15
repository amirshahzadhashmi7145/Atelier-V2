import type { QueryClient } from "@tanstack/react-query"
import type { components } from "@/lib/api/generated/types"
import { queryKeys } from "@/lib/api/query-keys"

export type Run = components["schemas"]["Run"]
export type RunEvent = components["schemas"]["Event"]

const terminal = new Set(["completed", "failed", "cancelled"])

export function isTerminal(status: string) {
  return terminal.has(status)
}

export function lastSeq(events: { seq: number; type?: string }[]) {
  return events.reduce((max, item) => (item.type === "MODEL_DELTA" ? max : Math.max(max, item.seq)), 0)
}

export function appendBySeq(events: RunEvent[], event: RunEvent): RunEvent[] {
  const index = events.findIndex((item) => item.id === event.id || item.seq === event.seq)
  if (index === -1) return [...events, event].sort((a, b) => a.seq - b.seq)
  const current = events[index]
  if (current.id === event.id && current.seq === event.seq && current.type === event.type) return events
  const copy = events.slice()
  copy[index] = event
  return copy.sort((a, b) => a.seq - b.seq)
}

export function applyStatus(run: Run, event: RunEvent): Run {
  const cost = event.cost
    ? {
        ...run,
        tokensIn: run.tokensIn + event.cost.inputTokens,
        tokensOut: run.tokensOut + event.cost.outputTokens,
        costUsd: Number((run.costUsd + event.cost.usd).toFixed(4)),
      }
    : run
  if (event.type === "STATE_CHANGED" && typeof event.payload.status === "string") {
    return { ...cost, status: event.payload.status as Run["status"] }
  }
  if (event.type === "CLIENT_TOOL_REQUESTED") return { ...cost, status: "waiting_client" }
  if (event.type === "CLARIFICATION_RAISED") return { ...cost, status: "waiting_user" }
  if (event.type === "RUN_COMPLETED") {
    const summary = event.payload.summary as Run["summary"]
    return {
      ...cost,
      status: "completed",
      endedAt: event.occurredAt,
      summary: summary ?? cost.summary,
      prUrl: typeof event.payload.prUrl === "string" ? event.payload.prUrl : cost.prUrl,
      previewUrl: typeof event.payload.previewUrl === "string" ? event.payload.previewUrl : cost.previewUrl,
      branch: typeof event.payload.branch === "string" ? event.payload.branch : cost.branch,
    }
  }
  if (event.type === "RUN_FAILED") {
    const cause = event.payload.cause
    return {
      ...cost,
      status: "failed",
      endedAt: event.occurredAt,
      terminalCause: isCause(cause) ? cause : cost.terminalCause,
    }
  }
  return cost
}

function isCause(value: unknown): value is NonNullable<Run["terminalCause"]> {
  return value === "budget" || value === "loop" || value === "timeout" || value === "error" || value === "escalated"
}

export function writeRunEvent(queryClient: QueryClient, event: RunEvent) {
  const key = queryKeys.runs.events(event.runId)
  const current = queryClient.getQueryData<RunEvent[]>(key) ?? []
  let next = appendBySeq(current, event)
  if (event.type === "MODEL_OUTPUT") {
    const callId = event.payload.modelCallId ?? event.payload.callId
    next = next.filter((item) => item.type !== "MODEL_DELTA" || (item.payload.modelCallId ?? item.payload.callId) !== callId)
  }
  if (next !== current) queryClient.setQueryData(key, next)
  if (event.type === "STATE_CHANGED" || event.type === "RUN_COMPLETED" || event.type === "RUN_FAILED" || event.type === "CLIENT_TOOL_REQUESTED" || event.type === "CLARIFICATION_RAISED" || event.cost) {
    queryClient.setQueryData<Run>(queryKeys.runs.detail(event.runId), (run) => (run ? applyStatus(run, event) : run))
  }
  if (event.type === "TOOL_RESULT" || event.type === "RUN_COMPLETED") {
    void queryClient.invalidateQueries({ queryKey: queryKeys.runs.artifacts(event.runId) })
  }
}
