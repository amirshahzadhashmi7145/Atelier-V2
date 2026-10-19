import { TaskDetail } from "@/features/chat/components/TaskDetail"

export const instant = false

export default async function TaskBoardPage({
  params,
}: {
  params: Promise<{ projectId: string; taskId: string }>
}) {
  const { projectId, taskId } = await params
  return <TaskDetail projectId={projectId} taskId={taskId} />
}
