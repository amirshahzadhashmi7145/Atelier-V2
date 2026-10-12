"use client"

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { createDataSource, createStack, importLibraryItem, listEditorSkills } from "@/features/agents/api"
import { queryKeys } from "@/lib/api/query-keys"

export function StackSheet({ onCreated }: { onCreated: (id: string) => void }) {
  const queryClient = useQueryClient()
  const skills = useQuery({ queryKey: queryKeys.skills, queryFn: listEditorSkills })
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [version, setVersion] = useState("")
  const [packages, setPackages] = useState("")
  const [scaffoldKind, setScaffoldKind] = useState<"none" | "command" | "repo">("none")
  const [scaffoldValue, setScaffoldValue] = useState("")
  const [skillIds, setSkillIds] = useState<string[]>([])
  const [docs, setDocs] = useState("")
  const created = useMutation({
    mutationFn: async () => {
      const refs = docs.split("\n").map((line) => line.trim()).filter(Boolean)
      const dataSourceIds: string[] = []
      for (const ref of refs) {
        const source = await createDataSource({ name: ref, kind: "url", ref, refreshPolicy: "manual" })
        dataSourceIds.push(source.id)
      }
      return createStack({
        name,
        version,
        packageAllowList: packages.split(",").map((item) => item.trim()).filter(Boolean),
        scaffoldTemplate: scaffoldKind === "none" ? null : scaffoldValue,
        skillIds,
        dataSourceIds,
      })
    },
    onSuccess: async (stack) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.stacks })
      toast.success("Stack created")
      onCreated(stack.id)
      setOpen(false)
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not create the stack"),
  })
  const imported = useMutation({
    mutationFn: (id: string) => importLibraryItem(id),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.stacks })
      toast.success("Stack imported")
      if (result.kind === "stack") onCreated(result.id)
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Import failed"),
  })

  return (
    <div className="flex flex-wrap gap-2">
      <Button type="button" variant="outline" onClick={() => setOpen(true)}>
        New stack
      </Button>
      <Button type="button" variant="outline" disabled={imported.isPending} onClick={() => imported.mutate("react")}>
        Import React
      </Button>
      <Button type="button" variant="outline" disabled={imported.isPending} onClick={() => imported.mutate("nextjs")}>
        Import Next.js
      </Button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="overflow-auto sm:max-w-md">
          <SheetHeader>
            <SheetTitle>New stack</SheetTitle>
          </SheetHeader>
          <FieldGroup className="px-4">
            <Field>
              <FieldLabel htmlFor="stack-name">Name</FieldLabel>
              <Input id="stack-name" value={name} onChange={(event) => setName(event.target.value)} />
            </Field>
            <Field>
              <FieldLabel htmlFor="stack-version">Version</FieldLabel>
              <Input id="stack-version" value={version} onChange={(event) => setVersion(event.target.value)} />
            </Field>
            <Field>
              <FieldLabel htmlFor="stack-packages">Package allow-list</FieldLabel>
              <Input
                id="stack-packages"
                placeholder="react, zod"
                value={packages}
                onChange={(event) => setPackages(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="stack-scaffold">Scaffold</FieldLabel>
              <select
                id="stack-scaffold"
                className="h-8 rounded-lg border border-input bg-background px-2.5 text-sm text-foreground"
                value={scaffoldKind}
                onChange={(event) => setScaffoldKind(event.target.value as "none" | "command" | "repo")}
              >
                <option value="none">none</option>
                <option value="command">command</option>
                <option value="repo">repo URL</option>
              </select>
            </Field>
            {scaffoldKind !== "none" ? (
              <Field>
                <FieldLabel htmlFor="stack-scaffold-value">{scaffoldKind === "command" ? "Command" : "Repo URL"}</FieldLabel>
                <Input id="stack-scaffold-value" value={scaffoldValue} onChange={(event) => setScaffoldValue(event.target.value)} />
              </Field>
            ) : null}
            <Field>
              <FieldLabel>Attached skills</FieldLabel>
              <div className="flex flex-col gap-1">
                {(skills.data ?? []).map((skill) => (
                  <label key={skill.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={skillIds.includes(skill.id)}
                      onChange={(event) =>
                        setSkillIds((current) =>
                          event.target.checked ? [...current, skill.id] : current.filter((id) => id !== skill.id),
                        )
                      }
                    />
                    {skill.name}
                  </label>
                ))}
              </div>
            </Field>
            <Field>
              <FieldLabel htmlFor="stack-docs">Docs sources</FieldLabel>
              <textarea
                id="stack-docs"
                className="min-h-20 rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm"
                placeholder="One URL per line"
                value={docs}
                onChange={(event) => setDocs(event.target.value)}
              />
            </Field>
            <Button type="button" disabled={created.isPending || !name.trim() || !version.trim()} onClick={() => created.mutate()}>
              {created.isPending ? "Saving…" : "Create stack"}
            </Button>
          </FieldGroup>
        </SheetContent>
      </Sheet>
    </div>
  )
}
