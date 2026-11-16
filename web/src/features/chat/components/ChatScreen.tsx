"use client"

import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowUpIcon,
  CalendarCheckIcon,
  ContactIcon,
  FileTextIcon,
  GraduationCapIcon,
  LayoutGridIcon,
  LifeBuoyIcon,
  ListChecksIcon,
  PackageIcon,
  PanelRightIcon,
  ShoppingBagIcon,
  UsersIcon,
  WalletIcon,
  type LucideIcon,
} from "lucide-react"
import { toast } from "sonner"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { Button } from "@/components/ui/button"
import { Select, type SelectOption } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  approveProjectPlan,
  editProjectPlan,
  createProject,
  getProject,
  listTemplates,
  instantiateTemplate,
  listProjectTemplates,
  createProjectFromTemplate,
  listChatAgents,
  listMessages,
  listProjectNeeds,
  answerNeed,
  postMessage,
  stopChatRun,
  type ChatMessage,
  type Project,
  type ProjectTemplate,
} from "@/features/chat/api"
import { queryKeys } from "@/lib/api/query-keys"
import { LiveText } from "./LiveText"
import { RunFollow } from "./RunFollow"

// Thumbnail art for the New Project template cards: a lucide icon over an accent
// gradient (both chosen by the backend). The gradient classes are literal so Tailwind
// keeps them.
const TEMPLATE_ICONS: Record<string, LucideIcon> = {
  users: UsersIcon,
  contact: ContactIcon,
  "square-check-big": ListChecksIcon,
  "shopping-bag": ShoppingBagIcon,
  package: PackageIcon,
  "calendar-check": CalendarCheckIcon,
  "life-buoy": LifeBuoyIcon,
  "file-text": FileTextIcon,
  wallet: WalletIcon,
  "graduation-cap": GraduationCapIcon,
  "layout-grid": LayoutGridIcon,
}
const TEMPLATE_ACCENTS: Record<string, string> = {
  indigo: "from-indigo-500 to-indigo-700",
  emerald: "from-emerald-500 to-emerald-700",
  amber: "from-amber-500 to-amber-600",
  rose: "from-rose-500 to-rose-700",
  teal: "from-teal-500 to-teal-700",
  violet: "from-violet-500 to-violet-700",
}

// A mini preview of the generated app using the template's REAL data — a themed header
// with the app name, and record cards showing actual sample values. Reads as a screenshot.
function TemplateThumb({ template }: { template: ProjectTemplate }) {
  const Icon = TEMPLATE_ICONS[template.icon ?? ""] ?? LayoutGridIcon
  const grad = TEMPLATE_ACCENTS[template.accent ?? ""] ?? TEMPLATE_ACCENTS.indigo
  const fields = template.fields ?? []
  const titleField = fields[0]?.name ?? "name"
  const detailFields = fields.slice(1, 3)
  const samples = (template.sample ?? []).slice(0, 2) as Record<string, string | number>[]
  const val = (row: Record<string, string | number>, key?: string) =>
    key && row[key] != null && row[key] !== "" ? String(row[key]) : "—"
  return (
    <div className="pointer-events-none select-none bg-slate-50">
      <div className={`flex items-center gap-2 bg-gradient-to-br ${grad} px-3 py-2.5 text-white`}>
        <span className="grid size-7 place-items-center rounded-lg bg-white/20 shadow-sm transition-transform group-hover:scale-110">
          <Icon className="size-4" aria-hidden />
        </span>
        <span className="min-w-0 leading-tight">
          <span className="block truncate text-[11px] font-semibold">{template.name}</span>
          <span className="block text-[8px] uppercase tracking-wide text-white/70">{template.entity} records</span>
        </span>
        <span className="ml-auto rounded bg-white/20 px-1.5 py-0.5 text-[8px] font-semibold">+ New</span>
      </div>
      <div className="grid grid-cols-2 gap-2 p-2.5">
        {(samples.length ? samples : [{}, {}]).map((row, i) => (
          <div key={i} className="rounded-lg border border-slate-200 bg-white p-2 shadow-sm">
            <div className="truncate text-[10px] font-semibold text-slate-800">{val(row, titleField)}</div>
            {detailFields.map((f) => (
              <div key={f.name} className="mt-1 flex items-center justify-between gap-1.5 text-[8px]">
                <span className="truncate text-slate-400">{f.label}</span>
                <span className="truncate font-medium text-slate-600">{val(row, f.name)}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

export function ChatScreen({
  projectId,
  renderRun,
}: {
  projectId?: string
  renderRun?: (id: string) => ReactNode
}) {
  const project = useQuery({
    queryKey: queryKeys.project(projectId ?? ""),
    queryFn: () => getProject(projectId ?? ""),
    enabled: Boolean(projectId),
    refetchInterval: 2000,
    // Keep polling while the tab is backgrounded so the preview (which can take a
    // while to build) appears without a manual refresh when the user returns.
    refetchIntervalInBackground: true,
  })
  const messages = useQuery({
    queryKey: queryKeys.messages(projectId ?? ""),
    queryFn: () => listMessages(projectId ?? ""),
    enabled: Boolean(projectId),
    refetchInterval: 1000,
  })
  // Locally-held sent-but-not-yet-confirmed messages. They live outside the query
  // cache so the 1s poll can never wipe them mid-flight (which caused the bubble to
  // flash). Each is dropped only once the identical server message has arrived, so
  // the hand-off is seamless with no empty frame.
  const [pending, setPending] = useState<{ msg: ChatMessage; serverId?: string }[]>([])
  const thread = useMemo(() => {
    const server = messages.data ?? []
    const serverIds = new Set(server.map((item) => item.id))
    const live = pending.filter((item) => !(item.serverId && serverIds.has(item.serverId))).map((item) => item.msg)
    return [...server, ...live]
  }, [messages.data, pending])
  const threadRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)
  const [away, setAway] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  // Desktop-only: the side preview pane is HIDDEN by default so a new chat is full-width.
  // Persisted per viewer; only an explicit "0" (the user opened it) keeps it shown.
  const [previewCollapsed, setPreviewCollapsed] = useState(() => {
    try {
      return localStorage.getItem("atelier.previewCollapsed") !== "0"
    } catch {
      return true
    }
  })
  // The preview only exists once a run has published a URL. Until then there is
  // nothing to show, so the pane, its resize handle and its toggles stay out of the way.
  const hasPreview = Boolean(project.data?.previewUrl)
  const togglePreviewCollapsed = () =>
    setPreviewCollapsed((value) => {
      const next = !value
      try {
        localStorage.setItem("atelier.previewCollapsed", next ? "1" : "0")
      } catch {
        // ignore unavailable storage
      }
      return next
    })
  // Client-only persisted width: the server renders the default and the client
  // reads the saved value, so the aside below carries suppressHydrationWarning.
  const [previewWidth, setPreviewWidth] = useState(() => {
    try {
      const saved = Number(localStorage.getItem("atelier.previewWidth"))
      if (saved >= 320 && saved <= 1100) return saved
    } catch {
      // ignore unavailable storage
    }
    return 480
  })
  const previewWidthRef = useRef(previewWidth)
  const dragCleanup = useRef<() => void>(() => {})
  useEffect(() => {
    previewWidthRef.current = previewWidth
  }, [previewWidth])
  useEffect(() => {
    // Remove any in-flight drag listeners if the component unmounts mid-drag.
    return () => dragCleanup.current()
  }, [])
  const startPreviewResize = (event: ReactPointerEvent) => {
    event.preventDefault()
    const startX = event.clientX
    const startW = previewWidth
    const onMove = (e: PointerEvent) => {
      setPreviewWidth(Math.min(1100, Math.max(320, startW + (startX - e.clientX))))
    }
    const detach = () => {
      window.removeEventListener("pointermove", onMove)
      window.removeEventListener("pointerup", onUp)
      dragCleanup.current = () => {}
    }
    const onUp = () => {
      detach()
      try {
        localStorage.setItem("atelier.previewWidth", String(previewWidthRef.current))
      } catch {
        // ignore unavailable storage
      }
    }
    dragCleanup.current = detach
    window.addEventListener("pointermove", onMove)
    window.addEventListener("pointerup", onUp)
  }

  const priorByRun = useMemo(() => {
    const map = new Map<string, string>()
    for (const item of messages.data ?? []) {
      if (item.role === "user" && item.runId && !map.has(item.runId)) map.set(item.runId, item.text)
    }
    return map
  }, [messages.data])

  useEffect(() => {
    const node = threadRef.current
    if (stickRef.current && node) node.scrollTop = node.scrollHeight
  }, [messages.data, pending])
  // Streamed tokens call scrollToBottom directly (coalesced into one rAF) instead
  // of bumping state, so a live run does not re-render the whole chat tree per token.
  const scrollRaf = useRef(0)
  const scrollToBottom = useCallback(() => {
    if (scrollRaf.current) return
    scrollRaf.current = requestAnimationFrame(() => {
      scrollRaf.current = 0
      const node = threadRef.current
      if (stickRef.current && node) node.scrollTop = node.scrollHeight
    })
  }, [])
  useEffect(() => () => cancelAnimationFrame(scrollRaf.current), [])

  if (!projectId) {
    return <WelcomeScreen />
  }

  return (
    <div className="flex h-full min-h-0 w-full min-w-0 overflow-hidden">
      <section className="flex min-h-0 min-w-0 flex-1 flex-col gap-3 px-6 py-4">
        {project.data?.localMode ? (
          <p className="rounded border bg-muted px-3 py-2 text-sm text-foreground">
            DEV LOCAL MODE. Commands run on this machine, inside the project folder only.
          </p>
        ) : null}
        {project.data ? (
          <div className="no-scrollbar flex max-h-[45%] w-full shrink-0 flex-col gap-2 overflow-auto">
            <NeedsYou projectId={projectId} />
            <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-2">
              <h1 className="truncate text-lg font-semibold">{project.data.name}</h1>
              <div className={hasPreview ? "flex items-center gap-1" : "hidden"}>
                <Button type="button" variant="ghost" size="sm" className="xl:hidden" onClick={() => setShowPreview((value) => !value)}>
                  {showPreview ? "Chat" : "Preview"}
                </Button>
                <Button type="button" variant="outline" size="sm" className="hidden gap-1.5 xl:inline-flex" onClick={togglePreviewCollapsed} suppressHydrationWarning>
                  <PanelRightIcon className="size-4" aria-hidden />
                  {previewCollapsed ? "Show preview" : "Hide preview"}
                </Button>
              </div>
            </div>
            {project.data.summary ? <p className="text-sm text-muted-foreground">{project.data.summary}</p> : null}
          </div>
        ) : null}
        <div className="relative min-h-0 flex-1">
          {showPreview && hasPreview ? (
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
              className="no-scrollbar flex h-full w-full flex-col gap-3 overflow-y-auto px-1 py-2"
            >
              {projectId && messages.isPending ? (
                <div className="flex flex-col gap-3" aria-busy="true">
                  <Skeleton className="h-16 w-2/3 self-end" />
                  <Skeleton className="h-16 w-2/3" />
                </div>
              ) : null}
              {projectId && messages.isError ? (
                <ErrorState
                  message={messages.error instanceof Error ? messages.error.message : "Could not load messages"}
                  onRetry={() => void messages.refetch()}
                />
              ) : null}
              {projectId && messages.data && thread.length === 0 ? (
                <EmptyState title="No messages yet" description="Describe what you want built and the agent gets to work." />
              ) : null}
              {thread.map((message) => {
                const mine = message.role === "user"
                return (
                  <article
                    key={message.id}
                    className={`flex w-fit min-w-0 max-w-[85%] flex-col gap-2 rounded-2xl border p-3 text-[0.95rem] shadow-sm ${
                      mine ? "self-end border-primary/20 bg-primary/10" : "self-start bg-card"
                    }`}
                  >
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span
                        className="font-medium text-foreground/80"
                        style={message.agentColor ? { color: message.agentColor } : undefined}
                        data-agent={message.agentName}
                      >
                        {message.agentName ?? (mine ? "You" : message.role)}
                      </span>
                      {message.label ? (
                        <span data-label={message.label} className="rounded-full border px-1.5 py-0.5 text-[10px]">
                          {message.label === "out"
                            ? "out of scope"
                            : message.label === "task"
                              ? "in scope"
                              : message.label === "plan"
                                ? "plan"
                                : message.label === "review"
                                  ? "review"
                                  : "chat"}
                        </span>
                      ) : null}
                      <time dateTime={message.createdAt} className="ml-auto tabular-nums">
                        {new Date(message.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </time>
                    </div>
                    <p className="whitespace-pre-wrap text-sm">{message.text}</p>
                    {message.verdict ? (
                      <p className="text-xs font-medium" data-verdict={message.verdict}>
                        {message.verdict === "approve" ? "Approved" : "Changes requested"}
                      </p>
                    ) : null}
                    {message.planId && message.planItems ? <PlanCard projectId={projectId ?? ""} message={message} /> : null}
                    {message.statusNote ? <p className="text-xs text-muted-foreground">{message.statusNote}</p> : null}
                    {message.runId ? (
                      <RunFollow
                        message={message}
                        renderRun={renderRun}
                        streaming={message.role === "user"}
                        prior={priorByRun.get(message.runId) ?? ""}
                        onActivity={scrollToBottom}
                      />
                    ) : null}
                  </article>
                )
              })}
              {thread.length > 0 && thread[thread.length - 1].role === "user" && !thread[thread.length - 1].runId ? (
                <ThinkingBubble />
              ) : null}
              <LiveWork
                steps={project.data?.supervisorSteps}
                threadRunIds={new Set((messages.data ?? []).map((item) => item.runId).filter((id): id is string => Boolean(id)))}
              />
            </div>
          )}
          {away && !(showPreview && hasPreview) ? (
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
        {projectId ? (
          <Composer
            projectId={projectId}
            project={project.data}
            onPending={(entry) =>
              setPending((prev) => {
                // Drop any already-reconciled entries (their server message has
                // landed) as we add the new one, so this list never grows unbounded.
                const serverIds = new Set((messages.data ?? []).map((item) => item.id))
                const kept = prev.filter((item) => !(item.serverId && serverIds.has(item.serverId)))
                return [...kept, entry]
              })
            }
            onSettled={(clientId, serverId) =>
              setPending((prev) =>
                serverId
                  ? prev.map((item) => (item.msg.id === clientId ? { ...item, serverId } : item))
                  : prev.filter((item) => item.msg.id !== clientId),
              )
            }
          />
        ) : null}
      </section>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize preview"
        onPointerDown={startPreviewResize}
        className={`hidden w-1.5 shrink-0 cursor-col-resize bg-border transition-colors hover:bg-primary/40 ${previewCollapsed || !hasPreview ? "xl:hidden" : "xl:block"}`}
        suppressHydrationWarning
      />
      <aside
        className={`hidden h-full min-h-0 shrink-0 flex-col border-l p-3 ${previewCollapsed || !hasPreview ? "xl:hidden" : "xl:flex"}`}
        style={{ width: previewWidth }}
        suppressHydrationWarning
      >
        <h2 className="mb-2 text-sm font-medium">Preview</h2>
        <PreviewPane url={project.data?.previewUrl} />
      </aside>
    </div>
  )
}

function PlanCard({ projectId, message }: { projectId: string; message: ChatMessage }) {
  const queryClient = useQueryClient()
  const approved = message.verdict === "approve"
  const [items, setItems] = useState(() => (message.planItems ?? []).map((item) => ({ ...item })))
  const approve = useMutation({
    mutationFn: () => approveProjectPlan(projectId, message.planId ?? "", items),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.messages(projectId) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not approve the plan"),
  })
  const edit = useMutation({
    mutationFn: () => editProjectPlan(projectId, message.planId ?? "", items),
    onSuccess: async () => {
      toast.success("Plan updated")
      await queryClient.invalidateQueries({ queryKey: queryKeys.messages(projectId) })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not edit the plan"),
  })
  return (
    <div className="flex flex-col gap-2 rounded border p-2" data-plan={message.planId}>
      {items.map((item, index) => (
        <label key={item.taskId} className="flex flex-col gap-1 text-sm">
          <span>{`${index + 1}. ${item.agentName || "Agent"}`}</span>
          <textarea
            className="min-h-16 rounded border px-2 py-1 text-sm"
            value={item.text}
            readOnly={approved}
            onChange={(event) => {
              if (approved) return
              const next = items.slice()
              next[index] = { ...item, text: event.target.value }
              setItems(next)
            }}
          />
        </label>
      ))}
      {approved ? null : (
        <div className="flex gap-2">
          <Button type="button" variant="outline" disabled={edit.isPending} onClick={() => edit.mutate()}>
            {edit.isPending ? "Saving…" : "Edit"}
          </Button>
          <Button type="button" disabled={approve.isPending} onClick={() => approve.mutate()}>
            {approve.isPending ? "Starting…" : "Approve"}
          </Button>
        </div>
      )}
    </div>
  )
}

const STEP_LABEL: Record<string, string> = {
  planning: "planning",
  working: "working",
  reviewing: "reviewing",
  escalated: "escalated",
  done: "done",
}

function ThinkingBubble() {
  return (
    <div className="flex w-fit items-center gap-2 self-start rounded-2xl border bg-card px-4 py-3 shadow-sm" aria-live="polite" data-thinking-bubble>
      <span className="sr-only">The agent is working</span>
      <span className="flex items-center gap-1" aria-hidden>
        <span className="size-2 animate-bounce rounded-full bg-muted-foreground/70 [animation-delay:-0.3s]" />
        <span className="size-2 animate-bounce rounded-full bg-muted-foreground/70 [animation-delay:-0.15s]" />
        <span className="size-2 animate-bounce rounded-full bg-muted-foreground/70" />
      </span>
      <span className="text-sm text-muted-foreground">Working…</span>
    </div>
  )
}

function LiveWork({ steps, threadRunIds }: { steps?: Project["supervisorSteps"]; threadRunIds?: Set<string> }) {
  const live = (steps ?? []).filter((item) => (item.step === "working" || item.step === "reviewing") && item.runId)
  if (!live.length) return null
  return (
    <div className="flex flex-col gap-2 rounded border p-3" data-live-work>
      {live.map((item) => (
        <div key={item.taskId} className="flex flex-col gap-1">
          <p className="flex items-center gap-2 text-xs font-medium">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-primary" aria-hidden />
            {item.agentName || "Agent"} · {STEP_LABEL[item.step] ?? item.step}
            {item.label ? ` — ${item.label}` : ""}
          </p>
          {item.runId && !threadRunIds?.has(item.runId) ? <LiveText key={item.runId} runId={item.runId} /> : null}
        </div>
      ))}
    </div>
  )
}

const NEED_KIND: Record<string, { label: string; className: string }> = {
  budget: { label: "budget", className: "border-destructive/50 bg-destructive/10 text-destructive" },
  escalate: { label: "escalated", className: "border-destructive/50 text-destructive" },
  question: { label: "question", className: "bg-muted text-muted-foreground" },
}

function NeedsYou({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient()
  const needs = useQuery({
    queryKey: queryKeys.needs(projectId),
    queryFn: () => listProjectNeeds(projectId),
    refetchInterval: 2000,
  })
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const answer = useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) => answerNeed(id, text),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.needs(projectId) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.messages(projectId) })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not send the answer"),
  })
  const rows = needs.data ?? []
  if (rows.length === 0) return null
  return (
    <section className="rounded border p-3" data-needs-you>
      <h2 className="text-sm font-semibold">Needs you</h2>
      <ul className="mt-2 flex flex-col gap-3">
        {rows.map((item) => {
          const kind = NEED_KIND[item.kind] ?? NEED_KIND.question
          return (
            <li key={item.id} className="flex flex-col gap-2 text-sm">
              <p className="flex items-center gap-2">
                <span data-need-kind={item.kind} className={`rounded-full border px-2 py-0.5 text-xs font-medium ${kind.className}`}>
                  {kind.label}
                </span>
                {item.taskId ? (
                  <Link href={`/chat/${projectId}/board#${item.taskId}`} className="text-xs underline">
                    On the board
                  </Link>
                ) : null}
              </p>
              <p>{item.question}</p>
              <form
                className="flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault()
                  const text = (drafts[item.id] || "").trim()
                  if (text) answer.mutate({ id: item.id, text })
                }}
              >
                <label className="sr-only" htmlFor={`need-${item.id}`}>
                  Answer
                </label>
                <input
                  id={`need-${item.id}`}
                  className="flex-1 rounded border px-2 py-1"
                  value={drafts[item.id] ?? ""}
                  onChange={(event) => setDrafts((current) => ({ ...current, [item.id]: event.target.value }))}
                />
                <Button type="submit" disabled={answer.isPending}>
                  {answer.isPending ? "Sending…" : "Answer"}
                </Button>
              </form>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function Field({ label, htmlFor, hint, children }: { label: string; htmlFor?: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-sm font-medium" htmlFor={htmlFor}>
        {label}
        {hint ? <span className="ml-1 font-normal text-muted-foreground">{hint}</span> : null}
      </label>
      {children}
    </div>
  )
}

const inputClass =
  "h-9 w-full rounded-lg border border-input bg-transparent px-3 py-1 text-sm outline-none transition-colors hover:border-ring/60 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40 dark:bg-input/30"

function deriveChatName(prompt: string) {
  const words = prompt.trim().split(/\s+/).slice(0, 7).join(" ")
  return (words.length > 60 ? words.slice(0, 60) : words) || "New chat"
}

function WelcomeScreen() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const templates = useQuery({ queryKey: ["project-templates"], queryFn: listProjectTemplates })
  const [prompt, setPrompt] = useState("")
  const promptRef = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    const node = promptRef.current
    if (!node) return
    node.style.height = "auto"
    node.style.height = `${Math.min(node.scrollHeight, 160)}px`
  }, [prompt])

  const start = useMutation({
    mutationFn: async (text: string) => {
      // A plain prompt spins up a default full-stack team — the system picks the
      // agents, the user never has to. The first message is posted right away.
      const project = await instantiateTemplate("fullstack-web", { name: deriveChatName(text) })
      await postMessage(project.id, text)
      return project
    },
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects })
      router.push(`/chat/${project.id}`)
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not start the chat"),
  })
  const fromTemplate = useMutation({
    mutationFn: (id: string) => createProjectFromTemplate(id, {}),
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects })
      router.push(`/chat/${project.id}`)
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not create the project"),
  })
  const submit = () => {
    const text = prompt.trim()
    if (!text || start.isPending) return
    start.mutate(text)
  }
  const rows = templates.data ?? []
  const busy = start.isPending || fromTemplate.isPending

  return (
    <div className="flex h-full w-full flex-col overflow-y-auto px-6 py-10">
      <div className="flex w-full flex-1 flex-col justify-center gap-7">
        <div className="text-center">
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">What do you want to build?</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Describe it and a team of agents gets to work — it picks the right agents for you. Or start from a template.
          </p>
        </div>
        <form className="w-full" onSubmit={(event) => { event.preventDefault(); submit() }}>
          <div className="flex items-end gap-2 rounded-2xl border bg-card p-2 shadow-sm transition-colors focus-within:border-ring">
            <label className="sr-only" htmlFor="welcome-prompt">Describe your app</label>
            <textarea
              id="welcome-prompt"
              ref={promptRef}
              rows={1}
              placeholder="Build a CRM to track contacts and deals…"
              className="max-h-40 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault()
                  submit()
                }
              }}
            />
            <Button type="submit" disabled={!prompt.trim() || start.isPending}>
              {start.isPending ? "Starting…" : "Start building"}
            </Button>
          </div>
        </form>

        <div className="w-full">
          <h2 className="mb-3 text-sm font-medium">Start from a template</h2>
          {templates.isLoading ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-[200px] rounded-2xl" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
              {rows.map((template) => (
                <button
                  key={template.id}
                  type="button"
                  disabled={busy}
                  onClick={() => fromTemplate.mutate(template.id)}
                  className="group overflow-hidden rounded-2xl border bg-card text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-ring hover:shadow-md disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <TemplateThumb template={template} />
                  <div className="flex flex-col gap-0.5 p-4">
                    <span className="text-sm font-semibold leading-tight">{template.name}</span>
                    <span className="text-xs text-muted-foreground">{template.category}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
          {fromTemplate.isPending ? <p className="mt-2 text-xs text-muted-foreground">Setting up your project…</p> : null}
        </div>

        <div className="flex flex-col items-start gap-2 border-t pt-5">
          <p className="text-xs text-muted-foreground">Want to choose the team or import an existing repo?</p>
          <NewProject />
        </div>
      </div>
    </div>
  )
}

function NewProject() {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<"app" | "team" | "manual">("app")
  if (!open) {
    return (
      <Button type="button" onClick={() => setOpen(true)}>
        New project
      </Button>
    )
  }
  const tab = (value: typeof mode, label: string) => (
    <button
      type="button"
      aria-pressed={mode === value}
      className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
        mode === value ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:text-foreground"
      }`}
      onClick={() => setMode(value)}
    >
      {label}
    </button>
  )
  return (
    <div className="flex flex-col gap-3 rounded-xl border bg-card p-3 shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">New project</h3>
        <button type="button" className="text-xs text-muted-foreground hover:text-foreground" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      <div className="flex flex-wrap gap-1 rounded-lg bg-muted p-1">
        {tab("app", "From an app")}
        {tab("team", "From a team")}
        {tab("manual", "Manual")}
      </div>
      {mode === "app" ? <NewProjectFromAppTemplate /> : mode === "team" ? <NewProjectFromTemplate /> : <NewProjectManual />}
    </div>
  )
}

function NewProjectFromAppTemplate() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const templates = useQuery({ queryKey: ["project-templates"], queryFn: listProjectTemplates })
  const [templateId, setTemplateId] = useState("")
  const [name, setName] = useState("")
  const rows = templates.data ?? []
  const selected = rows.find((row) => row.id === templateId)
  const create = useMutation({
    mutationFn: () => createProjectFromTemplate(templateId, { name: name || undefined }),
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects })
      router.push(`/chat/${project.id}`)
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not create the project"),
  })
  const options: SelectOption[] = rows.map((row) => ({ value: row.id, label: row.name, group: row.category }))
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault()
        create.mutate()
      }}
    >
      <p className="text-xs text-muted-foreground">
        Start from a ready-made app. It becomes your own project — edits never change the template.
      </p>
      <Field label="App template" htmlFor="app-template">
        <Select
          id="app-template"
          ariaLabel="App template"
          value={templateId}
          onValueChange={setTemplateId}
          options={options}
          placeholder={templates.isLoading ? "Loading…" : "Choose an app"}
        />
      </Field>
      {selected ? (
        <p className="rounded-lg bg-muted/60 p-2 text-xs text-muted-foreground">
          {selected.description} Full-stack starter (React + Tailwind frontend, Express + Prisma backend).
        </p>
      ) : null}
      <Field label="Project name" htmlFor="app-name" hint="(optional)">
        <input id="app-name" className={inputClass} placeholder={selected?.name ?? "My app"} value={name} onChange={(event) => setName(event.target.value)} />
      </Field>
      <p className="text-xs text-muted-foreground">
        Agents use <strong>Auto</strong> — they pick the best available model for each task. Just connect a provider key in{" "}
        <Link className="underline" href="/settings/providers">Settings → Providers</Link>.
      </p>
      <Button type="submit" disabled={create.isPending || !templateId}>
        {create.isPending ? "Creating…" : "Create project from app"}
      </Button>
    </form>
  )
}

function NewProjectFromTemplate() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const templates = useQuery({ queryKey: ["templates"], queryFn: listTemplates })
  const [templateId, setTemplateId] = useState("")
  const [name, setName] = useState("")
  const rows = templates.data ?? []
  const selected = rows.find((row) => row.id === templateId)
  const create = useMutation({
    mutationFn: () => instantiateTemplate(templateId, { name }),
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects })
      router.push(`/chat/${project.id}`)
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not create the project"),
  })
  const options: SelectOption[] = rows.map((row) => ({ value: row.id, label: row.name }))
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault()
        create.mutate()
      }}
    >
      <Field label="Team template" htmlFor="template-select">
        <Select
          id="template-select"
          ariaLabel="Team template"
          value={templateId}
          onValueChange={setTemplateId}
          options={options}
          placeholder={templates.isLoading ? "Loading…" : "Choose a team"}
        />
      </Field>
      {selected ? (
        <p className="rounded-lg bg-muted/60 p-2 text-xs text-muted-foreground">
          {selected.description} Team: {selected.members.map((m) => m.name).join(", ")}.
        </p>
      ) : null}
      <Field label="Project name" htmlFor="template-name">
        <input id="template-name" className={inputClass} value={name} onChange={(event) => setName(event.target.value)} />
      </Field>
      <p className="text-xs text-muted-foreground">
        Agents use <strong>Auto</strong> — they pick the best available model per task. Connect a provider key in{" "}
        <Link className="underline" href="/settings/providers">Settings → Providers</Link>.
      </p>
      <Button type="submit" disabled={create.isPending || !name || !templateId}>
        {create.isPending ? "Creating…" : "Create team & project"}
      </Button>
    </form>
  )
}

function NewProjectManual() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const agents = useQuery({ queryKey: queryKeys.agents, queryFn: listChatAgents })
  const [name, setName] = useState("")
  const [agentId, setAgentId] = useState("")
  const [repoUrl, setRepoUrl] = useState("")
  const [githubToken, setGithubToken] = useState("")
  const [importFromRepo, setImportFromRepo] = useState(false)
  const create = useMutation({
    mutationFn: () =>
      createProject({
        name,
        agentId,
        repoUrl: repoUrl || undefined,
        githubToken: githubToken || undefined,
        importFromRepo: importFromRepo && Boolean(repoUrl) ? true : undefined,
      }),
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects })
      setGithubToken("")
      router.push(`/chat/${project.id}`)
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not create the project"),
  })
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
        <input
          id="project-repo"
          className="mt-1 w-full rounded border px-2 py-1"
          placeholder="https://github.com/owner/repo"
          value={repoUrl}
          onChange={(event) => setRepoUrl(event.target.value)}
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={importFromRepo}
          disabled={!repoUrl}
          onChange={(event) => setImportFromRepo(event.target.checked)}
        />
        Clone this repo to start from it (import an existing project)
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

function Composer({
  projectId,
  project,
  onPending,
  onSettled,
}: {
  projectId: string
  project?: Project
  onPending: (entry: { msg: ChatMessage; serverId?: string }) => void
  onSettled: (clientId: string, serverId?: string) => void
}) {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const [text, setText] = useState("")
  const send = useMutation({
    mutationFn: (vars: { clientId: string; body: string }) => postMessage(projectId, vars.body),
    // The pending bubble is already on screen (added in submit, before the mutation
    // runs) so the chat feels instant. On success we tag it with the real server id
    // so the parent drops it only once the identical server message has arrived; on
    // error we remove it and restore the text.
    onSuccess: (created, vars) => {
      onSettled(vars.clientId, created?.id)
    },
    onError: (error, vars) => {
      onSettled(vars.clientId)
      setText(vars.body)
      toast.error(error instanceof Error ? error.message : "Could not send")
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.messages(projectId) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.needs(projectId) })
    },
  })
  const stop = useMutation({
    mutationFn: () => stopChatRun(project?.activeRunId ?? ""),
    onSuccess: async (_data, _vars, context) => {
      // Refresh the run detail too so the "Run stopped." state shows at once
      // instead of waiting for the next 1s poll.
      if (typeof context === "string") await queryClient.invalidateQueries({ queryKey: queryKeys.runs.detail(context) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.messages(projectId) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) })
    },
    onMutate: () => project?.activeRunId,
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not stop"),
  })
  useEffect(() => {
    const node = inputRef.current
    if (!node) return
    node.style.height = "auto"
    node.style.height = `${Math.min(node.scrollHeight, 160)}px`
  }, [text])
  const working = Boolean(project?.activeRunId)
  const live = (project?.supervisorSteps ?? []).find((item) => item.step === "working" || item.step === "reviewing")
  const workingLabel = live?.agentName ? `${live.agentName} is ${live.step}` : "agent is working"
  const submit = () => {
    const body = text.trim()
    if (!body) return
    const clientId = `pending-${Date.now()}`
    onPending({ msg: { id: clientId, projectId, role: "user", text: body, createdAt: new Date().toISOString() } })
    setText("")
    send.mutate({ clientId, body })
  }
  return (
    <form
      className="w-full"
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      {working ? (
        <div className="mb-2 flex items-center justify-between gap-2 rounded-full border bg-muted/50 px-3 py-1.5 text-sm text-muted-foreground">
          <span className="flex items-center gap-2">
            <span className="inline-block size-2 animate-pulse rounded-full bg-primary" aria-hidden />
            {workingLabel}
          </span>
          <Button type="button" variant="outline" size="sm" disabled={stop.isPending} onClick={() => stop.mutate()}>
            {stop.isPending ? "Stopping…" : "Stop"}
          </Button>
        </div>
      ) : null}
      <div className="flex items-end gap-2 rounded-[1.75rem] border bg-card p-2 pl-4 shadow-md transition-colors focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/20">
        <label className="sr-only" htmlFor="chat-message">
          Message
        </label>
        <textarea
          id="chat-message"
          ref={inputRef}
          rows={1}
          placeholder="Message the team…  (⏎ to send, ⇧⏎ for a new line)"
          className="max-h-40 flex-1 resize-none bg-transparent py-1.5 text-[0.95rem] outline-none placeholder:text-muted-foreground"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
          }}
        />
        <Button type="submit" size="icon" className="size-9 shrink-0 rounded-full" disabled={!text.trim()} aria-label="Send">
          <ArrowUpIcon className="size-5" />
        </Button>
      </div>
      <p className="mt-1.5 text-center text-[11px] text-muted-foreground">
        Agents pick a suitable model automatically. Ask to “push to GitHub” or “run the app” anytime.
      </p>
    </form>
  )
}

function PreviewPane({ url }: { url?: string | null }) {
  // Remounting the iframe (by changing its key) forces a fresh load.
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    if (!url) return
    // The dev server often isn't serving the built app yet the instant its URL
    // appears, so the very first iframe load can come up blank. Reload it a couple
    // of times over the next few seconds to pick up the now-ready server, which
    // removes the need to refresh by hand the first time.
    const timers = [setTimeout(() => setNonce((n) => n + 1), 1500), setTimeout(() => setNonce((n) => n + 1), 4000)]
    return () => timers.forEach(clearTimeout)
  }, [url])
  if (!url) {
    return (
      <p className="text-sm text-muted-foreground">
        No preview URL yet. When a run publishes one, it appears here. You can also run <code className="text-xs">npm run dev</code> in the
        project folder and open the local Vite URL.
      </p>
    )
  }
  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex flex-col gap-1 rounded border bg-muted/40 px-2 py-1.5">
        <span className="text-xs font-medium text-muted-foreground">Running at</span>
        <a href={url} target="_blank" rel="noreferrer" className="break-all text-sm underline">
          {url}
        </a>
        <div className="mt-1 flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-fit"
            onClick={() => {
              void navigator.clipboard.writeText(url)
              toast.success("Preview URL copied")
            }}
          >
            Copy URL
          </Button>
          <Button type="button" variant="outline" size="sm" className="w-fit" onClick={() => setNonce((n) => n + 1)}>
            Reload
          </Button>
        </div>
      </div>
      <iframe key={`${url}#${nonce}`} title="Project preview" src={url} className="min-h-48 w-full flex-1 rounded border" />
    </div>
  )
}
