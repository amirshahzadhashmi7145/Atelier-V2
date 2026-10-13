import { ChatPage } from "../chat-page"

export const instant = false

export default async function ProjectChatPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  return <ChatPage projectId={projectId} />
}
