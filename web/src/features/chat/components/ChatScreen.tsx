"use client"

import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  addProjectMember,
  approveProjectPlan,
  editProjectPlan,
  closeProject,
  createProject,
  deleteProject,
  getProject,
  patchProject,
  listChatAgents,
  listMessages,
  listProjectNeeds,
  listProjects,
  answerNeed,
  postMessage,
  stopChatRun,
  type ChatMessage,
  type Project,
} from "@/features/chat/api"
import { queryKeys } from "@/lib/api/query-keys"
import { LiveText } from "./LiveText"
import { RunFollow } from "./RunFollow"

export function ChatScreen({
  projectId,
  renderRun,
}: {
  projectId?: string
  renderRun?: (id: string) => ReactNode
}) {
  const router = useRouter()
  const projects = useQuery({ queryKey: queryKeys.projects, queryFn: listProjects })
  const queryClient = useQueryClient()
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
  const threadRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)
  const [away, setAway] = useState(false)
  const [activity, setActivity] = useState(0)
  const [showPreview, setShowPreview] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
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
          <p className="rounded border bg-muted px-3 py-2 text-sm text-foreground">
            DEV LOCAL MODE. Commands run on this machine, inside the project folder only.
          </p>
        ) : null}
        {projectId && project.data ? (
          <div className="flex max-h-[45%] shrink-0 flex-col gap-2 overflow-auto">
            <NeedsYou projectId={projectId} />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h1 className="text-lg font-semibold">{project.data.name}</h1>
              <div className="flex flex-wrap items-center gap-2">
                <Button nativeButton={false} variant="outline" render={<Link href={`/chat/${projectId}/board`} data-project-board />}>
                  Task board
                </Button>
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
                    void closeProject(projectId)
                      .then(() => {
                        toast.success("Preview stopped")
                        return queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) })
                      })
                      .catch((error) => toast.error(error instanceof Error ? error.message : "Could not stop preview"))
                  }}
                >
                  Stop preview
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  aria-expanded={showSettings}
                  onClick={() => setShowSettings((value) => !value)}
                >
                  {showSettings ? "Hide settings" : "Project settings"}
                </Button>
                <span className="h-5 border-l" aria-hidden />
                <Button
                  type="button"
                  variant="destructive"
                  onClick={() => {
                    if (!projectId || !project.data) return
                    if (!window.confirm(`Delete “${project.data.name}” from the studio? Files on disk are kept.`)) return
                    void deleteProject(projectId)
                      .then(async () => {
                        await queryClient.invalidateQueries({ queryKey: queryKeys.projects })
                        toast.success("Project deleted")
                        router.push("/chat")
                      })
                      .catch((error) => toast.error(error instanceof Error ? error.message : "Could not delete project"))
                  }}
                >
                  Delete project
                </Button>
              </div>
            </div>
            {project.data.summary ? <p className="text-sm text-muted-foreground">{project.data.summary}</p> : null}
            {showSettings ? (
              <div className="flex flex-col gap-2">
                <MemberPanel projectId={projectId} project={project.data} />
                <NotesSettings key={projectId} projectId={projectId} project={project.data} />
              </div>
            ) : null}
            <SupervisorSteps steps={project.data.supervisorSteps} />
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
              {projectId && messages.data && messages.data.length === 0 ? (
                <EmptyState title="No messages yet" description="Describe what you want built and the agent gets to work." />
              ) : null}
              {(messages.data ?? []).map((message) => {
                const mine = message.role === "user"
                return (
                  <article
                    key={message.id}
                    className={`flex w-fit min-w-0 max-w-[85%] flex-col gap-2 rounded border p-3 ${
                      mine ? "self-end bg-primary/10" : "self-start bg-card"
                    }`}
                  >
                    <p className="flex items-center gap-2 text-xs uppercase text-muted-foreground">
                      <span style={message.agentColor ? { color: message.agentColor } : undefined} data-agent={message.agentName}>
                        {message.agentName ?? message.role}
                      </span>
                      {message.label ? (
                        <span data-label={message.label} className="rounded-full border px-2 py-0.5 normal-case">
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
                      <time dateTime={message.createdAt} className="normal-case">
                        {new Date(message.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </time>
                    </p>
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
                        onActivity={() => setActivity((value) => value + 1)}
                      />
                    ) : null}
                  </article>
                )
              })}
              <LiveWork
                steps={project.data?.supervisorSteps}
                threadRunIds={new Set((messages.data ?? []).map((item) => item.runId).filter((id): id is string => Boolean(id)))}
              />
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
        {projectId ? <Composer projectId={projectId} project={project.data} /> : null}
      </section>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize preview"
        onPointerDown={startPreviewResize}
        className="hidden w-1.5 shrink-0 cursor-col-resize bg-border transition-colors hover:bg-primary/40 xl:block"
      />
      <aside
        className="hidden h-full min-h-0 shrink-0 flex-col border-l p-3 xl:flex"
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

function SupervisorSteps({ steps }: { steps?: Project["supervisorSteps"] }) {
  if (!steps?.length) return null
  return (
    <div className="rounded border p-2 text-sm" data-supervisor-steps>
      <ul className="flex flex-wrap gap-x-4 gap-y-1">
        {steps.map((item) => (
          <li key={item.taskId} data-supervisor-step={item.step} data-task-id={item.taskId}>
            <span className="font-medium">
              {item.agentName ? `${item.agentName} · ` : ""}
              {STEP_LABEL[item.step] ?? item.step}
            </span>
            {item.label ? <span className="text-muted-foreground"> — {item.label}</span> : null}
          </li>
        ))}
      </ul>
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

function NotesSettings({ projectId, project }: { projectId: string; project: Project }) {
  const queryClient = useQueryClient()
  const [path, setPath] = useState(project.notesPath || ".atelier/NOTES.md")
  const [maxBytes, setMaxBytes] = useState(String(project.notesMaxBytes ?? 8192))
  const save = useMutation({
    mutationFn: () => patchProject(projectId, { notesPath: path, notesMaxBytes: Number(maxBytes) }),
    onSuccess: async () => {
      toast.success("Project notes settings saved")
      await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not save notes settings"),
  })
  return (
    <form
      className="flex flex-wrap items-end gap-2 text-sm"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate()
      }}
    >
      <label className="flex flex-col gap-1">
        Notes file
        <input className="rounded border px-2 py-1" value={path} onChange={(event) => setPath(event.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        Size limit (bytes)
        <input className="w-28 rounded border px-2 py-1" value={maxBytes} onChange={(event) => setMaxBytes(event.target.value)} />
      </label>
      <Button type="submit" variant="outline" disabled={save.isPending}>
        {save.isPending ? "Saving…" : "Save notes settings"}
      </Button>
    </form>
  )
}

function MemberPanel({ projectId, project }: { projectId: string; project: Project }) {
  const queryClient = useQueryClient()
  const agents = useQuery({ queryKey: queryKeys.agents, queryFn: listChatAgents })
  const [agentId, setAgentId] = useState("")
  const [overlap, setOverlap] = useState("")
  const memberIds = new Set(project.members ?? [])
  const candidates = (agents.data ?? []).filter((agent) => !memberIds.has(agent.id))
  const add = useMutation({
    mutationFn: () => addProjectMember(projectId, agentId),
    onSuccess: async () => {
      setAgentId("")
      setOverlap("")
      await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) })
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "Could not add agent"
      toast.error(message)
      setOverlap(message)
    },
  })
  return (
    <div className="rounded border p-2 text-sm">
      <p className="mb-1 font-medium">Project members</p>
      <ul className="flex flex-col gap-2">
        {(project.memberDetails ?? []).map((member) => (
          <li key={member.agentId}>
            <p style={{ color: member.color }} className="font-medium" data-member={member.name}>
              {member.name}
            </p>
            <p className="text-xs text-muted-foreground">
              {member.lastTask && member.lastTaskId ? (
                <Link href={`/chat/${projectId}/board#${member.lastTaskId}`} className="underline">
                  Last: {member.lastTask}
                </Link>
              ) : member.lastTask ? (
                `Last: ${member.lastTask}`
              ) : (
                "No tasks yet"
              )}
            </p>
          </li>
        ))}
      </ul>
      {overlap ? (
        <p className="mt-2 text-xs text-destructive" data-zone-overlap="true">
          {overlap}
        </p>
      ) : null}
      <form
        className="mt-2 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          if (agentId) add.mutate()
        }}
      >
        <label className="sr-only" htmlFor="add-member">
          Add agent to project
        </label>
        <select
          id="add-member"
          className="flex-1 rounded border px-2 py-1"
          value={agentId}
          onChange={(event) => setAgentId(event.target.value)}
        >
          <option value="">Choose agent</option>
          {candidates.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name}
            </option>
          ))}
        </select>
        <Button type="submit" variant="outline" disabled={!agentId || add.isPending}>
          {add.isPending ? "Adding…" : "Add agent to project"}
        </Button>
      </form>
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

function Composer({ projectId, project }: { projectId: string; project?: Project }) {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const [text, setText] = useState("")
  const send = useMutation({
    mutationFn: () => postMessage(projectId, text),
    onSuccess: async () => {
      setText("")
      await queryClient.invalidateQueries({ queryKey: queryKeys.messages(projectId) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.needs(projectId) })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not send"),
  })
  const stop = useMutation({
    mutationFn: () => stopChatRun(project?.activeRunId ?? ""),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.messages(projectId) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) })
    },
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
    if (text.trim() && !send.isPending) send.mutate()
  }
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      {working ? (
        <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
          <span>{workingLabel}</span>
          <Button type="button" variant="outline" disabled={stop.isPending} onClick={() => stop.mutate()}>
            {stop.isPending ? "Stopping…" : "Stop"}
          </Button>
        </div>
      ) : null}
      <div className="flex items-end gap-2">
        <label className="sr-only" htmlFor="chat-message">
          Message
        </label>
        <textarea
          id="chat-message"
          ref={inputRef}
          rows={1}
          className="max-h-40 flex-1 resize-none rounded border bg-background px-2 py-1.5 text-sm"
          value={text}
          disabled={send.isPending}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
          }}
        />
        <Button type="submit" disabled={send.isPending || !text.trim()}>
          {send.isPending ? "Sending…" : "Send"}
        </Button>
      </div>
    </form>
  )
}

function PreviewPane({ url }: { url?: string | null }) {
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
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-1 w-fit"
          onClick={() => {
            void navigator.clipboard.writeText(url)
            toast.success("Preview URL copied")
          }}
        >
          Copy URL
        </Button>
      </div>
      <iframe key={url} title="Project preview" src={url} className="min-h-48 w-full flex-1 rounded border" />
    </div>
  )
}
