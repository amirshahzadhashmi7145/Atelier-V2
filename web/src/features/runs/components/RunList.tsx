"use client"

import { useQuery } from "@tanstack/react-query"
import { EmptyState } from "@/components/shared/EmptyState"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { Badge } from "@/components/ui/badge"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { listRuns } from "@/features/runs/api"
import { queryKeys } from "@/lib/api/query-keys"

export function RunList() {
  const query = useQuery({ queryKey: queryKeys.runs(), queryFn: () => listRuns(1) })
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Runs"
        description="Past and live runs. The live view arrives with the runs session."
      />
      <QueryBody
        query={query}
        emptyTitle="No runs yet"
        emptyDescription="Start a run when an agent has an active prompt."
      >
        {(page) =>
          page.items.length === 0 ? (
            <EmptyState title="No runs yet" description="Start a run when an agent has an active prompt." />
          ) : (
            <ul className="flex flex-col gap-3">
              {page.items.map((run) => (
                <li key={run.id}>
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        {run.task}
                        <Badge variant="secondary">{run.status}</Badge>
                      </CardTitle>
                      <CardDescription>
                        {run.iterations} iterations · ${run.costUsd.toFixed(2)}
                      </CardDescription>
                    </CardHeader>
                  </Card>
                </li>
              ))}
            </ul>
          )
        }
      </QueryBody>
    </div>
  )
}
