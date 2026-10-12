"use client"

import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { QueryBody } from "@/components/shared/QueryBody"
import { Button } from "@/components/ui/button"
import { ImportSheet } from "@/features/skills/components/ImportSheet"
import { listSkills } from "@/features/skills/api"
import { queryKeys } from "@/lib/api/query-keys"

export function SkillRail() {
  const query = useQuery({ queryKey: queryKeys.skills, queryFn: listSkills })
  return (
    <aside className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <Button nativeButton={false} render={<Link href="/skills/new" />}>
          New skill
        </Button>
        <ImportSheet />
      </div>
      <QueryBody query={query} emptyTitle="No skills yet" emptyDescription="Create a skill or import one.">
        {(skills) => (
          <ul className="flex flex-col gap-1">
            {skills.map((skill) => (
              <li key={skill.id}>
                <Link className="text-sm underline-offset-4 hover:underline" href={`/skills/${skill.id}`}>
                  {skill.name}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </QueryBody>
    </aside>
  )
}
