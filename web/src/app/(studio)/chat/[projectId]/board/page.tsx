import ProjectBoard from "@/features/chat/components/ProjectBoard"

export const instant = false

export default async function ProjectBoardPage({
  params,
}: {
  params: Promise<{ projectId: string }>
}) {
  const { projectId } = await params
  return <ProjectBoard projectId={projectId} />
}
