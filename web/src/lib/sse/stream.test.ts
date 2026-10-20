import { describe, expect, it } from "vitest"
import { parseSseChunk, readEventStream } from "@/lib/sse/stream"
import { db } from "@/mocks/db"

describe("sse frames", () => {
  it("parses id, event, and data, and keeps a partial frame", () => {
    const chunk = "id: 1\nevent: RUN_STARTED\ndata: {\"seq\":1}\n\nid: 2\nevent: MODEL"
    const parsed = parseSseChunk(chunk)
    expect(parsed.frames).toEqual([{ id: 1, event: "RUN_STARTED", data: "{\"seq\":1}" }])
    expect(parsed.rest.startsWith("id: 2")).toBe(true)
  })
})

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

  it("keeps live deltas when the SSE id is 0 or the resume seq is later", async () => {
    const body = [
      `id: 0\nevent: MODEL_DELTA\ndata: ${JSON.stringify({ id: "delta_a_1", seq: 1_000_001, type: "MODEL_DELTA" })}\n\n`,
      `id: 1000002\nevent: MODEL_DELTA\ndata: ${JSON.stringify({ id: "delta_a_2", seq: 1_000_002, type: "MODEL_DELTA" })}\n\n`,
      `id: 2\nevent: MODEL_OUTPUT\ndata: ${JSON.stringify({ id: "e2", seq: 2, type: "MODEL_OUTPUT" })}\n\n`,
    ].join("")
    const original = globalThis.fetch
    globalThis.fetch = async () => new Response(body, { headers: { "Content-Type": "text/event-stream" } })
    try {
      const ids: string[] = []
      await readEventStream("http://localhost/runs/stream-delta/events", 2, (frame) => {
        ids.push((JSON.parse(frame.data) as { id: string }).id)
      })
      expect(ids).toEqual(["delta_a_1", "delta_a_2"])
    } finally {
      globalThis.fetch = original
    }
  })
})
