"use client"

import { useEffect } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { getRun } from "@/features/runs/api"
import { apiBaseUrl } from "@/lib/api/client"
import { queryKeys } from "@/lib/api/query-keys"
import { isTerminal, lastSeq, writeRunEvent, type RunEvent } from "@/lib/runs/events"
import { readEventStream } from "@/lib/sse/stream"

function sleep(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    const abort = () => {
      clearTimeout(timer)
      reject(new DOMException("Aborted", "AbortError"))
    }
    if (signal.aborted) abort()
    else signal.addEventListener("abort", abort, { once: true })
  })
}

export function useRunEvents(id: string) {
  const queryClient = useQueryClient()
  const run = useQuery({ queryKey: queryKeys.runs.detail(id), queryFn: () => getRun(id) })
  const events = useQuery({
    queryKey: queryKeys.runs.events(id),
    queryFn: () => queryClient.getQueryData<RunEvent[]>(queryKeys.runs.events(id)) ?? [],
    initialData: [] as RunEvent[],
    staleTime: Infinity,
  })

  useEffect(() => {
    if (!run.isSuccess) return
    const controller = new AbortController()
    let stopped = false
    let delay = 500
    const pump = async () => {
      while (!stopped) {
        const cached = queryClient.getQueryData<RunEvent[]>(queryKeys.runs.events(id)) ?? []
        try {
          await readEventStream(
            `${apiBaseUrl()}/runs/${id}/events`,
            lastSeq(cached),
            (frame) => writeRunEvent(queryClient, JSON.parse(frame.data) as RunEvent),
            controller.signal,
          )
          delay = 500
        } catch (error) {
          if (stopped || (error instanceof DOMException && error.name === "AbortError")) return
          try {
            await sleep(delay, controller.signal)
          } catch {
            return
          }
          delay = Math.min(delay * 2, 8000)
          continue
        }
        const current = queryClient.getQueryData<{ status: string }>(queryKeys.runs.detail(id))
        if (!current || isTerminal(current.status)) return
        try {
          await sleep(delay, controller.signal)
        } catch {
          return
        }
      }
    }
    void pump()
    return () => {
      stopped = true
      controller.abort()
    }
  }, [id, queryClient, run.isSuccess])

  return { run, events: events.data }
}
