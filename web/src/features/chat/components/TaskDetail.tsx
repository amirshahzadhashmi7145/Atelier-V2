"use client"

import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { BoardCard } from "@/features/chat/components/ProjectBoard"
import { getProjectTask } from "@/features/chat/api"
import { queryKeys } from "@/lib/api/query-keys"

export function TaskDetail({ projectId, taskId }: { projectId: string; taskId: string }) {
  const detail = useQuery({
    queryKey: queryKeys.taskBoard(projectId, taskId),
    queryFn: () => getProjectTask(projectId, taskId),
  })
  return (
    <div className="flex h-full min-h-0 flex-col gap-6 overflow-auto p-6">
      <PageHeader title="Task" description="Every handoff note and review round for this task, in order." />
      <p className="text-sm">
        <Link href={`/chat/${projectId}/board`} className="underline">
          Project task board
        </Link>
      </p>
      <QueryBody query={detail} emptyTitle="Task not found" emptyDescription="This task has no board records yet.">
        {(board) => <BoardCard board={board} />}
      </QueryBody>
    </div>
  )
}
