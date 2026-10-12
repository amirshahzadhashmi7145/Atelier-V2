"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { diffVersions } from "@/features/agents/api"
import { MergeDiff } from "@/components/shared/MarkdownField"
import type { components } from "@/lib/api/generated/types"

type Version = components["schemas"]["PromptVersion"]

const sections = ["role", "goal", "instructions", "constraints", "output"] as const

export function VersionsDrawer({ id, versions }: { id: string; versions: Version[] }) {
  const [open, setOpen] = useState(false)
  const latest = versions.at(-1)
  const [against, setAgainst] = useState(0)
  const [section, setSection] = useState<(typeof sections)[number]>("role")
  const selectedAgainst = against || versions.find((item) => item.version !== latest?.version)?.version || 0
  const diff = useQuery({
    queryKey: ["diff", id, latest?.version, selectedAgainst],
    queryFn: () => diffVersions(id, latest!.version, selectedAgainst),
    enabled: open && Boolean(latest) && selectedAgainst > 0,
  })
  const row = diff.data?.sections.find((item) => item.path === section)

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger render={<Button variant="outline" />}>Versions</SheetTrigger>
      <SheetContent className="w-full sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Versions</SheetTitle>
          <SheetDescription>Compare two saved prompts.</SheetDescription>
        </SheetHeader>
        {versions.length < 2 || !latest ? (
          <p className="px-4 text-sm text-muted-foreground">Save another version to diff.</p>
        ) : (
          <div className="flex flex-col gap-4 px-4">
            <Field>
              <FieldLabel htmlFor="against">Compare with</FieldLabel>
              <select
                id="against"
                className="h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm"
                value={selectedAgainst}
                onChange={(event) => setAgainst(Number(event.target.value))}
              >
                {versions
                  .filter((item) => item.version !== latest.version)
                  .map((item) => (
                    <option key={item.version} value={item.version}>
                      Version {item.version}
                    </option>
                  ))}
              </select>
            </Field>
            <Field>
              <FieldLabel htmlFor="section">Section</FieldLabel>
              <select
                id="section"
                className="h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm"
                value={section}
                onChange={(event) => setSection(event.target.value as (typeof sections)[number])}
              >
                {sections.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </Field>
            {row ? <MergeDiff before={row.before} after={row.after} /> : <p className="text-sm">Loading diff…</p>}
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
