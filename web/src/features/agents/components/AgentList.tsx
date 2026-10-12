"use client"

import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { Button } from "@/components/ui/button"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { listAgents } from "@/features/agents/api"
import { queryKeys } from "@/lib/api/query-keys"

export function AgentList() {
  const query = useQuery({ queryKey: queryKeys.agents, queryFn: listAgents })
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <PageHeader title="Agents" description="Nothing is installed until you create an agent or import one." />
        <Button nativeButton={false} render={<Link href="/agents/new" />}>
          New agent
        </Button>
      </div>
      <QueryBody
        query={query}
        emptyTitle="No agents yet"
        emptyDescription="Create an agent or import a template from the library."
      >
        {(agents) => (
          <ul className="flex flex-col gap-3">
            {agents.map((agent) => (
              <li key={agent.id}>
                <Card>
                  <CardHeader>
                    <CardTitle>
                      <Link href={`/agents/${agent.id}`}>{agent.name}</Link>
                    </CardTitle>
                    <CardDescription>{agent.description}</CardDescription>
                  </CardHeader>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </QueryBody>
    </div>
  )
}
