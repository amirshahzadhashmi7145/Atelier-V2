import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it } from "vitest"
import { queryKeys } from "@/lib/api/query-keys"
import { appendBySeq, applyStatus, lastSeq, writeRunEvent, type Run, type RunEvent } from "@/lib/runs/events"

function event(seq: number, type: RunEvent["type"], payload: Record<string, unknown> = {}): RunEvent {
  return {
    id: `evt_${seq}`,
    runId: "run_1",
    seq,
    type,
    actor: { kind: "system" },
    payload,
    occurredAt: "2026-10-12T12:00:00.000Z",
  }
}

const run: Run = {
  id: "run_1",
  agentId: "agt",
  promptVersionId: "pv",
  model: { provider: "openai", name: "gpt-5" },
  workspace: { kind: "repo", url: "https://example.com/repo" },
  task: "Add a button",
  criteria: [],
  attachmentIds: [],
  status: "running",
  iterations: 0,
  tokensIn: 0,
  tokensOut: 0,
  costUsd: 0,
  startedAt: "2026-10-12T12:00:00.000Z",
}

describe("run event cache", () => {
  it("keeps one row per seq and resumes from the last", () => {
    const first = appendBySeq([], event(1, "RUN_STARTED"))
    const again = appendBySeq(first, event(1, "RUN_STARTED"))
    const second = appendBySeq(again, event(2, "MODEL_CALLED"))
    expect(again).toBe(first)
    expect(second.map((item) => item.seq)).toEqual([1, 2])
    expect(lastSeq(second)).toBe(2)
  })

  it("moves the run through waiting and terminal states", () => {
    const waiting = applyStatus(run, event(1, "CLARIFICATION_RAISED", { question: "Which label?" }))
    expect(waiting.status).toBe("waiting_user")
    const done = applyStatus(waiting, event(2, "RUN_COMPLETED", { summary: { description: "Done", filesChanged: [], dependencies: [], criteria: [], assumptions: [], followUps: [] } }))
    expect(done.status).toBe("completed")
    expect(done.summary?.description).toBe("Done")
    const failed = applyStatus(run, event(3, "RUN_FAILED", { cause: "error", text: "Sandbox exited" }))
    expect(failed.status).toBe("failed")
    expect(failed.terminalCause).toBe("error")
  })

  it("writes a seq once into the query cache", () => {
    const client = new QueryClient()
    client.setQueryData(queryKeys.runs.detail("run_1"), run)
    client.setQueryData(queryKeys.runs.events("run_1"), [])
    writeRunEvent(client, event(1, "STATE_CHANGED", { status: "running" }))
    writeRunEvent(client, event(1, "STATE_CHANGED", { status: "running" }))
    expect(client.getQueryData<RunEvent[]>(queryKeys.runs.events("run_1"))?.map((item) => item.seq)).toEqual([1])
    expect(client.getQueryData<Run>(queryKeys.runs.detail("run_1"))?.status).toBe("running")
  })
})
