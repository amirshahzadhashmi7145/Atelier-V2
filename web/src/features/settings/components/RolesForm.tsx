"use client"

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { createRole, deleteLesson, listLessons, listRoles, resetRole, updateRole } from "@/features/settings/api"
import { queryKeys } from "@/lib/api/query-keys"
import type { components } from "@/lib/api/generated/types"

const SEED_ROLE_IDS = new Set(["frontend-engineer", "backend-engineer", "team-lead", "qa-engineer"])

type Role = components["schemas"]["Role"]

const empty: {
  name: string
  kind: "worker" | "supervisor"
  reportsTo: string
  layer: string
  zones: string
  tags: string
  colour: string
  contractFile: string
} = {
  name: "",
  kind: "worker",
  reportsTo: "",
  layer: "0",
  zones: "",
  tags: "",
  colour: "",
  contractFile: "",
}

export function RolesForm() {
  const queryClient = useQueryClient()
  const roles = useQuery({ queryKey: queryKeys.roles, queryFn: listRoles })
  const [draft, setDraft] = useState(empty)
  const save = useMutation({
    mutationFn: () =>
      createRole({
        name: draft.name.trim(),
        kind: draft.kind,
        reportsTo: draft.reportsTo.trim() || null,
        layer: Number(draft.layer),
        zones: splitList(draft.zones),
        tags: splitList(draft.tags),
        colour: draft.colour.trim() || null,
        contractFile: draft.contractFile.trim() || null,
      }),
    onSuccess: async () => {
      toast.success("Role saved")
      setDraft(empty)
      await queryClient.invalidateQueries({ queryKey: queryKeys.roles })
      await queryClient.invalidateQueries({ queryKey: queryKeys.roleTags })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not save the role"),
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Roles" description="Roles are data. Workers do the work. Supervisors review. Add a role here; no code change is required." />
      <QueryBody query={roles} emptyTitle="No roles" emptyDescription="Seed roles failed to load.">
        {(items) => (
          <>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left">
                <th className="py-2 pr-3">Name</th>
                <th className="py-2 pr-3">Kind</th>
                <th className="py-2 pr-3">Reports to</th>
                <th className="py-2 pr-3">Layer</th>
                <th className="py-2 pr-3">Zones</th>
                <th className="py-2 pr-3">Tags</th>
                <th className="py-2 pr-3">Colour</th>
                <th className="py-2 pr-3">Contract file</th>
                <th className="py-2"> </th>
              </tr>
            </thead>
            <tbody>
              {items.map((role) => (
                <RoleRow key={role.id} role={role} peers={items} />
              ))}
            </tbody>
          </table>
          <div className="mt-6 flex flex-col gap-4">
            {items.map((role) => (
              <Card key={`${role.id}-lessons`}>
                <CardHeader>
                  <CardTitle className="text-base">{role.name} lessons</CardTitle>
                  <CardDescription>Short, repeatable mistakes for this role. Not project facts.</CardDescription>
                </CardHeader>
                <CardContent>
                  <RoleLessons roleId={role.id} />
                </CardContent>
              </Card>
            ))}
          </div>
          </>
        )}
      </QueryBody>
      <Card>
        <CardHeader>
          <CardTitle>Add a role</CardTitle>
          <CardDescription>Kind, reports-to, layer, zones, tags, colour, and an optional contract file.</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-3 sm:grid-cols-2"
            onSubmit={(event) => {
              event.preventDefault()
              if (draft.name.trim()) save.mutate()
            }}
          >
            <Field>
              <FieldLabel htmlFor="role-name">Name</FieldLabel>
              <Input id="role-name" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
            </Field>
            <Field>
              <FieldLabel htmlFor="role-kind">Kind</FieldLabel>
              <select
                id="role-kind"
                className="h-9 rounded-md border bg-background px-2 text-sm"
                value={draft.kind}
                onChange={(event) => setDraft({ ...draft, kind: event.target.value as "worker" | "supervisor" })}
              >
                <option value="worker">worker</option>
                <option value="supervisor">supervisor</option>
              </select>
            </Field>
            <Field>
              <FieldLabel htmlFor="role-reports">Reports to</FieldLabel>
              <Input
                id="role-reports"
                value={draft.reportsTo}
                onChange={(event) => setDraft({ ...draft, reportsTo: event.target.value })}
                placeholder="role id"
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="role-layer">Layer</FieldLabel>
              <Input id="role-layer" type="number" value={draft.layer} onChange={(event) => setDraft({ ...draft, layer: event.target.value })} />
            </Field>
            <Field>
              <FieldLabel htmlFor="role-zones">Zones</FieldLabel>
              <Input id="role-zones" value={draft.zones} onChange={(event) => setDraft({ ...draft, zones: event.target.value })} placeholder="src/**, app/**" />
            </Field>
            <Field>
              <FieldLabel htmlFor="role-tags">Tags</FieldLabel>
              <Input id="role-tags" value={draft.tags} onChange={(event) => setDraft({ ...draft, tags: event.target.value })} placeholder="mobile, review" />
            </Field>
            <Field>
              <FieldLabel htmlFor="role-colour">Colour</FieldLabel>
              <Input id="role-colour" value={draft.colour} onChange={(event) => setDraft({ ...draft, colour: event.target.value })} placeholder="#2563eb" />
            </Field>
            <Field>
              <FieldLabel htmlFor="role-contract">Contract file</FieldLabel>
              <Input
                id="role-contract"
                value={draft.contractFile}
                onChange={(event) => setDraft({ ...draft, contractFile: event.target.value })}
                placeholder="optional path this role writes"
              />
            </Field>
            <div className="sm:col-span-2">
              <Button type="submit" disabled={!draft.name.trim() || save.isPending}>
                {save.isPending ? "Saving…" : "Add role"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

function RoleRow({ role, peers }: { role: Role; peers: Role[] }) {
  const queryClient = useQueryClient()
  const seed = SEED_ROLE_IDS.has(role.id)
  const [draft, setDraft] = useState({
    name: role.name,
    reportsTo: role.reportsTo ?? "",
    layer: String(role.layer),
    zones: (role.zones ?? []).join(", "),
    tags: (role.tags ?? []).join(", "),
    colour: role.colour ?? "",
    contractFile: role.contractFile ?? "",
  })
  const patch = useMutation({
    mutationFn: (body: components["schemas"]["RoleWrite"]) => updateRole(role.id, body),
    onSuccess: async () => {
      toast.success("Role saved")
      await queryClient.invalidateQueries({ queryKey: queryKeys.roles })
      await queryClient.invalidateQueries({ queryKey: queryKeys.roleTags })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not update the role"),
  })
  const reset = useMutation({
    mutationFn: () => resetRole(role.id),
    onSuccess: async (next) => {
      toast.success("Role reset to default")
      setDraft({
        name: next.name,
        reportsTo: next.reportsTo ?? "",
        layer: String(next.layer),
        zones: (next.zones ?? []).join(", "),
        tags: (next.tags ?? []).join(", "),
        colour: next.colour ?? "",
        contractFile: next.contractFile ?? "",
      })
      await queryClient.invalidateQueries({ queryKey: queryKeys.roles })
      await queryClient.invalidateQueries({ queryKey: queryKeys.roleTags })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not reset the role"),
  })
  return (
    <tr className="border-t align-top" data-role={role.id} data-seed={seed ? "true" : "false"}>
      <td className="py-2 pr-3">
        <Input
          aria-label={`${role.id} name`}
          value={draft.name}
          onChange={(event) => setDraft({ ...draft, name: event.target.value })}
        />
      </td>
      <td className="py-2 pr-3">
        <span aria-label={`${role.id} kind`}>{role.kind}</span>
      </td>
      <td className="py-2 pr-3">
        <select
          aria-label={`${role.name} reports to`}
          className="h-8 rounded border bg-background px-1 text-sm"
          value={draft.reportsTo}
          onChange={(event) => setDraft({ ...draft, reportsTo: event.target.value })}
        >
          <option value="">none</option>
          {peers
            .filter((item) => item.id !== role.id)
            .map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
        </select>
      </td>
      <td className="py-2 pr-3">
        <Input
          aria-label={`${role.id} layer`}
          type="number"
          value={draft.layer}
          onChange={(event) => setDraft({ ...draft, layer: event.target.value })}
        />
      </td>
      <td className="py-2 pr-3">
        <Input
          aria-label={`${role.id} zones`}
          value={draft.zones}
          onChange={(event) => setDraft({ ...draft, zones: event.target.value })}
        />
      </td>
      <td className="py-2 pr-3">
        <Input
          aria-label={`${role.id} tags`}
          value={draft.tags}
          onChange={(event) => setDraft({ ...draft, tags: event.target.value })}
        />
      </td>
      <td className="py-2 pr-3">
        <Input
          aria-label={`${role.id} colour`}
          value={draft.colour}
          onChange={(event) => setDraft({ ...draft, colour: event.target.value })}
        />
      </td>
      <td className="py-2 pr-3">
        <Input
          aria-label={`${role.id} contract file`}
          value={draft.contractFile}
          onChange={(event) => setDraft({ ...draft, contractFile: event.target.value })}
        />
      </td>
      <td className="py-2">
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            disabled={patch.isPending}
            onClick={() =>
              patch.mutate({
                name: draft.name.trim(),
                reportsTo: draft.reportsTo.trim() || null,
                layer: Number(draft.layer),
                zones: splitList(draft.zones),
                tags: splitList(draft.tags),
                colour: draft.colour.trim() || null,
                contractFile: draft.contractFile.trim() || null,
              })
            }
          >
            Save
          </Button>
          {seed ? (
            <Button type="button" size="sm" variant="outline" disabled={reset.isPending} onClick={() => reset.mutate()}>
              Reset to default
            </Button>
          ) : null}
        </div>
      </td>
    </tr>
  )
}

function RoleLessons({ roleId }: { roleId: string }) {
  const queryClient = useQueryClient()
  const lessons = useQuery({ queryKey: queryKeys.lessons(roleId), queryFn: () => listLessons(roleId) })
  const remove = useMutation({
    mutationFn: (lessonId: string) => deleteLesson(roleId, lessonId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.lessons(roleId) })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not delete the lesson"),
  })
  const rows = lessons.data ?? []
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">No lessons yet.</p>
  return (
    <ul className="flex flex-col gap-2">
      {rows.map((item) => (
        <li key={item.id} className="flex items-start justify-between gap-2 text-sm">
          <span>{item.text}</span>
          <Button type="button" variant="outline" onClick={() => remove.mutate(item.id)}>
            Delete
          </Button>
        </li>
      ))}
    </ul>
  )
}

function splitList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
}
