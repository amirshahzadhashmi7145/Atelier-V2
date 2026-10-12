import { SkillScreen } from "@/features/skills/components/SkillScreen"

export const instant = false

export default async function SkillPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return <SkillScreen id={id} />
}
