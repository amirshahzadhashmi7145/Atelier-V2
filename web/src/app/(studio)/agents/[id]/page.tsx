import { AgentEditor } from "@/features/agents/components/AgentEditor"

export const instant = false

export default async function AgentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return <AgentEditor id={id} />
}
