import { RunView } from "@/features/runs/components/RunView"

export const instant = false

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return <RunView id={id} />
}
