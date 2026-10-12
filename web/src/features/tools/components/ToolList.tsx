"use client"

import { useQuery } from "@tanstack/react-query"
import { PageHeader } from "@/components/shared/PageHeader"
import { PermissionBadge } from "@/components/shared/PermissionBadge"
import { QueryBody } from "@/components/shared/QueryBody"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { listTools } from "@/features/tools/api"
import { queryKeys } from "@/lib/api/query-keys"

export function ToolList() {
  const query = useQuery({ queryKey: queryKeys.tools, queryFn: listTools })
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Tools"
        description="Built-in tools the runtime can allow. The registry tabs arrive next."
      />
      <QueryBody
        query={query}
        emptyTitle="No tools yet"
        emptyDescription="Built-in tools are part of the runtime. Control tools stay hidden."
      >
        {(tools) => (
          <ul className="flex flex-col gap-3">
            {tools.map((tool) => (
              <li key={tool.id}>
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      {tool.name}
                      <PermissionBadge permission={tool.permission} />
                    </CardTitle>
                    <CardDescription>{tool.description}</CardDescription>
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
