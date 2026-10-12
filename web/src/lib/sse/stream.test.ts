import { describe, expect, it } from "vitest"
import { readEventStream } from "@/lib/sse/stream"
import { db } from "@/mocks/db"

describe("event stream", () => {
  it("resumes after the last seq without repeating it", async () => {
    db.runs.push({
      id: "run_completed",
      agentId: "agt",
      promptVersionId: "pv",
      model: { provider: "openai", name: "gpt-5" },
      workspace: { kind: "repo", url: "https://example.com/repo" },
      task: "Add a button",
      criteria: [],
      attachmentIds: [],
      budget: { maxIterations: 1, maxMinutes: 1, maxTokens: 1 },
      status: "completed",
      iterations: 1,
      tokensIn: 1,
      tokensOut: 1,
      costUsd: 0,
      startedAt: "2026-10-02T12:00:00.000Z",
    })
    db.events.push(
      {
        id: "e1",
        runId: "run_completed",
        seq: 1,
        type: "RUN_STARTED",
        actor: { kind: "system" },
        payload: {},
        occurredAt: "2026-10-02T12:00:00.000Z",
      },
      {
        id: "e2",
        runId: "run_completed",
        seq: 2,
        type: "RUN_COMPLETED",
        actor: { kind: "system" },
        payload: {},
        occurredAt: "2026-10-02T12:05:00.000Z",
      },
    )
    const ids: number[] = []
    await readEventStream("http://localhost/runs/run_completed/events", 1, (frame) => {
      ids.push(frame.id)
    })
    expect(ids).toEqual([2])
  })
})
