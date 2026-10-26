"use client"

import { useEffect } from "react"
import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { listProjectTasks } from "@/features/chat/api"
import { queryKeys } from "@/lib/api/query-keys"
import type { components } from "@/lib/api/generated/types"

type TaskBoard = components["schemas"]["TaskBoard"]

export default function ProjectBoard({ projectId }: { projectId: string }) {
  const board = useQuery({
    queryKey: queryKeys.projectBoard(projectId),
    queryFn: () => listProjectTasks(projectId),
    refetchInterval: 2000,
  })
  const items = board.data?.items ?? []

  useEffect(() => {
    const id = window.location.hash.replace("#", "")
    if (!id) return
    document.getElementById(id)?.scrollIntoView({ block: "start" })
  }, [items])

  return (
    <div className="no-scrollbar flex h-full min-h-0 flex-col gap-6 overflow-auto p-6">
      <PageHeader title="Task board" description="Every agent on this project. One board, not one per task." />
      <p className="text-sm">
        <Link href={`/chat/${projectId}`} className="underline">
          Back to chat
        </Link>
      </p>
      <QueryBody query={board} emptyTitle="No tasks yet" emptyDescription="Approve a plan and work shows up here for every agent.">
        {(data) =>
          data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">No tasks yet. Approve a plan and work shows up here for every agent.</p>
          ) : (
            <div className="flex flex-col gap-8">
              {data.items.map((item) => (
                <BoardCard key={item.task.id} board={item} />
              ))}
            </div>
          )
        }
      </QueryBody>
    </div>
  )
}

export function BoardCard({ board }: { board: TaskBoard }) {
  return (
    <div className="flex flex-col gap-4" id={board.task.id} data-task={board.task.id}>
      <section className="rounded border p-3">
        <h2 className="text-sm font-medium">{board.agentName || "Task"}</h2>
        <p className="whitespace-pre-wrap text-sm">{board.task.text}</p>
        <p className="mt-2 text-xs text-muted-foreground">
          Status {board.task.status}
          {typeof board.task.reworkCount === "number" ? ` · reworks ${board.task.reworkCount}` : ""}
        </p>
        {(board.task.acceptanceCriteria ?? []).length ? (
          <ul className="mt-2 list-disc pl-5 text-sm">
            {board.task.acceptanceCriteria?.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}
        {(board.sessionLogs ?? []).length ? (
          <ul className="mt-3 flex flex-col gap-1 text-sm">
            {board.sessionLogs?.map((log) => (
              <li key={log.runId}>
                <a href={log.url} className="underline" data-session-log={log.runId}>
                  OpenHands event log
                </a>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
      {board.events.map((event, index) => {
        const kind = String(event.kind)
        return (
          <article key={`${kind}-${index}`} className="rounded border p-3" data-board-kind={kind}>
            <p className="text-xs uppercase text-muted-foreground">
              {kind === "handoff"
                ? "Handoff note"
                : kind === "notes"
                  ? "Project notes"
                  : kind === "user"
                    ? "Your answer"
                    : "Review feedback"}
            </p>
            {kind === "handoff" ? (
              <HandoffBody event={event as unknown as Record<string, unknown>} />
            ) : kind === "notes" || kind === "user" ? (
              <NotesBody event={event as unknown as Record<string, unknown>} />
            ) : (
              <FeedbackBody event={event as unknown as Record<string, unknown>} />
            )}
          </article>
        )
      })}
    </div>
  )
}

function HandoffBody({ event }: { event: Record<string, unknown> }) {
  const files = Array.isArray(event.filesChanged) ? (event.filesChanged as string[]) : []
  const evidence = Array.isArray(event.evidence) ? (event.evidence as { criterion?: string; evidence?: string }[]) : []
  const questions = Array.isArray(event.openQuestions) ? (event.openQuestions as string[]) : []
  return (
    <div className="mt-2 flex flex-col gap-2 text-sm">
      <p className="whitespace-pre-wrap">{String(event.summary ?? "")}</p>
      {files.length ? <p>Files: {files.join(", ")}</p> : null}
      {evidence.map((item) => (
        <p key={item.criterion}>
          {item.criterion}: {item.evidence}
        </p>
      ))}
      {questions.length ? <p>Open questions: {questions.join("; ")}</p> : null}
    </div>
  )
}

function NotesBody({ event }: { event: Record<string, unknown> }) {
  return (
    <div className="mt-2 flex flex-col gap-2 text-sm">
      <p className="whitespace-pre-wrap">{String(event.summary ?? "")}</p>
      {event.path ? <p className="text-xs text-muted-foreground">{String(event.path)}</p> : null}
    </div>
  )
}

function FeedbackBody({ event }: { event: Record<string, unknown> }) {
  const items = Array.isArray(event.items) ? (event.items as { targetKind?: string; target?: string; wrong?: string; expected?: string }[]) : []
  return (
    <div className="mt-2 flex flex-col gap-2 text-sm">
      <p className="font-medium">{event.verdict === "approve" ? "Approved" : "Changes requested"}</p>
      {event.notes ? <p className="whitespace-pre-wrap">{String(event.notes)}</p> : null}
      {items.map((item, index) => (
        <p key={index}>
          {item.targetKind} {item.target}: {item.wrong} (expected {item.expected})
        </p>
      ))}
    </div>
  )
}
