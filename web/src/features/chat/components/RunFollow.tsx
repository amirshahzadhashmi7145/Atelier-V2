"use client"

import { useState, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { answerChat, getChatRun, postMessage, type ChatMessage, type Run } from "@/features/chat/api"
import { queryKeys } from "@/lib/api/query-keys"
import { isTerminal } from "@/lib/runs/events"
import { Elapsed, LiveText } from "./LiveText"

function formatElapsed(startedAt: string, endedAt?: string) {
  const end = endedAt ? Date.parse(endedAt) : Date.now()
  const seconds = Math.max(0, Math.floor((end - Date.parse(startedAt)) / 1000))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`
}

const CAUSE_LABEL: Record<string, string> = {
  budget: "spend cap reached",
  loop: "the agent looped",
  timeout: "the run timed out",
  error: "an error stopped the run",
  escalated: "escalated to you",
}

function RunVitals({ run }: { run: Run }) {
  const model = run.actualModel?.name ?? run.model.name
  return (
    <p className="flex flex-wrap gap-x-2 text-xs text-muted-foreground" data-run-vitals>
      <span>
        <Elapsed since={Date.parse(run.startedAt)} />
      </span>
      <span>turn {run.iterations}</span>
      <span>{run.tokensIn + run.tokensOut} tokens</span>
      <span>${run.costUsd.toFixed(2)}</span>
      <span>
        {model}
        {run.backupUsed ? " (backup)" : ""}
      </span>
    </p>
  )
}

export function RunFollow({
  message,
  renderRun,
  streaming,
  prior,
  onActivity,
}: {
  message: ChatMessage
  renderRun?: (id: string) => ReactNode
  streaming?: boolean
  prior?: string
  onActivity?: () => void
}) {
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState(false)
  const [answer, setAnswer] = useState("")
  const runId = message.runId ?? ""
  const run = useQuery({
    queryKey: queryKeys.runs.detail(runId),
    queryFn: () => getChatRun(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => (query.state.data && isTerminal(query.state.data.status) ? false : 1000),
  })
  const reply = useMutation({
    mutationFn: () => answerChat(runId, answer),
    onSuccess: async () => {
      setAnswer("")
      await queryClient.invalidateQueries({ queryKey: queryKeys.runs.detail(runId) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.messages(message.projectId) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.needs(message.projectId) })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not send the answer"),
  })
  const retry = useMutation({
    mutationFn: () => {
      // `||` not `??`: prior is "" (not nullish) for runs with no owning user
      // message, and an empty base must fall back to the message text so the
      // retry never sends only "Previous attempt failed: …" with no task.
      const base = (prior || message.text).split("\n\nPrevious attempt failed:")[0]?.trim() || message.text
      const note = (run.data?.terminalCause ?? "error").slice(0, 80)
      return postMessage(message.projectId, `${base}\n\nPrevious attempt failed: ${note}`)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.messages(message.projectId) })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not try again"),
  })
  const runModel = run.data?.model
  if (streaming) {
    if (!run.data || isTerminal(run.data.status)) return null
    return (
      <div className="flex flex-col gap-2">
        <LiveText key={runId} runId={runId} model={runModel} onActivity={onActivity} />
        <RunVitals run={run.data} />
        <Button type="button" variant="outline" className="w-fit" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "Hide details" : "Details"}
        </Button>
        {expanded && renderRun ? <div className="min-w-0 overflow-auto">{renderRun(runId)}</div> : null}
      </div>
    )
  }
  if (!run.data) return null
  if (message.role === "agent" && run.data.status === "failed") {
    const cause = run.data.terminalCause
    return (
      <div className="flex flex-col gap-2 rounded border border-destructive/50 bg-destructive/10 p-2 text-sm">
        <p className="font-medium text-destructive">Run failed{cause ? ` — ${CAUSE_LABEL[cause] ?? cause}` : ""}</p>
        <p className="text-xs text-muted-foreground">
          ${run.data.costUsd.toFixed(2)} · {formatElapsed(run.data.startedAt, run.data.endedAt)}
        </p>
        <Button type="button" variant="outline" className="w-fit" disabled={retry.isPending} onClick={() => retry.mutate()}>
          {retry.isPending ? "Trying…" : "Try again"}
        </Button>
      </div>
    )
  }
  if (message.role === "agent" && run.data.status === "waiting_user") {
    return (
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          if (answer.trim()) reply.mutate()
        }}
      >
        <label className="sr-only" htmlFor={`answer-${runId}`}>
          Answer
        </label>
        <input id={`answer-${runId}`} className="flex-1 rounded border px-2 py-1" value={answer} onChange={(event) => setAnswer(event.target.value)} />
        <Button type="submit" disabled={reply.isPending}>
          Send answer
        </Button>
      </form>
    )
  }
  if (message.role === "agent" && run.data.status === "completed" && run.data.summary) {
    const summary = run.data.summary
    const description = summary.description?.trim()
    const criteria = (summary.criteria ?? []).filter((item) => item.text)
    return (
      <div className="flex flex-col gap-1 text-sm">
        {description && description !== message.text.trim() ? <p className="text-muted-foreground">{description}</p> : null}
        <p>Files changed: {summary.filesChanged.join(", ") || "none"}</p>
        {criteria.length ? (
          <ul className="flex flex-col gap-0.5 text-xs text-muted-foreground">
            {criteria.map((item) => (
              <li key={item.text}>
                ✓ {item.text}
                {item.evidence ? (
                  item.evidence.startsWith("http") ? (
                    <>
                      {" — "}
                      <a className="underline" href={item.evidence} target="_blank" rel="noreferrer">
                        evidence
                      </a>
                    </>
                  ) : (
                    ` — ${item.evidence}`
                  )
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
        <p className="flex flex-wrap gap-x-2 text-xs text-muted-foreground">
          {run.data.branch ? <span>branch {run.data.branch}</span> : null}
          <span>${run.data.costUsd.toFixed(2)}</span>
          <span>{formatElapsed(run.data.startedAt, run.data.endedAt)}</span>
          {run.data.actualModel?.name ? (
            <span>
              {run.data.actualModel.name}
              {run.data.backupUsed ? " (backup)" : ""}
            </span>
          ) : null}
        </p>
        {run.data.previewUrl ? (
          <a className="underline" href={run.data.previewUrl}>
            Preview
          </a>
        ) : null}
        {run.data.prUrl ? (
          <a className="underline" href={run.data.prUrl}>
            Pull request
          </a>
        ) : null}
      </div>
    )
  }
  return null
}
