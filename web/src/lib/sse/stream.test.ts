import { describe, expect, it } from "vitest"
import { readEventStream } from "@/lib/sse/stream"

describe("event stream", () => {
  it("resumes after the last seq without repeating it", async () => {
    const ids: number[] = []
    await readEventStream("http://localhost/runs/run_completed/events", 1, (frame) => {
      ids.push(frame.id)
    })
    expect(ids).toEqual([2])
  })
})
