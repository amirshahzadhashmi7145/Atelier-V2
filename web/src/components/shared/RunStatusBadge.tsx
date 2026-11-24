import { cn } from "cn"
import type { components } from "@/lib/api/generated/types"

type RunStatus = components["schemas"]["RunStatus"]

const tone = {
  neutral: "bg-muted text-muted-foreground",
  info: "bg-info-surface text-info",
  warning: "bg-warning-surface text-warning",
  success: "bg-success-surface text-success",
  danger: "bg-destructive/10 text-destructive",
} as const

const statuses: Record<RunStatus, { label: string; tone: keyof typeof tone; live?: boolean }> = {
  queued: { label: "Queued", tone: "neutral" },
  running: { label: "Running", tone: "info", live: true },
  waiting_client: { label: "Waiting for client", tone: "warning" },
  waiting_user: { label: "Waiting for you", tone: "warning" },
  completed: { label: "Completed", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
}

/** A run's state, named in plain words and coloured by what it asks of the reader. */
export function RunStatusBadge({ status, className }: { status: RunStatus; className?: string }) {
  const entry = statuses[status] ?? { label: status, tone: "neutral" as const }
  return (
    <span
      data-status={status}
      className={cn(
        "inline-flex h-5 w-fit shrink-0 items-center gap-1.5 rounded-full px-2 text-xs font-medium whitespace-nowrap",
        tone[entry.tone],
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn("size-1.5 rounded-full bg-current", entry.live && "motion-safe:animate-pulse")}
      />
      {entry.label}
    </span>
  )
}
