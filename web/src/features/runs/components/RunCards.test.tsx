import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { LogRow, eventSummary } from "@/features/runs/components/ActivityLog"
import { ClarificationCard, StatusCard } from "@/features/runs/components/RunCards"
import type { Run, RunEvent } from "@/lib/runs/events"

function event(type: RunEvent["type"], payload: Record<string, unknown> = {}, cost?: RunEvent["cost"]): RunEvent {
  return {
    id: type,
    runId: "run_1",
    seq: 1,
    type,
    actor: { kind: "agent", role: "frontend-engineer" },
    payload,
    cost,
    occurredAt: "2026-10-12T12:00:00.000Z",
  }
}

const samples: RunEvent[] = [
  event("RUN_STARTED"),
  event("MODEL_CALLED", {}, { inputTokens: 10, outputTokens: 4, usd: 0.12 }),
  event("TOOL_CALLED", { name: "shell" }),
  event("TOOL_RESULT", { name: "shell" }),
  event("TOOL_REFUSED", { name: "package_install" }),
  event("SKILL_LOADED", { name: "react-best-practices" }),
  event("CLIENT_TOOL_REQUESTED", { prompt: "Use this heading?" }),
  event("CLARIFICATION_RAISED", { question: "Which button label should the page use?" }),
  event("STATE_CHANGED", { status: "running" }),
  event("RUN_COMPLETED"),
  event("RUN_FAILED", { text: "Sandbox exited" }),
]

const run: Run = {
  id: "run_1",
  agentId: "agt",
  promptVersionId: "pv_1",
  model: { provider: "openai", name: "gpt-5" },
  workspace: { kind: "scaffold", template: "vite-react-ts" },
  task: "Add a button",
  criteria: [],
  attachmentIds: [],
  status: "running",
  iterations: 1,
  tokensIn: 100,
  tokensOut: 40,
  costUsd: 2.5,
  startedAt: "2026-10-12T12:00:00.000Z",
}

describe("log row", () => {
  it("renders a one-line summary for every event type", () => {
    for (const sample of samples) {
      const { unmount } = render(<LogRow event={sample} />)
      expect(screen.getAllByText(eventSummary(sample)).length).toBeGreaterThan(0)
      unmount()
    }
    expect(screen.queryByText("$0.120")).toBeNull()
    const { getByText } = render(<LogRow event={samples[1]!} />)
    expect(getByText("$0.120")).toBeTruthy()
  })
})

describe("status card", () => {
  it("fills the spend bar from cost over the cap", () => {
    render(<StatusCard run={run} capUsd={5} stopping={false} onStop={vi.fn()} />)
    const bar = screen.getByRole("progressbar", { name: "Spend of cap" })
    expect(bar.getAttribute("aria-valuenow")).toBe("2.5")
    expect(bar.getAttribute("aria-valuemax")).toBe("5")
    expect(bar.firstElementChild?.getAttribute("style")).toContain("50%")
  })
})

describe("clarification card", () => {
  it("submits the typed answer", () => {
    const onSubmit = vi.fn()
    render(<ClarificationCard question="Which button label should the page use?" pending={false} onSubmit={onSubmit} />)
    fireEvent.change(screen.getByLabelText("Answer"), { target: { value: "Go" } })
    fireEvent.click(screen.getByRole("button", { name: "Send answer" }))
    expect(onSubmit).toHaveBeenCalledWith("Go")
  })
})
