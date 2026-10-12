import { StudioShell } from "@/components/shared/StudioShell"

export const instant = false

export default function StudioLayout({ children }: { children: React.ReactNode }) {
  return <StudioShell>{children}</StudioShell>
}
