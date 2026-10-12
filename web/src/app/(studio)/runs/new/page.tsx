import { Suspense } from "react"
import { NewRun } from "@/features/runs/components/NewRun"
import { Skeleton } from "@/components/ui/skeleton"

export const instant = false

export default function NewRunPage() {
  return (
    <Suspense fallback={<Skeleton className="h-40 w-full" />}>
      <NewRun />
    </Suspense>
  )
}
