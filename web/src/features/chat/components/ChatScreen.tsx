"use client"

import { useState, type ReactNode } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { answerChat, closeProject, createProject, getChatRun, getProject, listChatAgents, listMessages, listProjects, postMessage, type ChatMessage } from "@/features/chat/api"
import { queryKeys } from "@/lib/api/query-keys"
import { isTerminal } from "@/lib/runs/events"

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

  return (
    <div className="flex h-[calc(100vh-1rem)] min-h-0 w-full min-w-0">
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
      <section className="flex min-w-0 flex-1 flex-col gap-3 p-4">
        {project.data?.localMode ? (
          <p className="rounded bg-yellow-100 px-3 py-2 text-sm text-yellow-950">
            DEV LOCAL MODE. Commands run on this machine, inside the project folder only.
          </p>
        ) : null}
        {projectId && project.data ? (
          <div className="flex items-center justify-between gap-2">
            <h1 className="text-lg font-semibold">{project.data.name}</h1>
            <div className="flex gap-2">
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
        ) : (
          <p className="text-sm text-muted-foreground">Choose a project or create one.</p>
        )}
        <div className="flex flex-1 flex-col gap-3 overflow-auto">
          {(messages.data ?? []).map((message) => (
            <article key={message.id} className="flex flex-col gap-2 rounded border p-3">
              <p className="text-xs uppercase text-muted-foreground">{message.role}</p>
              <p className="whitespace-pre-wrap text-sm">{message.text}</p>
              {message.runId ? <RunFollow message={message} renderRun={renderRun} /> : null}
            </article>
          ))}
        </div>
        {projectId ? <Composer projectId={projectId} /> : null}
      </section>
      <aside className="hidden w-72 shrink-0 border-l p-3 xl:block">
        {project.data?.previewUrl ? (
          <iframe key={project.data.previewUrl} title="Project preview" src={project.data.previewUrl} className="h-full min-h-64 w-full rounded border" />
        ) : (
          <p className="text-sm text-muted-foreground">The preview appears here when a run finishes.</p>
        )}
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
  const [text, setText] = useState("")
  const send = useMutation({
    mutationFn: () => postMessage(projectId, text),
    onSuccess: async () => {
      setText("")
      await queryClient.invalidateQueries({ queryKey: queryKeys.messages(projectId) })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not send"),
  })
  return (
    <form
      className="flex gap-2"
      onSubmit={(event) => {
        event.preventDefault()
        if (text.trim()) send.mutate()
      }}
    >
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
    </form>
  )
}

function RunFollow({
  message,
  renderRun,
}: {
  message: ChatMessage
  renderRun?: (id: string) => ReactNode
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
  if (!run.data) return null
  if (message.role === "user" && running.has(run.data.status)) {
    return (
      <div className="flex flex-col gap-2">
        <Button type="button" variant="outline" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "Collapse" : "Working"}
        </Button>
        {expanded && renderRun ? renderRun(runId) : null}
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
    return (
      <div className="flex flex-col gap-1 text-sm">
        <p>{run.data.summary.filesChanged.join(", ") || "No files changed"}</p>
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
