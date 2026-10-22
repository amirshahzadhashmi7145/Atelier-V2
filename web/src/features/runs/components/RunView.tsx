"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { PointerEvent as ReactPointerEvent } from "react"
import { toast } from "sonner"
import { ErrorState } from "@/components/shared/ErrorState"
import { PageHeader } from "@/components/shared/PageHeader"
import { Skeleton } from "@/components/ui/skeleton"
import { answerRun, getSpendCap, listRunArtifacts, respondToClientTool, stopRun } from "@/features/runs/api"
import { ActivityLog } from "@/features/runs/components/ActivityLog"
import { RunCentre } from "@/features/runs/components/RunCentre"
import { ClarificationCard, ClientToolCard, ResultCard, StatusCard } from "@/features/runs/components/RunCards"
import { useRunEvents } from "@/features/runs/hooks/useRunEvents"
import { queryKeys } from "@/lib/api/query-keys"
import { isTerminal, type RunEvent } from "@/lib/runs/events"
import { useUiStore } from "@/stores/ui-store"

function latest(events: RunEvent[], type: RunEvent["type"]) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (events[index]?.type === type) return events[index]
  }
  return undefined
}

export function RunView({ id, embedded }: { id: string; embedded?: boolean }) {
  const queryClient = useQueryClient()
  const { run, events } = useRunEvents(id)
  const cap = useQuery({ queryKey: queryKeys.runSettings, queryFn: getSpendCap })
  const artifacts = useQuery({ queryKey: queryKeys.runs.artifacts(id), queryFn: () => listRunArtifacts(id) })
  const leftPane = useUiStore((state) => state.leftPane)
  const rightPane = useUiStore((state) => state.rightPane)
  const setPane = useUiStore((state) => state.setPane)
  const fail = (error: unknown) => toast.error(error instanceof Error ? error.message : "Request failed")
  const stop = useMutation({
    mutationFn: () => stopRun(id),
    onSuccess: (next) => queryClient.setQueryData(queryKeys.runs.detail(id), next),
    onError: fail,
  })
  const answer = useMutation({
    mutationFn: (text: string) => answerRun(id, text),
    onSuccess: (next) => queryClient.setQueryData(queryKeys.runs.detail(id), next),
    onError: fail,
  })
  const respond = useMutation({
    mutationFn: () => {
      const request = latest(events, "CLIENT_TOOL_REQUESTED")
      const requestId = String(request?.payload.requestId ?? "")
      return respondToClientTool(id, requestId)
    },
    onSuccess: (next) => queryClient.setQueryData(queryKeys.runs.detail(id), next),
    onError: fail,
  })

  if (run.isPending) return <Skeleton className="h-80 w-full" />
  if (run.isError || !run.data) {
    return <ErrorState message={run.error instanceof Error ? run.error.message : "Run not found"} onRetry={() => void run.refetch()} />
  }

  const current = run.data
  const terminal = isTerminal(current.status)
  const question = latest(events, "CLARIFICATION_RAISED")
  const clientTool = latest(events, "CLIENT_TOOL_REQUESTED")
  const zip = artifacts.data?.find((item) => item.kind === "zip")

  const drag = (side: "left" | "right", event: ReactPointerEvent<HTMLDivElement>) => {
    const startX = event.clientX
    const start = side === "left" ? leftPane : rightPane
    const move = (ev: PointerEvent) => {
      const delta = ev.clientX - startX
      const width = Math.min(640, Math.max(240, side === "left" ? start + delta : start - delta))
      setPane(side, width)
    }
    const up = () => {
      window.removeEventListener("pointermove", move)
      window.removeEventListener("pointerup", up)
    }
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", up)
  }

  return (
    <div className={embedded ? "flex max-h-[60vh] min-h-[24rem] flex-col gap-3 overflow-auto" : "flex h-[calc(100dvh-8rem)] min-h-[32rem] flex-col gap-3"}>
      <PageHeader title="Run" description={current.task.split("\n")[0] ?? current.task} />
      <div className="flex min-h-0 flex-1">
        <div className="min-h-0 shrink-0 overflow-hidden border" style={{ width: leftPane }}>
          <ActivityLog events={events} />
        </div>
        <div className="w-1.5 shrink-0 cursor-col-resize bg-border" onPointerDown={(event) => drag("left", event)} />
        <div className="min-h-0 min-w-0 flex-1 border">
          <RunCentre id={id} previewUrl={current.previewUrl} />
        </div>
        <div className="w-1.5 shrink-0 cursor-col-resize bg-border" onPointerDown={(event) => drag("right", event)} />
        <div className="flex min-h-0 shrink-0 flex-col gap-3 overflow-auto" style={{ width: rightPane }}>
          {!terminal && current.status === "waiting_client" && clientTool ? (
            <ClientToolCard
              prompt={String(clientTool.payload.prompt ?? clientTool.payload.name ?? "Respond")}
              pending={respond.isPending}
              onRespond={() => respond.mutate()}
            />
          ) : null}
          {!terminal && current.status === "waiting_user" && question ? (
            <ClarificationCard
              question={String(question.payload.question ?? "")}
              pending={answer.isPending}
              onSubmit={(text) => answer.mutate(text)}
            />
          ) : null}
          {terminal ? (
            <ResultCard run={current} events={events} zipUrl={zip?.url} />
          ) : (
            <StatusCard run={current} capUsd={cap.data?.maxSpendPerRunUsd ?? 0} stopping={stop.isPending} onStop={() => stop.mutate()} />
          )}
        </div>
      </div>
    </div>
  )
}
