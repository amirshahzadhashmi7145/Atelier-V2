"use client"

import Link from "next/link"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { z } from "zod"
import { ErrorState } from "@/components/shared/ErrorState"
import { PageHeader } from "@/components/shared/PageHeader"
import { PermissionBadge } from "@/components/shared/PermissionBadge"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Field, FieldGroup, FieldLabel, FieldSet, FieldLegend } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  activateVersion,
  activeBlockReason,
  compilePreview,
  createEval,
  createVersion,
  deleteEval,
  getAgent,
  listEditorModels,
  listEditorProviders,
  listEditorSkills,
  listEditorStacks,
  listEditorTools,
  latestVersion,
  listRoles,
  listVersions,
  runEvals,
  updateAgent,
} from "@/features/agents/api"
import { asSchema, defaultsFromSchema, retainConfig, validateConfig } from "@/features/agents/config-schema"
import { ModelPicker } from "@/features/agents/components/ModelPicker"
import { StackSheet } from "@/features/agents/components/StackSheet"
import { TeachSheet } from "@/features/agents/components/TeachSheet"
import { MarkdownField } from "@/components/shared/MarkdownField"
import { ModelCard } from "@/features/agents/components/ModelCard"
import { SchemaForm } from "@/features/agents/components/SchemaForm"
import { VersionsDrawer } from "@/features/agents/components/VersionsDrawer"
import type { components } from "@/lib/api/generated/types"
import { listModelTags } from "@/lib/api/model-tags"
import { queryKeys } from "@/lib/api/query-keys"
import { useUiStore } from "@/stores/ui-store"

type Agent = components["schemas"]["AgentDefinition"]
type Sections = components["schemas"]["PromptSections"]

type Draft = {
  name: string
  roleKey: string
  description: string
  model: Agent["model"]
  backupModel?: Agent["backupModel"]
  toolIds: string[]
  skillIds: string[]
  stackIds: string[]
  does: string[]
  neverDoes: string[]
  zones: string[]
  workerEngine: "loop" | "openhands"
  sections: Sections
}

const prompts = [
  ["role", "Role", "Who the agent is."],
  ["goal", "Goal", "What done means."],
  ["instructions", "Instructions", "How it should work."],
  ["constraints", "Constraints", "What it must not do."],
  ["output", "Output", "The shape of a finished task."],
] as const

const emptySections: Sections = { role: "", goal: "", instructions: "", constraints: "", output: "" }

function ChipList({ id, label, values, onChange }: { id: string; label: string; values: string[]; onChange: (next: string[]) => void }) {
  const [text, setText] = useState("")
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <div className="flex flex-wrap gap-1">
        {values.map((item) => (
          <button
            key={item}
            type="button"
            className="rounded-full border px-2 py-0.5 text-xs"
            onClick={() => onChange(values.filter((value) => value !== item))}
          >
            {item} ×
          </button>
        ))}
      </div>
      <Input
        id={id}
        value={text}
        placeholder="Add and press Enter"
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key !== "Enter") return
          event.preventDefault()
          const next = text.trim()
          if (!next || values.includes(next)) return
          onChange([...values, next])
          setText("")
        }}
      />
    </Field>
  )
}

const evalSchema = z.object({
  name: z.string().min(1, "Name the eval"),
  task: z.string().min(1, "Describe the task"),
  criteria: z.string().min(1, "Add a criterion"),
  passRule: z.string().min(1, "Say what passing means"),
})

function draftFrom(agent: Agent, sections: Sections | undefined): Draft {
  return {
    name: agent.name,
    roleKey: agent.roleKey,
    description: agent.description,
    model: agent.model,
    backupModel: agent.backupModel,
    toolIds: agent.toolIds,
    skillIds: agent.skillIds,
    stackIds: agent.stackIds,
    does: agent.scope?.does ?? [],
    neverDoes: agent.scope?.neverDoes ?? [],
    zones: agent.scope?.zones ?? agent.zones,
    workerEngine: agent.workerEngine === "openhands" ? "openhands" : "loop",
    sections: sections ?? emptySections,
  }
}

export function AgentEditor({ id }: { id: string }) {
  const queryClient = useQueryClient()
  const setSelectedAgentId = useUiStore((state) => state.setSelectedAgentId)
  const agentQuery = useQuery({ queryKey: queryKeys.agent(id), queryFn: () => getAgent(id) })
  const versionsQuery = useQuery({ queryKey: queryKeys.versions(id), queryFn: () => listVersions(id) })
  const toolsQuery = useQuery({ queryKey: queryKeys.tools, queryFn: listEditorTools })
  const skillsQuery = useQuery({ queryKey: queryKeys.skills, queryFn: listEditorSkills })
  const stacksQuery = useQuery({ queryKey: queryKeys.stacks, queryFn: listEditorStacks })
  const modelsQuery = useQuery({ queryKey: queryKeys.models, queryFn: listEditorModels })
  const tagsQuery = useQuery({ queryKey: queryKeys.modelTags, queryFn: listModelTags })
  const rolesQuery = useQuery({ queryKey: queryKeys.roles, queryFn: listRoles })
  const providersQuery = useQuery({ queryKey: queryKeys.providers, queryFn: listEditorProviders })
  const [draft, setDraft] = useState<Draft | null>(null)
  const [previewBody, setPreviewBody] = useState<components["schemas"]["CompilePreviewRequest"] | null>(null)
  const [evalForm, setEvalForm] = useState({ name: "", task: "", criteria: "", passRule: "" })
  const latest = versionsQuery.data ? latestVersion(versionsQuery.data) : undefined
  const loaded =
    agentQuery.data && versionsQuery.data
      ? draftFrom(agentQuery.data, latest?.sections)
      : null
  const current = draft ?? loaded

  useEffect(() => {
    setSelectedAgentId(id)
  }, [id, setSelectedAgentId])

  const previewKey = current
    ? JSON.stringify({
        sections: current.sections,
        toolIds: current.toolIds,
        skillIds: current.skillIds,
        stackIds: current.stackIds,
        scope: { does: current.does, neverDoes: current.neverDoes, zones: current.zones },
      })
    : ""

  useEffect(() => {
    if (!previewKey) return
    const handle = setTimeout(() => {
      setPreviewBody(JSON.parse(previewKey) as components["schemas"]["CompilePreviewRequest"])
    }, 400)
    return () => clearTimeout(handle)
  }, [previewKey])

  const preview = useQuery({
    queryKey: ["compile", id, previewBody],
    queryFn: () => compilePreview(id, previewBody!),
    enabled: previewBody !== null,
  })

  const selectedModel = modelsQuery.data?.find((model) => model.name === current?.model.name)
  const schema = selectedModel ? asSchema(selectedModel.configSchema) : null
  const configError = schema && current ? validateConfig(schema, { ...defaultsFromSchema(schema), ...current.model.config }) : null
  const blockReason = activeBlockReason(agentQuery.data?.evals ?? [], latest)
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.agent(id) })
    void queryClient.invalidateQueries({ queryKey: queryKeys.versions(id) })
    void queryClient.invalidateQueries({ queryKey: queryKeys.agents })
  }

  const save = useMutation({
    mutationFn: async () => {
      if (!current || !agentQuery.data) throw new Error("Agent is still loading")
      if (!schema) throw new Error("Choose a model from Settings after refreshing the provider")
      const config = { ...defaultsFromSchema(schema), ...current.model.config }
      const invalid = validateConfig(schema, config)
      if (invalid) throw new Error(invalid)
      await updateAgent(id, {
        name: current.name,
        roleKey: current.roleKey,
        description: current.description,
        model: { ...current.model, config },
        backupModel: current.backupModel,
        toolIds: current.toolIds,
        skillIds: current.skillIds,
        stackIds: current.stackIds,
        zones: current.zones,
        scope: { does: current.does, neverDoes: current.neverDoes, zones: current.zones },
        workerEngine: current.workerEngine,
      })
      return createVersion(id, current.sections)
    },
    onSuccess: async (version) => {
      setDraft(null)
      await queryClient.invalidateQueries({ queryKey: queryKeys.versions(id) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.agent(id) })
      toast.success(`Saved version ${version.version}`)
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Save failed"),
  })

  const activate = useMutation({
    mutationFn: () => activateVersion(id, latest!.version),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agent(id) })
      toast.success("Active version set")
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not set active"),
  })

  const evals = useMutation({
    mutationFn: () => runEvals(id, latest!.version),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.versions(id) })
      toast.success("Evals finished")
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Eval run failed"),
  })

  const addEval = useMutation({
    mutationFn: () => {
      const parsed = evalSchema.safeParse(evalForm)
      if (!parsed.success) throw new Error(parsed.error.issues[0]?.message ?? "Eval is incomplete")
      const criteria = parsed.data.criteria.split("\n").map((line) => line.trim()).filter(Boolean)
      if (criteria.length === 0) throw new Error("Add a criterion")
      return createEval(id, { ...parsed.data, criteria })
    },
    onSuccess: () => {
      toast.success("Eval added")
      setEvalForm({ name: "", task: "", criteria: "", passRule: "" })
      invalidate()
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not add the eval"),
  })

  const removeEval = useMutation({
    mutationFn: (evalId: string) => deleteEval(id, evalId),
    onSuccess: () => invalidate(),
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not remove the eval"),
  })

  const tools = useMemo(() => (toolsQuery.data ?? []).filter((tool) => tool.kind !== "control"), [toolsQuery.data])
  const allTools = toolsQuery.data ?? []
  const role = (rolesQuery.data ?? []).find((item) => item.id === current?.roleKey)
  const supervisor = role?.kind === "supervisor"
  const openhands = current?.workerEngine === "openhands"
  const missingKey = (() => {
    const providers = providersQuery.data ?? []
    const needed = [current?.model.provider, current?.backupModel?.provider].filter(Boolean) as string[]
    const missing = [...new Set(needed)].filter((pid) => {
      const provider = providers.find((item) => item.id === pid)
      return !provider?.keyRef && !provider?.keyHint
    })
    if (missing.length === 0) return null
    return `Add an API key for ${missing.join(" and ")} in Settings > Providers before running this agent.`
  })()

  if (agentQuery.isPending || versionsQuery.isPending) {
    return <Skeleton className="h-40 w-full" />
  }
  if (agentQuery.isError || versionsQuery.isError || !agentQuery.data || !current) {
    const message =
      (agentQuery.error instanceof Error && agentQuery.error.message) ||
      (versionsQuery.error instanceof Error && versionsQuery.error.message) ||
      "Agent not found"
    return (
      <ErrorState
        message={message}
        onRetry={() => {
          void agentQuery.refetch()
          void versionsQuery.refetch()
        }}
      />
    )
  }

  const agent = agentQuery.data
  const patch = (next: Partial<Draft>) => setDraft({ ...current, ...next })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-3">
        <PageHeader title={current.name || "Agent"} description="Identity, model, prompt, access, and evals for this agent." />
        <TeachSheet
          agentId={id}
          onSaved={() => {
            setDraft(null)
            void queryClient.invalidateQueries({ queryKey: queryKeys.agent(id) })
          }}
        />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Identity</CardTitle>
          <CardDescription>The name people see, and the slug other pages use.</CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="name">Name</FieldLabel>
              <Input id="name" value={current.name} onChange={(event) => patch({ name: event.target.value })} />
            </Field>
            <Field>
              <FieldLabel htmlFor="roleKey">Role key</FieldLabel>
              <Input id="roleKey" value={current.roleKey} onChange={(event) => patch({ roleKey: event.target.value })} />
            </Field>
            <Field>
              <p className="text-sm">Reports to</p>
              <p className="text-sm text-muted-foreground">{agent.reportsTo ?? "no one"}</p>
            </Field>
            <Field>
              <FieldLabel htmlFor="description">Description</FieldLabel>
              <Input id="description" value={current.description} onChange={(event) => patch({ description: event.target.value })} />
            </Field>
            {supervisor ? null : (
              <Field>
                <FieldLabel htmlFor="workerEngine">Worker engine</FieldLabel>
                <select
                  id="workerEngine"
                  className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm"
                  value={current.workerEngine}
                  onChange={(event) => patch({ workerEngine: event.target.value === "openhands" ? "openhands" : "loop" })}
                >
                  <option value="loop">Loop</option>
                  <option value="openhands">OpenHands</option>
                </select>
              </Field>
            )}
          </FieldGroup>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Model</CardTitle>
          <CardDescription>Settings come from the model schema, so a new option shows up without a code change.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <ModelPicker
            models={modelsQuery.data ?? []}
            value={current.model.name}
            roleKey={current.roleKey}
            tags={tagsQuery.data}
            onChange={(name) => {
              const model = modelsQuery.data?.find((item) => item.name === name)
              if (!model) return
              const schemaForModel = asSchema(model.configSchema)
              patch({
                model: {
                  provider: model.provider,
                  name: model.name,
                  config: retainConfig(schemaForModel, current.model.config),
                },
              })
            }}
          />
          {schema ? (
            <SchemaForm
              schema={schema}
              value={current.model.config}
              onChange={(config) => patch({ model: { ...current.model, config } })}
            />
          ) : (
            <p className="text-sm text-muted-foreground">Refresh models in Settings to edit this model&apos;s settings.</p>
          )}
          {configError ? <p className="text-sm text-destructive">{configError}</p> : null}
          {missingKey ? (
            <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950" role="alert">
              {missingKey}{" "}
              <Link className="underline" href="/settings/providers">
                Open Providers
              </Link>
            </p>
          ) : null}
          {selectedModel ? <ModelCard model={selectedModel} /> : null}
          <Field>
            <FieldLabel>Backup model</FieldLabel>
            <ModelPicker
              models={modelsQuery.data ?? []}
              value={current.backupModel?.name ?? ""}
              roleKey={current.roleKey}
              tags={tagsQuery.data}
              allowEmpty
              emptyLabel="No backup"
              label="Backup model"
              onChange={(name) => {
                if (!name) {
                  patch({ backupModel: undefined })
                  return
                }
                const model = modelsQuery.data?.find((item) => item.name === name)
                if (!model) return
                patch({
                  backupModel: {
                    provider: model.provider,
                    name: model.name,
                    config: {},
                  },
                })
              }}
            />
            <p className="text-sm text-muted-foreground">Used only if the main model&apos;s provider errors, times out, or rate-limits.</p>
          </Field>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Prompt</CardTitle>
          <CardDescription>The five sections you write. Stacks, tools, and skills are generated.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {prompts.map(([key, label, hint]) => (
            <MarkdownField
              key={`${id}-${key}`}
              id={`prompt-${key}`}
              label={label}
              hint={hint}
              value={current.sections[key]}
              onChange={(text) => patch({ sections: { ...current.sections, [key]: text } })}
            />
          ))}
          <div className="flex flex-col gap-2">
            <h2 className="text-sm font-medium">Compiled preview</h2>
            <p className="text-sm text-muted-foreground">
              {preview.data ? `${preview.data.tokenCount} tokens` : "Compiling…"}
            </p>
            <pre tabIndex={0} className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg border p-3 text-sm">
              {preview.data?.compiled ?? ""}
            </pre>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Access</CardTitle>
          <CardDescription>Control tools stay on and are hidden from the Tools page.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          {openhands ? (
            <div className="flex flex-col gap-2">
              <p className="text-sm text-muted-foreground">
                OpenHands provides a file editor, terminal, and task tracker. Safety comes from the zone, package, and
                build checks after each run.
              </p>
              <ul className="list-disc pl-5 text-sm" data-openhands-tools="true">
                <li>File editor</li>
                <li>Terminal</li>
                <li>Task tracker</li>
              </ul>
            </div>
          ) : !current.toolIds.includes("build_test") ||
            !current.toolIds.includes("shell") ||
            !current.toolIds.includes("preview_deploy") ? (
            <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950" role="alert">
              this agent cannot build or run anything
            </p>
          ) : null}
          {(
            [
              ...(openhands ? [] : ([["builtin", "Built-in"]] as const)),
              ["client", "Client-side"],
              ["mcp", "MCP"],
              ["api", "APIs"],
              ["data", "Data"],
            ] as const
          ).map(([kind, legend]) => {
            const items = tools
              .filter((tool) => tool.kind === kind)
              .map((tool) => ({
                id: tool.id,
                label: tool.kind === "data" ? `${tool.name} (${tool.description})` : tool.name,
                detail: tool.description,
                badge: <PermissionBadge permission={tool.permission} />,
              }))
            if (items.length === 0 && kind !== "builtin") return null
            return (
              <Checklist
                key={kind}
                legend={legend}
                empty="No tools yet."
                items={items}
                selected={current.toolIds}
                onToggle={(toolId, on) =>
                  patch({ toolIds: on ? [...current.toolIds, toolId] : current.toolIds.filter((item) => item !== toolId) })
                }
              />
            )
          })}
          {openhands ? (
            <Checklist
              legend="Studio"
              empty="No tools yet."
              items={[
                ...allTools
                  .filter((tool) => tool.id === "search_data")
                  .map((tool) => ({
                    id: tool.id,
                    label: tool.name,
                    detail: tool.description,
                    badge: <PermissionBadge permission={tool.permission} />,
                  })),
                {
                  id: "load_skill",
                  label: "load_skill",
                  detail: "Load a skill body into the context.",
                  badge: <PermissionBadge permission="read" />,
                },
              ]}
              selected={current.toolIds}
              onToggle={(toolId, on) =>
                patch({ toolIds: on ? [...current.toolIds, toolId] : current.toolIds.filter((item) => item !== toolId) })
              }
            />
          ) : null}
          <Checklist
            legend="Skills"
            empty="No skills yet. Import an agent to copy the skills it uses."
            items={(skillsQuery.data ?? []).map((skill) => ({ id: skill.id, label: skill.name, detail: skill.description }))}
            selected={current.skillIds}
            onToggle={(skillId, on) =>
              patch({ skillIds: on ? [...current.skillIds, skillId] : current.skillIds.filter((item) => item !== skillId) })
            }
          />
          <StackSheet
            onCreated={(stackId) =>
              patch({ stackIds: current.stackIds.includes(stackId) ? current.stackIds : [...current.stackIds, stackId] })
            }
          />
          <Checklist
            legend="Stacks"
            empty="No stacks yet. Create one, or import React or Next.js."
            items={(stacksQuery.data ?? []).map((stack) => ({
              id: stack.id,
              label: `${stack.name} ${stack.version}`,
              detail: stack.scaffoldTemplate ?? "",
            }))}
            selected={current.stackIds}
            onToggle={(stackId, on) =>
              patch({ stackIds: on ? [...current.stackIds, stackId] : current.stackIds.filter((item) => item !== stackId) })
            }
          />
          <ChipList id="does" label="Does" values={current.does} onChange={(does) => patch({ does })} />
          <ChipList id="never-does" label="Never does" values={current.neverDoes} onChange={(neverDoes) => patch({ neverDoes })} />
          <ChipList id="zones" label="Zones" values={current.zones} onChange={(zones) => patch({ zones })} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Evals</CardTitle>
          <CardDescription>Set active stays off until every eval has passed on the latest version.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <ul className="flex flex-col gap-2">
            {agent.evals.map((item) => {
              const result = latest?.evalResults.find((entry) => entry.evalId === item.id)
              return (
                <li key={item.id} className="flex items-center justify-between gap-2">
                  <span className="flex flex-wrap items-center gap-2" data-eval-status={result?.status ?? "not_run"}>
                    {item.name}
                    <Badge variant="secondary">{result?.status ?? "not_run"}</Badge>
                    {result?.costUsd != null ? <span className="text-xs text-muted-foreground">${result.costUsd.toFixed(4)}</span> : null}
                    {result?.durationMs != null ? <span className="text-xs text-muted-foreground">{(result.durationMs / 1000).toFixed(1)}s</span> : null}
                    {result?.runId ? (
                      <Link className="text-xs underline" href={`/runs/${result.runId}`}>
                        run
                      </Link>
                    ) : null}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={removeEval.isPending}
                    onClick={() => removeEval.mutate(item.id)}
                  >
                    Remove
                  </Button>
                </li>
              )
            })}
          </ul>
          <FieldGroup>
            {(
              [
                ["name", "Eval name"],
                ["task", "Task"],
                ["criteria", "Criteria"],
                ["passRule", "Pass rule"],
              ] as const
            ).map(([key, label]) => (
              <Field key={key}>
                <FieldLabel htmlFor={`eval-${key}`}>{label}</FieldLabel>
                {key === "criteria" ? (
                  <textarea
                    id={`eval-${key}`}
                    className="min-h-16 rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm"
                    value={evalForm[key]}
                    onChange={(event) => setEvalForm({ ...evalForm, [key]: event.target.value })}
                  />
                ) : (
                  <Input
                    id={`eval-${key}`}
                    value={evalForm[key]}
                    onChange={(event) => setEvalForm({ ...evalForm, [key]: event.target.value })}
                  />
                )}
              </Field>
            ))}
          </FieldGroup>
          <Button variant="outline" disabled={addEval.isPending} onClick={() => addEval.mutate()}>
            {addEval.isPending ? "Adding…" : "Add eval"}
          </Button>
        </CardContent>
      </Card>
      <div className="sticky bottom-0 flex flex-wrap items-center gap-2 border-t bg-background py-3">
        <Button disabled={save.isPending || Boolean(configError)} onClick={() => save.mutate()}>
          {save.isPending ? "Saving…" : "Save as new version"}
        </Button>
        <Button variant="outline" disabled={!latest || evals.isPending || agent.evals.length === 0} onClick={() => evals.mutate()}>
          {evals.isPending ? "Running…" : "Run evals"}
        </Button>
        <Button variant="outline" disabled={Boolean(blockReason) || activate.isPending} onClick={() => activate.mutate()}>
          {activate.isPending ? "Setting active…" : "Set active"}
        </Button>
        {latest ? (
          <Button
            variant="outline"
            nativeButton={false}
            render={
              <Link
                href={`/runs/new?agentId=${encodeURIComponent(id)}&task=${encodeURIComponent(agent.evals[agent.evals.length - 1]?.task ?? "")}&criteria=${encodeURIComponent((agent.evals[agent.evals.length - 1]?.criteria ?? []).join("\n"))}`}
              />
            }
          >
            Test run
          </Button>
        ) : (
          <Button variant="outline" disabled>
            Test run
          </Button>
        )}
        <VersionsDrawer id={id} versions={versionsQuery.data ?? []} />
        {blockReason ? <p className="text-sm text-muted-foreground">{blockReason}</p> : <p className="text-sm">Active version ready</p>}
        {agent.activePromptVersionId ? <Badge>Active</Badge> : null}
      </div>
    </div>
  )
}

function Checklist({
  legend,
  empty,
  items,
  selected,
  onToggle,
}: {
  legend: string
  empty: string
  items: { id: string; label: string; detail?: string; badge?: ReactNode }[]
  selected: string[]
  onToggle: (id: string, on: boolean) => void
}) {
  if (items.length === 0) {
    return (
      <FieldSet>
        <FieldLegend>{legend}</FieldLegend>
        <p className="text-sm text-muted-foreground">{empty}</p>
      </FieldSet>
    )
  }
  return (
    <FieldSet>
      <FieldLegend>{legend}</FieldLegend>
      <div className="flex flex-col gap-2">
        {items.map((item) => (
          <Field key={item.id} orientation="horizontal">
            <Checkbox
              id={`access-${item.id}`}
              checked={selected.includes(item.id)}
              onCheckedChange={(checked) => onToggle(item.id, checked === true)}
            />
            <FieldLabel htmlFor={`access-${item.id}`}>
              {item.label}
              {item.badge}
            </FieldLabel>
          </Field>
        ))}
      </div>
    </FieldSet>
  )
}
