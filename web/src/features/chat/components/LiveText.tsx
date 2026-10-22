"use client"

import { useEffect, useRef, useState } from "react"
import { apiBaseUrl } from "@/lib/api/client"
import { bubbleText, placeDelta, type Bubble } from "@/lib/runs/bubbles"
import type { RunEvent } from "@/lib/runs/events"
import { readEventStream } from "@/lib/sse/stream"

export function toolKind(name: string) {
  const compact = name.toLowerCase().replace(/[^a-z0-9]/g, "")
  if (compact.includes("terminal") || compact.includes("cmdrun") || compact.includes("bash") || compact === "run" || compact === "shell") return "terminal"
  if (compact.includes("tasktracker") || compact === "task") return "task_tracker"
  if (compact.includes("browser")) return "browser"
  if (compact.includes("edit") || compact.includes("write") || compact.includes("strreplace") || compact === "files") return "edit"
  return name
}

export function toolLine(name: string, args: unknown) {
  const record = args && typeof args === "object" ? (args as Record<string, unknown>) : {}
  const kind = toolKind(name)
  if (name === "package_install") return `running npm install ${String(record.name ?? "")}`.trim()
  if (name === "files") {
    const op = String(record.op ?? "write")
    return `${op} ${String(record.path ?? "a file")}`
  }
  if (name === "headless_browser" || kind === "browser") return "using the browser"
  if (kind === "terminal") {
    const command = String(record.command ?? "").slice(0, 80)
    return command ? `running: ${command}` : "running terminal"
  }
  if (kind === "edit") return `edit ${String(record.path ?? "a file")}`
  if (kind === "task_tracker") return "updating tasks"
  return `running ${name}`
}

export function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(since)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  const seconds = Math.max(0, Math.floor((now - since) / 1000))
  if (seconds < 60) return <>{seconds}s</>
  return <>{`${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`}</>
}

export function modelWaitHint(model?: { provider?: string; name?: string }) {
  const provider = model?.provider ?? "openai"
  const name = model?.name?.trim()
  if (provider === "ollama") return "Ollama (can take 30–120s on CPU)"
  if (provider === "gemini") return name ? `Gemini · ${name}` : "Gemini"
  return name ? `${provider} · ${name}` : provider
}

type ToolRow = { name: string; args: unknown; done: boolean; started: number; note?: string; output?: string }

export function LiveText({
  runId,
  model,
  onActivity,
}: {
  runId: string
  model?: { provider?: string; name?: string }
  onActivity?: () => void
}) {
  const [bubbles, setBubbles] = useState<Bubble[]>([])
  const [active, setActive] = useState(true)
  const [tools, setTools] = useState<ToolRow[]>([])
  const [started] = useState(() => Date.now())
  const [retry, setRetry] = useState<{ attempt?: number; reason?: string } | null>(null)
  const [phase, setPhase] = useState("Starting run…")
  const seen = useRef(new Set<string>())
  const sealed = useRef(new Set<string>())
  const notify = useRef(onActivity)
  const waitHint = modelWaitHint(model)
  const waitHintRef = useRef(waitHint)
  useEffect(() => {
    waitHintRef.current = waitHint
  }, [waitHint])
  useEffect(() => {
    notify.current = onActivity
  }, [onActivity])

  useEffect(() => {
    const controller = new AbortController()
    let seq = 0
    const take = (event: RunEvent) => {
      if (seen.current.has(event.id)) return
      seen.current.add(event.id)
      if (event.type !== "MODEL_DELTA") seq = Math.max(seq, event.seq)
      if (event.type === "MODEL_DELTA") {
        const callId = String(event.payload.modelCallId ?? event.payload.callId ?? "call")
        if (sealed.current.has(callId)) return
        setPhase("Model responding…")
        const index = Number(event.payload.index ?? 0)
        setBubbles((current) => placeDelta(current, callId, index, String(event.payload.text ?? "")))
        notify.current?.()
      }
      if (event.type === "MODEL_OUTPUT") {
        const callId = String(event.payload.modelCallId ?? event.payload.callId ?? "call")
        const text = String(event.payload.text ?? "")
        sealed.current.add(callId)
        setBubbles((current) => {
          const index = current.findIndex((item) => item.callId === callId)
          if (index === -1) return placeDelta(current, callId, 1, text)
          const copy = current.slice()
          const existing = bubbleText(copy[index])
          copy[index] = { callId, parts: new Map([[1, text.length >= existing.length ? text : existing]]) }
          return copy
        })
        notify.current?.()
      }
      if (event.type === "RUN_STARTED") {
        setPhase("OpenHands starting…")
        notify.current?.()
      }
      if (event.type === "MODEL_STARTED") {
        setPhase(`Turn ${String(event.payload.iteration ?? "?")}: waiting for ${waitHintRef.current}…`)
        notify.current?.()
      }
      if (event.type === "TOOL_CALLED") {
        const name = String(event.payload.name ?? "")
        const args = event.payload.arguments
        setPhase(toolLine(name, args))
        setTools((current) => {
          const last = current[current.length - 1]
          const duplicate =
            last &&
            !last.done &&
            toolKind(last.name) === toolKind(name) &&
            JSON.stringify(last.args ?? {}) === JSON.stringify(args ?? {})
          if (duplicate) return current
          return [...current, { name, args, done: false, started: Date.now() }]
        })
        notify.current?.()
      }
      if (event.type === "TOOL_RESULT") {
        const name = String(event.payload.name ?? "")
        const output = typeof event.payload.output === "string" ? event.payload.output : undefined
        setTools((current) => {
          const copy = current.slice()
          for (let index = 0; index < copy.length; index += 1) {
            if (!copy[index].done && toolKind(copy[index].name) === toolKind(name)) {
              copy[index] = { ...copy[index], done: true, output }
              break
            }
          }
          return copy
        })
        setPhase("Model thinking…")
        notify.current?.()
      }
      if (event.type === "TOOL_REFUSED") {
        const name = String(event.payload.name ?? "")
        const reason = String(event.payload.reason ?? "refused")
        setPhase(`${name} refused: ${reason}`)
        setTools((current) => [
          ...current,
          { name, args: event.payload.arguments, done: true, started: Date.now(), note: reason },
        ])
        notify.current?.()
      }
      if (event.type === "CLARIFICATION_RAISED") {
        setPhase(`Waiting for you: ${String(event.payload.question ?? "the agent asked a question")}`)
        notify.current?.()
      }
      if (event.type === "CLIENT_TOOL_REQUESTED") {
        setPhase(`Waiting on a client tool: ${String(event.payload.prompt ?? event.payload.name ?? "respond to continue")}`)
        notify.current?.()
      }
      if (event.type === "MODEL_RETRY") {
        const attempt = Number(event.payload.attempt ?? 0)
        setRetry({
          attempt: Number.isFinite(attempt) && attempt > 0 ? attempt : undefined,
          reason: typeof event.payload.reason === "string" ? event.payload.reason : undefined,
        })
        notify.current?.()
      }
      if (event.type === "MODEL_OUTPUT" || event.type === "MODEL_CALLED") {
        setRetry(null)
      }
      if (event.type === "RUN_COMPLETED" || event.type === "RUN_FAILED" || (event.type === "STATE_CHANGED" && event.payload.status === "cancelled")) {
        setActive(false)
      }
    }
    const pump = async () => {
      let delay = 500
      while (!controller.signal.aborted) {
        try {
          await readEventStream(
            `${apiBaseUrl()}/runs/${runId}/events`,
            seq,
            (frame) => take(JSON.parse(frame.data) as RunEvent),
            controller.signal,
          )
          setActive(false)
          return
        } catch {
          if (controller.signal.aborted) return
          await new Promise((resolve) => setTimeout(resolve, delay))
          delay = Math.min(delay * 2, 8000)
        }
      }
    }
    void pump()
    return () => controller.abort()
  }, [runId])

  const finished = tools.filter((item) => item.done)
  const runningTools = tools.filter((item) => !item.done)
  const retryLine = retry
    ? `Retrying model${retry.attempt ? ` (attempt ${retry.attempt})` : ""}${retry.reason ? `: ${retry.reason}` : ""}`
    : null
  return (
    <div className="flex flex-col gap-1 text-sm" data-streaming={active || bubbles.length ? "" : undefined}>
      {active ? (
        <p data-thinking="" className="text-muted-foreground">
          {retryLine ?? phase} · <Elapsed since={started} />
        </p>
      ) : null}
      {bubbles.map((bubble) => (
        <p key={bubble.callId} data-bubble={bubble.callId} className="whitespace-pre-wrap">
          {bubbleText(bubble)}
          {active ? <span className="ml-0.5 inline-block animate-pulse">▍</span> : null}
        </p>
      ))}
      {finished.map((item, index) =>
        item.output ? (
          <details key={`done-${item.name}-${index}`} className="text-xs text-muted-foreground">
            <summary className="cursor-pointer">
              ✓ {toolLine(item.name, item.args)}
              {item.note ? ` — ${item.note}` : null}
            </summary>
            <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded border bg-muted p-2">{item.output}</pre>
          </details>
        ) : (
          <p key={`done-${item.name}-${index}`} className="text-xs text-muted-foreground">
            ✓ {toolLine(item.name, item.args)}
            {item.note ? ` — ${item.note}` : null}
          </p>
        ),
      )}
      {runningTools.map((item, index) => (
        <p key={`run-${item.name}-${index}`} className="text-xs font-medium text-foreground">
          → {toolLine(item.name, item.args)} <Elapsed since={item.started} />
        </p>
      ))}
    </div>
  )
}
