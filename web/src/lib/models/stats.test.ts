import { describe, expect, it } from "vitest"
import { bestForRole, ownStatsFor } from "@/lib/models/stats"

const agents = [
  { id: "a1", roleKey: "frontend-engineer" },
  { id: "a2", roleKey: "frontend-engineer" },
]

describe("ownStatsFor", () => {
  it("counts runs and passed tasks for the model's role", () => {
    const stats = ownStatsFor("gpt-5", agents, [
      { agentId: "a1", model: { name: "gpt-5" }, status: "completed", summary: { ok: true }, costUsd: 1 },
      { agentId: "a1", model: { name: "gpt-5" }, status: "failed", costUsd: 2 },
      { agentId: "a2", model: { name: "gpt-4.1" }, status: "completed", summary: {}, costUsd: 3 },
    ])
    expect(stats).toEqual([{ roleKey: "frontend-engineer", runs: 2, passed: 1, avgCostUsd: 1 }])
  })
})

describe("bestForRole", () => {
  it("badges the highest pass rate once a model has five runs", () => {
    const models = [
      { name: "gpt-5", ownStats: [{ roleKey: "frontend-engineer", runs: 5, passed: 4 }] },
      { name: "gpt-4.1", ownStats: [{ roleKey: "frontend-engineer", runs: 5, passed: 2 }] },
      { name: "o3", ownStats: [{ roleKey: "frontend-engineer", runs: 4, passed: 4 }] },
    ]
    expect(bestForRole(models, "frontend-engineer")).toEqual(["gpt-5"])
  })
})
