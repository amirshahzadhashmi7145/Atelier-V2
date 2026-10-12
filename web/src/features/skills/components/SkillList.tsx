"use client"

import { useQuery } from "@tanstack/react-query"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { listSkills } from "@/features/skills/api"
import { queryKeys } from "@/lib/api/query-keys"

export function SkillList() {
  const query = useQuery({ queryKey: queryKeys.skills, queryFn: listSkills })
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Skills"
        description="Instructions an agent loads by name. The editor arrives in a later session."
      />
      <QueryBody
        query={query}
        emptyTitle="No skills yet"
        emptyDescription="Import a skill or add one from the editor."
      >
        {(skills) => (
          <ul className="flex flex-col gap-3">
            {skills.map((skill) => (
              <li key={skill.id}>
                <Card>
                  <CardHeader>
                    <CardTitle>{skill.name}</CardTitle>
                    <CardDescription>{skill.description}</CardDescription>
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
