import { redirect } from "next/navigation"

export const instant = false

export default async function TaskBoardPage({
  params,
}: {
  params: Promise<{ projectId: string; taskId: string }>
}) {
  const { projectId, taskId } = await params
  redirect(`/chat/${projectId}/board#${taskId}`)
}
