"use client"

import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { draftTeachRules, teachAgent } from "@/features/agents/api"
import { queryKeys } from "@/lib/api/query-keys"

export function TeachSheet({ agentId, onSaved }: { agentId: string; onSaved: () => void }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [version, setVersion] = useState("")
  const [rules, setRules] = useState("")
  const [docsUrl, setDocsUrl] = useState("")
  const [packages, setPackages] = useState("")
  const [scaffold, setScaffold] = useState("")
  const [repoUrl, setRepoUrl] = useState("")

  const save = useMutation({
    mutationFn: () =>
      teachAgent(agentId, {
        name,
        version,
        rules,
        docsUrl: docsUrl || undefined,
        packages: packages.split(",").map((item) => item.trim()).filter(Boolean),
        scaffold: scaffold || undefined,
      }),
    onSuccess: async () => {
      setOpen(false)
      onSaved()
      await queryClient.invalidateQueries({ queryKey: queryKeys.agent(agentId) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.skills })
      await queryClient.invalidateQueries({ queryKey: queryKeys.stacks })
      await queryClient.invalidateQueries({ queryKey: queryKeys.dataSources })
      toast.success("Taught")
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not teach"),
  })

  const draft = useMutation({
    mutationFn: () => draftTeachRules(agentId, repoUrl),
    onSuccess: (result) => setRules(result.rules),
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not draft rules"),
  })

  return (
    <>
      <Button type="button" variant="outline" onClick={() => setOpen(true)}>
        Teach
      </Button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="overflow-auto sm:max-w-md">
          <SheetHeader>
            <SheetTitle>Teach</SheetTitle>
            <SheetDescription>Add a skill, a stack, and docs for this agent in one step.</SheetDescription>
          </SheetHeader>
          <form
            className="flex flex-col gap-3 px-4"
            onSubmit={(event) => {
              event.preventDefault()
              save.mutate()
            }}
          >
            <Field>
              <FieldLabel htmlFor="teach-name">Tech name</FieldLabel>
              <Input id="teach-name" value={name} onChange={(event) => setName(event.target.value)} />
            </Field>
            <Field>
              <FieldLabel htmlFor="teach-version">Version</FieldLabel>
              <Input id="teach-version" value={version} onChange={(event) => setVersion(event.target.value)} />
            </Field>
            <Field>
              <FieldLabel htmlFor="teach-rules">Rules</FieldLabel>
              <textarea
                id="teach-rules"
                className="min-h-32 w-full rounded border px-2 py-1 text-sm"
                value={rules}
                onChange={(event) => setRules(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="teach-docs">Docs URL</FieldLabel>
              <Input id="teach-docs" value={docsUrl} onChange={(event) => setDocsUrl(event.target.value)} />
            </Field>
            <Field>
              <FieldLabel htmlFor="teach-packages">Allowed package names</FieldLabel>
              <Input id="teach-packages" value={packages} onChange={(event) => setPackages(event.target.value)} placeholder="hono, zod" />
            </Field>
            <Field>
              <FieldLabel htmlFor="teach-scaffold">Scaffold command</FieldLabel>
              <Input id="teach-scaffold" value={scaffold} onChange={(event) => setScaffold(event.target.value)} />
            </Field>
            <Field>
              <FieldLabel htmlFor="teach-repo">Repo URL</FieldLabel>
              <Input id="teach-repo" value={repoUrl} onChange={(event) => setRepoUrl(event.target.value)} />
            </Field>
            <Button type="button" variant="outline" disabled={!repoUrl || draft.isPending} onClick={() => draft.mutate()}>
              {draft.isPending ? "Drafting…" : "Draft rules"}
            </Button>
            <Button type="submit" disabled={save.isPending || !name.trim() || !version.trim() || !rules.trim()}>
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </form>
        </SheetContent>
      </Sheet>
    </>
  )
}
