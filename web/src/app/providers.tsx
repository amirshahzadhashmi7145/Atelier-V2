"use client"

import { useEffect, useState } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { TooltipProvider } from "@/components/ui/tooltip"

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1 } },
})

let mocksReady: Promise<void> | undefined

function ensureMocks() {
  mocksReady ??= import("@/mocks/browser")
    .then(({ worker }) => worker.start({ onUnhandledRequest: "bypass" }))
    .then(() => undefined)
  return mocksReady
}

export function AppProviders({ children }: { children: React.ReactNode }) {
  const mocks = process.env.NEXT_PUBLIC_USE_MOCKS === "true"
  const [ready, setReady] = useState(!mocks)

  useEffect(() => {
    if (!mocks) return
    let cancelled = false
    void ensureMocks().then(() => {
      if (!cancelled) setReady(true)
    })
    return () => {
      cancelled = true
    }
  }, [mocks])

  if (!ready) {
    return <p className="p-6 text-sm text-muted-foreground">Loading studio…</p>
  }

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>{children}</TooltipProvider>
    </QueryClientProvider>
  )
}
