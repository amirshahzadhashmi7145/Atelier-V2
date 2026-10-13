"use client"

import { useEffect, useRef, useState, type ReactNode } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  answerChat,
  closeProject,
  createProject,
  getChatRun,
  getProject,
  listChatAgents,
  listMessages,
  listProjects,
  postMessage,
  stopChatRun,
  type ChatMessage,
} from "@/features/chat/api"
import { apiBaseUrl } from "@/lib/api/client"
import { queryKeys } from "@/lib/api/query-keys"
import { bubbleText, placeDelta, type Bubble } from "@/lib/runs/bubbles"
import { isTerminal, type RunEvent } from "@/lib/runs/events"
import { readEventStream } from "@/lib/sse/stream"

const running = new Set(["queued", "running", "waiting_client"])

export function ChatScreen({
  projectId,
  renderRun,
}: {
  projectId?: string
  renderRun?: (id: string) => ReactNode
}) {
  const projects = useQuery({ queryKey: queryKeys.projects, queryFn: listProjects })
  const queryClient = useQueryClient()
  const project = useQuery({
    queryKey: queryKeys.project(projectId ?? ""),
    queryFn: () => getProject(projectId ?? ""),
    enabled: Boolean(projectId),
    refetchInterval: 2000,
  })
  const messages = useQuery({
    queryKey: queryKeys.messages(projectId ?? ""),
    queryFn: () => listMessages(projectId ?? ""),
    enabled: Boolean(projectId),
    refetchInterval: 1000,
  })
  const threadRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)
  const [away, setAway] = useState(false)
  const [activity, setActivity] = useState(0)
  const [showPreview, setShowPreview] = useState(false)

  useEffect(() => {
    const node = threadRef.current
    if (stickRef.current && node) node.scrollTop = node.scrollHeight
  }, [activity, messages.data])

  return (
    <div className="flex h-full min-h-0 w-full min-w-0 overflow-hidden">
      <aside className="flex w-56 shrink-0 flex-col gap-3 overflow-auto border-r p-3">
        <NewProject />
        {projects.isLoading ? <p className="text-sm text-muted-foreground">Loading projects</p> : null}
        {projects.isError ? <p className="text-sm text-destructive">Could not load projects</p> : null}
        {(projects.data ?? []).length === 0 && !projects.isLoading ? (
          <p className="text-sm text-muted-foreground">No projects yet</p>
        ) : null}
        <ul className="flex flex-col gap-1">
          {(projects.data ?? []).map((item) => (
            <li key={item.id}>
              <Link className={item.id === projectId ? "font-medium" : ""} href={`/chat/${item.id}`}>
                {item.name}
              </Link>
            </li>
          ))}
        </ul>
      </aside>
      <section className="flex min-h-0 min-w-0 flex-1 flex-col gap-3 p-4">
        {project.data?.localMode ? (
          <p className="rounded bg-yellow-100 px-3 py-2 text-sm text-yellow-950">
            DEV LOCAL MODE. Commands run on this machine, inside the project folder only.
          </p>
        ) : null}
        {projectId && project.data ? (
          <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between gap-2">
            <h1 className="text-lg font-semibold">{project.data.name}</h1>
            <div className="flex gap-2">
              <Button type="button" variant="outline" className="xl:hidden" onClick={() => setShowPreview((value) => !value)}>
                {showPreview ? "Chat" : "Preview"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  void navigator.clipboard.writeText(project.data?.folderPath ?? "")
                  toast.success("Folder path copied")
                }}
              >
                Open folder
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  if (!projectId) return
                  void closeProject(projectId).then(() => queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) }))
                }}
              >
                Close project
              </Button>
            </div>
          </div>
          {project.data.summary ? <p className="text-sm text-muted-foreground">{project.data.summary}</p> : null}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Choose a project or create one.</p>
        )}
        <div className="relative min-h-0 flex-1">
          {showPreview ? (
            <div className="h-full overflow-hidden xl:hidden">
              <PreviewPane url={project.data?.previewUrl} />
            </div>
          ) : (
            <div
              ref={threadRef}
              onScroll={() => {
                const node = threadRef.current
                if (!node) return
                const near = node.scrollHeight - node.scrollTop - node.clientHeight < 48
                stickRef.current = near
                setAway(!near)
              }}
              className="flex h-full flex-col gap-3 overflow-y-auto [scrollbar-width:thin]"
            >
              {(messages.data ?? []).map((message) => {
                const replied = (messages.data ?? []).some((item) => item.role === "agent" && item.runId === message.runId)
                const prior = (messages.data ?? []).find((item) => item.role === "user" && item.runId === message.runId)?.text ?? ""
                return (
                  <article key={message.id} className="flex flex-col gap-2 rounded border p-3">
                    <p className="flex items-center gap-2 text-xs uppercase text-muted-foreground">
                      {message.role}
                      {message.label ? (
                        <span data-label={message.label} className="rounded-full border px-2 py-0.5 normal-case">
                          {message.label === "out" ? "out of scope" : message.label === "task" ? "in scope" : "chat"}
                        </span>
                      ) : null}
                    </p>
                    <p className="whitespace-pre-wrap text-sm">{message.text}</p>
                    {message.statusNote ? <p className="text-xs text-muted-foreground">{message.statusNote}</p> : null}
                    {message.runId ? (
                      <RunFollow
                        message={message}
                        renderRun={renderRun}
                        streaming={message.role === "user" && !replied}
                        prior={prior}
                        onActivity={() => setActivity((value) => value + 1)}
                      />
                    ) : null}
                  </article>
                )
              })}
            </div>
          )}
          {away && !showPreview ? (
            <button
              type="button"
              className="absolute bottom-2 left-1/2 -translate-x-1/2 rounded-full border bg-background px-3 py-1 text-xs shadow"
              onClick={() => {
                const node = threadRef.current
                if (!node) return
                node.scrollTop = node.scrollHeight
                stickRef.current = true
                setAway(false)
              }}
            >
              jump to latest
            </button>
          ) : null}
        </div>
        {projectId ? <Composer projectId={projectId} /> : null}
      </section>
      <aside className="hidden h-full min-h-0 w-72 shrink-0 border-l p-3 xl:block">
        <PreviewPane url={project.data?.previewUrl} />
      </aside>
    </div>
  )
}

function NewProject() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const agents = useQuery({ queryKey: queryKeys.agents, queryFn: listChatAgents })
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [agentId, setAgentId] = useState("")
  const [repoUrl, setRepoUrl] = useState("")
  const [githubToken, setGithubToken] = useState("")
  const create = useMutation({
    mutationFn: () => createProject({ name, agentId, repoUrl: repoUrl || undefined, githubToken: githubToken || undefined }),
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects })
      setGithubToken("")
      router.push(`/chat/${project.id}`)
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not create the project"),
  })
  if (!open) {
    return (
      <Button type="button" onClick={() => setOpen(true)}>
        New project
      </Button>
    )
  }
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault()
        create.mutate()
      }}
    >
      <label className="text-sm" htmlFor="project-name">
        Name
        <input id="project-name" className="mt-1 w-full rounded border px-2 py-1" value={name} onChange={(event) => setName(event.target.value)} />
      </label>
      <label className="text-sm" htmlFor="project-agent">
        Agent
        <select id="project-agent" className="mt-1 w-full rounded border px-2 py-1" value={agentId} onChange={(event) => setAgentId(event.target.value)}>
          <option value="">Choose</option>
          {(agents.data ?? []).map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name}
            </option>
          ))}
        </select>
      </label>
      {(agents.data ?? []).length === 0 ? (
        <Link className="text-sm underline" href="/agents/new">
          Create an agent first
        </Link>
      ) : null}
      <label className="text-sm" htmlFor="project-repo">
        Repo URL
        <input id="project-repo" className="mt-1 w-full rounded border px-2 py-1" value={repoUrl} onChange={(event) => setRepoUrl(event.target.value)} />
      </label>
      <label className="text-sm" htmlFor="project-token">
        GitHub token
        <input id="project-token" type="password" className="mt-1 w-full rounded border px-2 py-1" value={githubToken} onChange={(event) => setGithubToken(event.target.value)} />
      </label>
      <Button type="submit" disabled={create.isPending || !name || !agentId}>
        {create.isPending ? "Creating…" : "Create"}
      </Button>
    </form>
  )
}

function Composer({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient()
  const project = useQuery({ queryKey: queryKeys.project(projectId), queryFn: () => getProject(projectId), refetchInterval: 1000 })
  const [text, setText] = useState("")
  const send = useMutation({
    mutationFn: () => postMessage(projectId, text),
    onSuccess: async () => {
      setText("")
      await queryClient.invalidateQueries({ queryKey: queryKeys.messages(projectId) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not send"),
  })
  const stop = useMutation({
    mutationFn: () => stopChatRun(project.data?.activeRunId ?? ""),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.messages(projectId) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not stop"),
  })
  const working = Boolean(project.data?.activeRunId)
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault()
        if (text.trim()) send.mutate()
      }}
    >
      {working ? (
        <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
          <span>agent is working</span>
          <Button type="button" variant="outline" disabled={stop.isPending} onClick={() => stop.mutate()}>
            {stop.isPending ? "Stopping…" : "Stop"}
          </Button>
        </div>
      ) : null}
      <div className="flex gap-2">
        <label className="sr-only" htmlFor="chat-message">
          Message
        </label>
        <input
          id="chat-message"
          className="flex-1 rounded border px-2 py-1"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <Button type="submit" disabled={send.isPending || !text.trim()}>
          {send.isPending ? "Sending…" : "Send"}
        </Button>
      </div>
    </form>
  )
}

function PreviewPane({ url }: { url?: string | null }) {
  if (url) return <iframe key={url} title="Project preview" src={url} className="h-full min-h-0 w-full rounded border" />
  return <p className="text-sm text-muted-foreground">The preview appears here when a run finishes.</p>
}

function toolLine(name: string, args: unknown) {
  const record = args && typeof args === "object" ? (args as Record<string, unknown>) : {}
  if (name === "package_install") return `running npm install ${String(record.name ?? "")}`.trim()
  if (name === "files") return `writing ${String(record.path ?? "a file")}`
  if (name === "headless_browser") return "taking screenshots"
  if (name === "shell") return `running: ${String(record.command ?? "").slice(0, 80)}`
  return `running ${name}`
}

function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(since)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  return <>{Math.max(0, Math.floor((now - since) / 1000))}s</>
}

function LiveText({ runId, onActivity }: { runId: string; onActivity?: () => void }) {
  const [bubbles, setBubbles] = useState<Bubble[]>([])
  const [active, setActive] = useState(true)
  const [tools, setTools] = useState<{ name: string; args: unknown; done: boolean; started: number }[]>([])
  const [started] = useState(() => Date.now())
  const [retrying, setRetrying] = useState(false)
  const seen = useRef(new Set<string>())
  const notify = useRef(onActivity)
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
        const index = Number(event.payload.index ?? 0)
        setBubbles((current) => placeDelta(current, callId, index, String(event.payload.text ?? "")))
        notify.current?.()
      }
      if (event.type === "MODEL_OUTPUT") {
        const callId = String(event.payload.modelCallId ?? event.payload.callId ?? "call")
        const text = String(event.payload.text ?? "")
        setBubbles((current) => {
          const index = current.findIndex((item) => item.callId === callId)
          if (index === -1) return placeDelta(current, callId, 1, text)
          const copy = current.slice()
          copy[index] = { callId, parts: new Map([[1, text]]) }
          return copy
        })
        notify.current?.()
      }
      if (event.type === "TOOL_CALLED") {
        setTools((current) => [...current, { name: String(event.payload.name ?? ""), args: event.payload.arguments, done: false, started: Date.now() }])
        notify.current?.()
      }
      if (event.type === "TOOL_RESULT" || event.type === "TOOL_REFUSED") {
        setTools((current) => {
          const copy = current.slice()
          for (let index = copy.length - 1; index >= 0; index -= 1) {
            if (copy[index].name === event.payload.name && !copy[index].done) {
              copy[index] = { ...copy[index], done: true }
              break
            }
          }
          return copy
        })
      }
      if (event.type === "MODEL_RETRY") {
        setRetrying(true)
        notify.current?.()
      }
      if (event.type === "MODEL_OUTPUT" || event.type === "MODEL_CALLED") {
        setRetrying(false)
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
  const spoken = bubbles.some((bubble) => bubbleText(bubble).length > 0)
  return (
    <div className="flex flex-col gap-1 text-sm" data-streaming={active ? "" : undefined}>
      {active && !spoken ? (
        <p data-thinking="">
          {retrying ? "retrying" : "thinking"} <Elapsed since={started} />
        </p>
      ) : null}
      {bubbles.map((bubble) => (
        <p key={bubble.callId} data-bubble={bubble.callId}>
          {bubbleText(bubble)}
          {active ? <span className="ml-0.5 inline-block animate-pulse">▍</span> : null}
        </p>
      ))}
      {finished.length ? (
        <details>
          <summary>{finished.length} finished</summary>
          {finished.map((item, index) => (
            <p key={`${item.name}-${index}`} className="text-xs text-muted-foreground">
              {toolLine(item.name, item.args)}
            </p>
          ))}
        </details>
      ) : null}
      {runningTools.map((item, index) => (
        <p key={`${item.name}-${index}`} className="text-xs text-muted-foreground">
          {toolLine(item.name, item.args)} <Elapsed since={item.started} />
        </p>
      ))}
    </div>
  )
}

function RunFollow({
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
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not send the answer"),
  })
  const retry = useMutation({
    mutationFn: () => postMessage(message.projectId, `${prior ?? ""}\n\nPrevious attempt failed: ${run.data?.terminalCause ?? "error"}: ${message.text}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.messages(message.projectId) })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not try again"),
  })
  if (!run.data) return streaming ? <LiveText runId={runId} onActivity={onActivity} /> : null
  if (streaming) {
    return (
      <div className="flex flex-col gap-2">
        <LiveText runId={runId} onActivity={onActivity} />
        {running.has(run.data.status) ? (
          <Button type="button" variant="outline" onClick={() => setExpanded((value) => !value)}>
            {expanded ? "Collapse" : "Working"}
          </Button>
        ) : null}
        {expanded && renderRun ? renderRun(runId) : null}
      </div>
    )
  }
  if (message.role === "agent" && run.data.status === "failed") {
    return (
      <Button type="button" variant="outline" disabled={retry.isPending} onClick={() => retry.mutate()}>
        {retry.isPending ? "Trying…" : "Try again"}
      </Button>
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
    return (
      <div className="flex flex-col gap-1 text-sm">
        <p>Files changed: {run.data.summary.filesChanged.join(", ") || "none"}</p>
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
