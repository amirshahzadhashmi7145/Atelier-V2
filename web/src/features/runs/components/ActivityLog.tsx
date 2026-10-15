"use client"

import { useEffect, useRef, useState } from "react"
import { useVirtualizer } from "@tanstack/react-virtual"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { RunEvent } from "@/lib/runs/events"

const labels: Record<RunEvent["type"], string> = {
  RUN_STARTED: "Run started",
  MODEL_CALLED: "Model called",
  MODEL_DELTA: "Model delta",
  MODEL_OUTPUT: "Model output",
  MODEL_RETRY: "Model retry",
  TOOL_CALLED: "Tool called",
  TOOL_RESULT: "Tool result",
  TOOL_REFUSED: "Tool refused",
  SKILL_LOADED: "Skill loaded",
  CLIENT_TOOL_REQUESTED: "Client tool",
  CLARIFICATION_RAISED: "Clarification",
  STATE_CHANGED: "State",
  RUN_COMPLETED: "Run completed",
  RUN_FAILED: "Run failed",
}

export function eventSummary(event: RunEvent) {
  const payload = event.payload
  if (event.type === "MODEL_DELTA" || event.type === "MODEL_OUTPUT") return String(payload.text ?? labels[event.type])
  if (event.type === "TOOL_CALLED" || event.type === "TOOL_RESULT" || event.type === "TOOL_REFUSED") {
    return `${labels[event.type]}: ${String(payload.name ?? "")}`
  }
  if (event.type === "SKILL_LOADED") return `Skill loaded: ${String(payload.name ?? "")}`
  if (event.type === "CLARIFICATION_RAISED") return String(payload.question ?? "Clarification")
  if (event.type === "CLIENT_TOOL_REQUESTED") return String(payload.prompt ?? payload.name ?? "Client tool")
  if (event.type === "STATE_CHANGED") return `State: ${String(payload.status ?? "")}`
  if (event.type === "RUN_FAILED") return String(payload.text ?? "Run failed")
  return labels[event.type]
}

export function LogRow({ event }: { event: RunEvent }) {
  const when = new Date(event.occurredAt).toLocaleTimeString()
  return (
    <article data-seq={event.seq} className="flex flex-col gap-1 border-b px-3 py-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span aria-hidden className="text-xs text-muted-foreground">
          {labels[event.type]}
        </span>
        <time dateTime={event.occurredAt}>{when}</time>
        <span>{event.actor.role ?? event.actor.kind}</span>
        {event.cost ? <Badge variant="secondary">${event.cost.usd.toFixed(3)}</Badge> : null}
      </div>
      <p>{eventSummary(event)}</p>
      <details>
        <summary>Payload</summary>
        <pre tabIndex={0} className="max-h-40 overflow-auto text-xs">
          {JSON.stringify(event.payload, null, 2)}
        </pre>
      </details>
    </article>
  )
}

export function ActivityLog({ events }: { events: RunEvent[] }) {
  const [active, setActive] = useState<string>("all")
  const [stick, setStick] = useState(true)
  const parent = useRef<HTMLDivElement>(null)
  const types = [...new Set(events.map((event) => event.type))]
  const rows = active === "all" ? events : events.filter((event) => event.type === active)
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parent.current,
    estimateSize: () => 88,
    overscan: 6,
  })

  const scrollToEnd = useRef(virtualizer.scrollToIndex)
  scrollToEnd.current = virtualizer.scrollToIndex
  useEffect(() => {
    if (!stick || rows.length === 0) return
    scrollToEnd.current(rows.length - 1, { align: "end" })
  }, [rows.length, stick])

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap gap-1 border-b p-2">
        <Button size="xs" variant={active === "all" ? "secondary" : "ghost"} onClick={() => setActive("all")}>
          All
        </Button>
        {types.map((type) => (
          <Button key={type} size="xs" className="transition-none" variant={active === type ? "secondary" : "ghost"} onClick={() => setActive(type)}>
            {labels[type]}
          </Button>
        ))}
      </div>
      <div
        ref={parent}
        className="min-h-0 flex-1 overflow-auto"
        onScroll={() => {
          const el = parent.current
          if (!el) return
          setStick(el.scrollHeight - el.scrollTop - el.clientHeight < 48)
        }}
      >
        {rows.length === 0 ? (
          <p className="p-3 text-sm text-muted-foreground">Waiting for events</p>
        ) : (
          <div className="relative w-full" style={{ height: virtualizer.getTotalSize() }}>
            {virtualizer.getVirtualItems().map((item) => (
              <div
                key={item.key}
                data-index={item.index}
                ref={virtualizer.measureElement}
                className="absolute top-0 left-0 w-full"
                style={{ transform: `translateY(${item.start}px)` }}
              >
                <LogRow event={rows[item.index]!} />
              </div>
            ))}
          </div>
        )}
      </div>
      {stick ? null : (
        <Button className="m-2" size="sm" variant="outline" onClick={() => setStick(true)}>
          Jump to latest
        </Button>
      )}
    </div>
  )
}
