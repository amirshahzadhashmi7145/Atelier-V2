import { SettingsNav } from "@/features/settings/components/SettingsNav"

export const instant = false

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-6">
      <SettingsNav />
      {children}
    </div>
  )
}
