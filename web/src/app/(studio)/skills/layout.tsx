import { PageHeader } from "@/components/shared/PageHeader"
import { SkillRail } from "@/features/skills/components/SkillRail"

export const instant = false

export default function SkillsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Skills" description="Instructions an agent loads by name." />
      <div className="grid items-start gap-6 md:grid-cols-[16rem_1fr]">
        <SkillRail />
        {children}
      </div>
    </div>
  )
}
