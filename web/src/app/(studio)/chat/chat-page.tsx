"use client"

import { ChatScreen } from "@/features/chat/components/ChatScreen"
import { RunView } from "@/features/runs/components/RunView"

export function ChatPage({ projectId }: { projectId?: string }) {
  return <ChatScreen projectId={projectId} renderRun={(id) => <RunView id={id} embedded />} />
}
