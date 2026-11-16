"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useQuery } from "@tanstack/react-query"
import { QueryBody } from "@/components/shared/QueryBody"
import { Button } from "@/components/ui/button"
import { ImportSheet } from "@/features/skills/components/ImportSheet"
import { listSkills } from "@/features/skills/api"
import { queryKeys } from "@/lib/api/query-keys"

export function SkillRail() {
  const query = useQuery({ queryKey: queryKeys.skills, queryFn: listSkills })
  const pathname = usePathname()
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
          <ul className="-mx-2 flex flex-col gap-0.5">
            {skills.map((skill) => (
              <li key={skill.id}>
                <Link
                  href={`/skills/${skill.id}`}
                  aria-current={pathname === `/skills/${skill.id}` ? "page" : undefined}
                  className="block truncate rounded-md px-2 py-1.5 text-sm outline-none transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 aria-[current=page]:bg-muted aria-[current=page]:font-medium"
                >
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
