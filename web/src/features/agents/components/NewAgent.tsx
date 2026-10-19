"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { createAgent, createVersion, importLibraryItem, listEditorModels, listLibrary, listRoles } from "@/features/agents/api"
import { asSchema, defaultsFromSchema } from "@/features/agents/config-schema"
import { queryKeys } from "@/lib/api/query-keys"

const blank = z.object({
  name: z.string().min(1, "Name the agent"),
  roleKey: z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, "Use a lowercase slug"),
  description: z.string().min(1, "Say what it does"),
  model: z.string().min(1, "Choose a model"),
})

type Blank = z.infer<typeof blank>

export function NewAgent() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const library = useQuery({ queryKey: queryKeys.library("agent"), queryFn: () => listLibrary("agent") })
  const models = useQuery({ queryKey: queryKeys.models, queryFn: listEditorModels })
  const roles = useQuery({ queryKey: queryKeys.roles, queryFn: listRoles })
  const form = useForm<Blank>({ defaultValues: { name: "", roleKey: "", description: "", model: "" } })
  const imported = useMutation({
    mutationFn: (id: string) => importLibraryItem(id),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.agents })
      if (result.kind === "agent") router.push(`/agents/${result.id}`)
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Import failed"),
  })
  const created = useMutation({
    mutationFn: async (values: Blank) => {
      const parsed = blank.safeParse(values)
      if (!parsed.success) throw new Error(parsed.error.issues[0]?.message ?? "Check the form")
      const model = models.data?.find((item) => item.name === parsed.data.model)
      if (!model) throw new Error("Refresh models in Settings first")
      const agent = await createAgent({
        name: parsed.data.name,
        roleKey: parsed.data.roleKey,
        description: parsed.data.description,
        model: {
          provider: model.provider,
          name: model.name,
          config: defaultsFromSchema(asSchema(model.configSchema)),
        },
        zones: ["src/**"],
      })
      await createVersion(agent.id, { role: "", goal: "", instructions: "", constraints: "", output: "" })
      return agent
    },
    onSuccess: (agent) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.agents })
      router.push(`/agents/${agent.id}`)
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not create the agent"),
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="New agent" description="Start blank, or import a template from the library." />
      <Card>
        <CardHeader>
          <CardTitle>Library</CardTitle>
          <CardDescription>Templates are not installed until you import one.</CardDescription>
        </CardHeader>
        <CardContent>
          <QueryBody query={library} emptyTitle="No templates" emptyDescription="The library has no agent templates.">
            {(items) => (
              <ul className="flex flex-col gap-3">
                {items.map((item) => (
                  <li key={item.id} className="flex items-center justify-between gap-3">
                    <span>
                      <span className="font-medium">{item.name}</span>
                      <span className="block text-sm text-muted-foreground">{item.description}</span>
                    </span>
                    <Button disabled={imported.isPending} onClick={() => imported.mutate(item.id)}>
                      {imported.isPending ? "Importing…" : `Import ${item.name}`}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </QueryBody>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Blank agent</CardTitle>
          <CardDescription>
            {(models.data ?? []).length === 0 ? (
              <>
                Refresh models in <Link href="/settings/providers">Settings</Link> before creating a blank agent.
              </>
            ) : (
              "Budgets start at 40 iterations, 30 minutes, and 400000 tokens."
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-4"
            onSubmit={form.handleSubmit((values) => created.mutate(values))}
          >
            <FieldGroup>
              <Field data-invalid={Boolean(form.formState.errors.name) || undefined}>
                <FieldLabel htmlFor="blank-name">Name</FieldLabel>
                <Input
                  id="blank-name"
                  aria-invalid={Boolean(form.formState.errors.name)}
                  onChange={(event) => form.setValue("name", event.target.value, { shouldValidate: true })}
                />
                <FieldError>{form.formState.errors.name?.message}</FieldError>
              </Field>
              <Field>
                <FieldLabel htmlFor="blank-role">Role key</FieldLabel>
                <Input id="blank-role" list="blank-role-options" onChange={(event) => form.setValue("roleKey", event.target.value)} />
                <datalist id="blank-role-options">
                  {(roles.data ?? []).map((role) => (
                    <option key={role.id} value={role.id}>
                      {role.name}
                    </option>
                  ))}
                </datalist>
              </Field>
              <Field>
                <FieldLabel htmlFor="blank-description">Description</FieldLabel>
                <Input
                  id="blank-description"
                  onChange={(event) => form.setValue("description", event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="blank-model">Model</FieldLabel>
                <select
                  id="blank-model"
                  className="h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm"
                  defaultValue=""
                  onChange={(event) => form.setValue("model", event.target.value)}
                >
                  <option value="">Choose a model</option>
                  {(models.data ?? []).map((model) => (
                    <option key={model.name} value={model.name}>
                      {model.name}
                    </option>
                  ))}
                </select>
              </Field>
            </FieldGroup>
            <Button type="submit" disabled={created.isPending || (models.data ?? []).length === 0}>
              {created.isPending ? "Creating…" : "Create agent"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
