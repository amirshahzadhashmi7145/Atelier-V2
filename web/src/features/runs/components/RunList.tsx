"use client"

import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { PageHeader } from "@/components/shared/PageHeader"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { listRunAgents, listRuns } from "@/features/runs/api"
import { formatElapsed } from "@/features/runs/components/RunCards"
import { queryKeys } from "@/lib/api/query-keys"
import { isTerminal, type Run } from "@/lib/runs/events"
import { useUiStore } from "@/stores/ui-store"

const pageSize = 20

export function RunList() {
  const agentId = useUiStore((state) => state.runListAgent)
  const status = useUiStore((state) => state.runListStatus)
  const page = useUiStore((state) => state.runListPage)
  const setRunList = useUiStore((state) => state.setRunList)
  const agents = useQuery({ queryKey: queryKeys.agents, queryFn: listRunAgents })
  const query = useQuery({
    queryKey: queryKeys.runs(page, agentId, status),
    queryFn: () =>
      listRuns({
        page,
        agentId: agentId || undefined,
        status: status ? (status as Run["status"]) : undefined,
      }),
    refetchInterval: (current) => (current.state.data?.items.some((run) => !isTerminal(run.status)) ? 2000 : false),
  })
  const names = new Map((agents.data ?? []).map((agent) => [agent.id, agent.name]))
  const pages = Math.max(1, Math.ceil((query.data?.total ?? 0) / pageSize))

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-3">
        <PageHeader title="Runs" description="Past and live runs." />
        <Button nativeButton={false} render={<Link href="/runs/new" />}>
          New run
        </Button>
      </div>
      <div className="flex flex-wrap gap-3">
        <label className="flex flex-col gap-1 text-sm" htmlFor="run-filter-agent">
          Agent
          <select
            id="run-filter-agent"
            className="h-8 rounded-lg border border-input bg-background px-2"
            value={agentId}
            onChange={(event) => setRunList({ runListAgent: event.target.value, runListPage: 1 })}
          >
            <option value="">All agents</option>
            {(agents.data ?? []).map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm" htmlFor="run-filter-state">
          State
          <select
            id="run-filter-state"
            className="h-8 rounded-lg border border-input bg-background px-2"
            value={status}
            onChange={(event) => setRunList({ runListStatus: event.target.value, runListPage: 1 })}
          >
            <option value="">All states</option>
            {["queued", "running", "waiting_client", "waiting_user", "completed", "failed", "cancelled"].map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
      </div>
      {query.isPending ? <Skeleton className="h-40 w-full" /> : null}
      {query.isError ? (
        <ErrorState message={query.error instanceof Error ? query.error.message : "Could not load runs"} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data && query.data.items.length === 0 ? (
        <EmptyState
          title={agentId || status ? "No matching runs" : "No runs yet"}
          description="Start a run when an agent has an active prompt."
        />
      ) : null}
      {query.data && query.data.items.length > 0 ? (
        <>
          <div className="overflow-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b">
                  {["Agent", "Task", "State", "Cost", "Duration", "Model", "Prompt version", "Started"].map((heading) => (
                    <th key={heading} className="px-2 py-2 font-medium">
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {query.data.items.map((run) => (
                  <tr key={run.id} className="border-b">
                    <td className="px-2 py-2">{names.get(run.agentId) ?? run.agentId}</td>
                    <td className="px-2 py-2">
                      <Link href={`/runs/${run.id}`} className="underline">
                        {run.task.split("\n")[0]}
                      </Link>
                    </td>
                    <td className="px-2 py-2">{run.status}</td>
                    <td className="px-2 py-2">${run.costUsd.toFixed(2)}</td>
                    <td className="px-2 py-2">{formatElapsed(run.startedAt, run.endedAt)}</td>
                    <td className="px-2 py-2">{run.model.name}</td>
                    <td className="px-2 py-2">{run.promptVersionId}</td>
                    <td className="px-2 py-2">{new Date(run.startedAt).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" disabled={page <= 1} onClick={() => setRunList({ runListPage: page - 1 })}>
              Previous
            </Button>
            <span className="text-sm">
              Page {page} of {pages}
            </span>
            <Button variant="outline" disabled={page >= pages} onClick={() => setRunList({ runListPage: page + 1 })}>
              Next
            </Button>
          </div>
        </>
      ) : null}
    </div>
  )
}
