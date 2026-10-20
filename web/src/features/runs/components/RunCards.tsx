"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { isTerminal, type Run, type RunEvent } from "@/lib/runs/events"

export function formatElapsed(startedAt: string, endedAt?: string) {
  const end = endedAt ? Date.parse(endedAt) : Date.now()
  const seconds = Math.max(0, Math.floor((end - Date.parse(startedAt)) / 1000))
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`
}

export function StatusCard({
  run,
  capUsd,
  stopping,
  onStop,
}: {
  run: Run
  capUsd: number
  stopping: boolean
  onStop: () => void
}) {
  const [now, setNow] = useState(0)
  const [confirming, setConfirming] = useState(false)
  useEffect(() => {
    if (isTerminal(run.status)) return
    const timer = setInterval(() => setNow((value) => value + 1), 1000)
    return () => clearInterval(timer)
  }, [run.status])
  const ratio = capUsd > 0 ? Math.min(100, (run.costUsd / capUsd) * 100) : 0
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Status
          <Badge>{run.status}</Badge>
        </CardTitle>
        <CardDescription>
          {formatElapsed(run.startedAt, run.endedAt)}
          <span className="sr-only">{now}</span>
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm">
          {run.tokensIn + run.tokensOut} tokens · {run.model.name} · {run.promptVersionId}
        </p>
        <div
          role="progressbar"
          aria-label="Spend of cap"
          aria-valuemin={0}
          aria-valuemax={capUsd}
          aria-valuenow={run.costUsd}
          className="h-2 overflow-hidden rounded-full bg-muted"
        >
          <div className="h-full bg-primary" style={{ width: `${ratio}%` }} />
        </div>
        <p className="text-sm text-muted-foreground">
          ${run.costUsd.toFixed(2)} of ${capUsd.toFixed(2)}
          {run.costSource === "openhands" ? " · cost from the OpenHands process" : ""}
        </p>
        {isTerminal(run.status) ? null : confirming ? (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={stopping} onClick={onStop}>
              {stopping ? "Stopping…" : "Stop now"}
            </Button>
            <Button variant="outline" onClick={() => setConfirming(false)}>
              Keep running
            </Button>
          </div>
        ) : (
          <Button variant="outline" onClick={() => setConfirming(true)}>
            Stop
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

export function ClarificationCard({
  question,
  pending,
  onSubmit,
}: {
  question: string
  pending: boolean
  onSubmit: (text: string) => void
}) {
  const [text, setText] = useState("")
  return (
    <Card>
      <CardHeader>
        <CardTitle>Clarification</CardTitle>
        <CardDescription>{question}</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            onSubmit(text.trim())
          }}
        >
          <label htmlFor="clarification-answer" className="text-sm">
            Answer
          </label>
          <textarea
            id="clarification-answer"
            className="min-h-20 rounded-lg border border-input px-2.5 py-1 text-sm"
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <Button type="submit" disabled={pending || text.trim() === ""}>
            {pending ? "Sending…" : "Send answer"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

export function ClientToolCard({
  prompt,
  pending,
  onRespond,
}: {
  prompt: string
  pending: boolean
  onRespond: () => void
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Client tool</CardTitle>
        <CardDescription>{prompt}</CardDescription>
      </CardHeader>
      <CardContent>
        <Button disabled={pending} onClick={onRespond}>
          {pending ? "Sending…" : "Respond"}
        </Button>
      </CardContent>
    </Card>
  )
}

export function ResultCard({
  run,
  events,
  zipUrl,
}: {
  run: Run
  events: RunEvent[]
  zipUrl?: string
}) {
  const failed = [...events].reverse().find((event) => event.type === "RUN_FAILED")
  const summary = run.summary
  const task = [run.task, ...(summary?.followUps ?? [])].filter(Boolean).join("\n")
  const rerun = `/runs/new?agentId=${encodeURIComponent(run.agentId)}&task=${encodeURIComponent(task)}&criteria=${encodeURIComponent((run.criteria ?? []).join("\n"))}`
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Result
          <Badge>{run.status}</Badge>
        </CardTitle>
        {run.terminalCause ? <CardDescription>Cause: {run.terminalCause}</CardDescription> : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {run.costSource === "openhands" ? (
          <p className="text-muted-foreground">Cost (from OpenHands process): ${run.costUsd.toFixed(4)}</p>
        ) : (
          <p className="text-muted-foreground">Cost: ${run.costUsd.toFixed(4)}</p>
        )}
        {run.actualModel?.name ? (
          <p className="text-muted-foreground">
            Model that ran: {run.actualModel.name}
            {run.backupUsed ? " (backup)" : ""}
          </p>
        ) : null}
        {failed && typeof failed.payload.text === "string" ? <p>{failed.payload.text}</p> : null}
        {summary ? (
          <>
            <p>{summary.description}</p>
            <p>Files: {summary.filesChanged.join(", ") || "none"}</p>
            <p>Dependencies: {summary.dependencies.join(", ") || "none"}</p>
            <ul className="flex flex-col gap-1">
              {summary.criteria.map((item) => (
                <li key={item.text}>
                  {item.text}{" "}
                  {item.evidence.startsWith("http") ? (
                    <a href={item.evidence}>{item.evidence}</a>
                  ) : (
                    <span>{item.evidence}</span>
                  )}
                </li>
              ))}
            </ul>
            <p>Assumptions: {summary.assumptions.join("; ") || "none"}</p>
            <p>Follow-ups: {summary.followUps.join("; ") || "none"}</p>
          </>
        ) : null}
        <div className="flex flex-wrap gap-2">
          {run.prUrl ? (
            <Button nativeButton={false} render={<a href={run.prUrl} target="_blank" rel="noreferrer" />}>
              Open PR
            </Button>
          ) : null}
          {zipUrl ? (
            <Button nativeButton={false} variant="outline" render={<a href={zipUrl} />}>
              Download zip
            </Button>
          ) : null}
          {run.previewUrl ? (
            <Button nativeButton={false} variant="outline" render={<a href={run.previewUrl} target="_blank" rel="noreferrer" />}>
              Open preview
            </Button>
          ) : null}
          <Button nativeButton={false} variant="outline" render={<Link href={rerun} />}>
            Re-run with changes
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
