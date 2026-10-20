"use client"

import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { getProjectTask } from "@/features/chat/api"
import { queryKeys } from "@/lib/api/query-keys"

export function TaskDetail({ projectId, taskId }: { projectId: string; taskId: string }) {
  const detail = useQuery({
    queryKey: queryKeys.taskBoard(projectId, taskId),
    queryFn: () => getProjectTask(projectId, taskId),
  })
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Task" description="Every handoff note and review round for this task, in order." />
      <p className="text-sm">
        <Link href={`/chat/${projectId}`} className="underline">
          Back to chat
        </Link>
      </p>
      <QueryBody query={detail} emptyTitle="Task not found" emptyDescription="This task has no board records yet.">
        {(board) => (
          <div className="flex flex-col gap-4">
            <section className="rounded border p-3" data-task={board.task.id}>
              <h2 className="text-sm font-medium">Task</h2>
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
            {board.events.map((event, index) => (
              <article key={`${event.kind}-${index}`} className="rounded border p-3" data-board-kind={event.kind}>
                <p className="text-xs uppercase text-muted-foreground">
                  {event.kind === "handoff" ? "Handoff note" : event.kind === "notes" ? "Project notes" : "Review feedback"}
                </p>
                {event.kind === "handoff" ? (
                  <HandoffBody event={event as unknown as Record<string, unknown>} />
                ) : event.kind === "notes" ? (
                  <NotesBody event={event as unknown as Record<string, unknown>} />
                ) : (
                  <FeedbackBody event={event as unknown as Record<string, unknown>} />
                )}
              </article>
            ))}
          </div>
        )}
      </QueryBody>
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
