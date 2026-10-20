import { modelId } from "@/lib/models/schema"

export type StatRun = {
  agentId: string
  model: { name: string }
  status: string
  summary?: unknown
  costUsd: number
}

export type OwnStat = {
  roleKey: string
  runs: number
  passed: number
  avgCostUsd?: number
  firstTryRate?: number
  suggested?: boolean
  reason?: string
}

export function ownStatsFor(
  modelName: string,
  agents: { id: string; roleKey: string }[],
  runs: StatRun[],
) {
  return [...new Set(agents.map((agent) => agent.roleKey))].flatMap((roleKey) => {
    const agentIds = new Set(agents.filter((agent) => agent.roleKey === roleKey).map((agent) => agent.id))
    const matched = runs.filter((run) => modelId(run.model.name) === modelId(modelName) && agentIds.has(run.agentId))
    if (matched.length === 0) return []
    const passed = matched.filter((run) => run.status === "completed" && run.summary)
    const avgCostUsd = passed.reduce((sum, run) => sum + run.costUsd, 0) / (passed.length || 1)
    return [{ roleKey, runs: matched.length, passed: passed.length, avgCostUsd, reason: matched.length >= 5 ? undefined : "not enough data yet" }]
  })
}

export function suggestedForRole(
  models: { name: string; ownStats: OwnStat[] }[],
  roleKey: string,
) {
  const ready = models.flatMap((model) => {
    const stat = model.ownStats.find((item) => item.roleKey === roleKey)
    if (!stat || stat.runs < 5) return []
    const rate = stat.firstTryRate ?? (stat.runs ? stat.passed / stat.runs : 0)
    return [{ name: model.name, rate, cost: stat.avgCostUsd ?? 0, suggested: Boolean(stat.suggested), reason: stat.reason }]
  })
  if (ready.length === 0) return null
  const marked = ready.find((item) => item.suggested)
  if (marked) return marked
  ready.sort((left, right) => right.rate - left.rate || left.cost - right.cost || left.name.localeCompare(right.name))
  const top = ready[0]
  const close = ready.filter((item) => top.rate - item.rate <= 0.1)
  close.sort((left, right) => left.cost - right.cost || left.name.localeCompare(right.name))
  return close[0] ?? null
}

export function bestForRole(
  models: { name: string; ownStats: OwnStat[] }[],
  roleKey: string,
) {
  const pick = suggestedForRole(models, roleKey)
  return pick ? [pick.name] : []
}
