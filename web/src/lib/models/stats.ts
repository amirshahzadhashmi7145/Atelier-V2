export type StatRun = {
  agentId: string
  model: { name: string }
  status: string
  summary?: unknown
  costUsd: number
}

export function ownStatsFor(
  modelName: string,
  agents: { id: string; roleKey: string }[],
  runs: StatRun[],
) {
  return [...new Set(agents.map((agent) => agent.roleKey))].flatMap((roleKey) => {
    const agentIds = new Set(agents.filter((agent) => agent.roleKey === roleKey).map((agent) => agent.id))
    const matched = runs.filter((run) => run.model.name === modelName && agentIds.has(run.agentId))
    if (matched.length === 0) return []
    const passed = matched.filter((run) => run.status === "completed" && run.summary)
    const avgCostUsd = passed.reduce((sum, run) => sum + run.costUsd, 0) / (passed.length || 1)
    return [{ roleKey, runs: matched.length, passed: passed.length, avgCostUsd }]
  })
}

export function bestForRole(
  models: { name: string; ownStats: { roleKey: string; runs: number; passed: number }[] }[],
  roleKey: string,
) {
  const scored = models.flatMap((model) => {
    const stat = model.ownStats.find((item) => item.roleKey === roleKey)
    if (!stat || stat.runs < 5) return []
    return [{ name: model.name, rate: stat.passed / stat.runs }]
  })
  const top = Math.max(-1, ...scored.map((item) => item.rate))
  return scored.filter((item) => item.rate === top).map((item) => item.name)
}
