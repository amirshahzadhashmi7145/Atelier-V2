"use client"

import type { ReactNode } from "react"
import type { UseQueryResult } from "@tanstack/react-query"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { Skeleton } from "@/components/ui/skeleton"

export function QueryBody<T>({
  query,
  emptyTitle,
  emptyDescription,
  children,
}: {
  query: UseQueryResult<T>
  emptyTitle: string
  emptyDescription: string
  children: (data: T) => ReactNode
}) {
  if (query.isPending) {
    return (
      <div className="flex flex-col gap-3" aria-busy="true">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    )
  }
  if (query.isError) {
    const message = query.error instanceof Error ? query.error.message : "Request failed"
    return <ErrorState message={message} onRetry={() => void query.refetch()} />
  }
  if (query.data === undefined || (Array.isArray(query.data) && query.data.length === 0)) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />
  }
  return children(query.data)
}
