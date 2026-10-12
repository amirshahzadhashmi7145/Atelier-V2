"use client"

import { useQuery } from "@tanstack/react-query"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { listAgents } from "@/features/agents/api"
import { queryKeys } from "@/lib/api/query-keys"

export function AgentList() {
  const query = useQuery({ queryKey: queryKeys.agents, queryFn: listAgents })
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Agents"
        description="Roles you can run. The editor arrives in the next session."
      />
      <QueryBody
        query={query}
        emptyTitle="No agents yet"
        emptyDescription="Create an agent to give a role a prompt, tools, and stacks."
      >
        {(agents) => (
          <ul className="flex flex-col gap-3">
            {agents.map((agent) => (
              <li key={agent.id}>
                <Card>
                  <CardHeader>
                    <CardTitle>{agent.name}</CardTitle>
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
