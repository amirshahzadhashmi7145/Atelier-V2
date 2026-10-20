"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { useMutation, useQuery } from "@tanstack/react-query"
import { toast } from "sonner"
import { PageHeader } from "@/components/shared/PageHeader"
import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { createRun, getSpendCap, listRunAgents, listRunProviders, listRunStacks, listRunVersions } from "@/features/runs/api"
import { queryKeys } from "@/lib/api/query-keys"

export function NewRun() {
  const router = useRouter()
  const params = useSearchParams()
  const agents = useQuery({ queryKey: queryKeys.agents, queryFn: listRunAgents })
  const stacks = useQuery({ queryKey: queryKeys.stacks, queryFn: listRunStacks })
  const cap = useQuery({ queryKey: queryKeys.runSettings, queryFn: getSpendCap })
  const providers = useQuery({ queryKey: queryKeys.providers, queryFn: listRunProviders })
  const [agentId, setAgentId] = useState(params.get("agentId") ?? "")
  const [kind, setKind] = useState<"repo" | "scaffold">("scaffold")
  const [url, setUrl] = useState("")
  const [template, setTemplate] = useState("")
  const [task, setTask] = useState(params.get("task") ?? "")
  const [criteria, setCriteria] = useState(() => {
    const raw = params.get("criteria") ?? ""
    return raw ? raw.split("\n") : [""]
  })
  const [link, setLink] = useState("")
  const [links, setLinks] = useState<string[]>([])
  const [files, setFiles] = useState<string[]>([])
  const versions = useQuery({
    queryKey: queryKeys.versions(agentId),
    queryFn: () => listRunVersions(agentId),
    enabled: Boolean(agentId),
  })
  const agent = agents.data?.find((item) => item.id === agentId)
  const active = versions.data?.find((item) => item.id === agent?.activePromptVersionId)
  const enabled = (stacks.data ?? []).filter((stack) => agent?.stackIds.includes(stack.id) && stack.scaffoldTemplate)
  const chosenTemplate = template || enabled[0]?.scaffoldTemplate || ""
  const missingKey = (() => {
    if (!agent) return ""
    const needed = [agent.model.provider, agent.backupModel?.provider].filter(Boolean) as string[]
    const missing = [...new Set(needed)].filter((pid) => {
      const provider = (providers.data ?? []).find((item) => item.id === pid)
      return !provider?.keyRef && !provider?.keyHint
    })
    if (missing.length === 0) return ""
    return `Add an API key for ${missing.join(" and ")} in Settings > Providers before running this agent.`
  })()
  const blocked = !agent
    ? "Choose an agent"
    : missingKey
      ? missingKey
      : !agent.activePromptVersionId
        ? "No active prompt version. Set one on the agent before starting a run."
        : kind === "repo" && !url.trim()
          ? "Add a GitHub repository URL"
          : kind === "scaffold" && !chosenTemplate
            ? "no stacks enabled"
            : !task.trim()
              ? "Write the task"
              : ""

  const create = useMutation({
    mutationFn: () =>
      createRun({
        agentId,
        promptVersionId: agent?.activePromptVersionId ?? undefined,
        workspace:
          kind === "repo"
            ? { kind: "repo", url: url.trim() }
            : { kind: "scaffold", template: chosenTemplate },
        task: task.trim(),
        criteria: criteria.map((item) => item.trim()).filter(Boolean),
        attachmentIds: [...links, ...files],
      }),
    onSuccess: (run) => router.push(`/runs/${run.id}`),
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not start the run"),
  })

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
      <PageHeader title="New run" description="One agent, one task, one workspace." />
      <Field>
        <FieldLabel htmlFor="run-agent">Agent</FieldLabel>
        <select
          id="run-agent"
          className="h-8 rounded-lg border border-input bg-background px-2 text-sm"
          value={agentId}
          onChange={(event) => {
            setAgentId(event.target.value)
            setTemplate("")
          }}
        >
          <option value="">Choose an agent</option>
          {(agents.data ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
              {item.activePromptVersionId ? " · active" : " · no active version"}
            </option>
          ))}
        </select>
        {active ? <p className="text-sm text-muted-foreground">Active prompt v{active.version}</p> : null}
        {agent && !agent.activePromptVersionId ? (
          <p className="text-sm text-destructive">No active prompt version. Set one on the agent before starting a run.</p>
        ) : null}
      </Field>
      <fieldset className="flex flex-col gap-3">
        <legend className="text-sm font-medium">Workspace</legend>
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" name="workspace" checked={kind === "repo"} onChange={() => setKind("repo")} />
          GitHub repository
        </label>
        {kind === "repo" ? (
          <Input aria-label="Repository URL" placeholder="https://github.com/org/repo" value={url} onChange={(event) => setUrl(event.target.value)} />
        ) : null}
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" name="workspace" checked={kind === "scaffold"} onChange={() => setKind("scaffold")} />
          Scaffold
        </label>
        {kind === "scaffold" ? (
          enabled.length === 0 ? (
            <p className="text-sm text-muted-foreground">no stacks enabled</p>
          ) : (
            <select
              aria-label="Scaffold"
              className="h-8 rounded-lg border border-input bg-background px-2 text-sm"
              value={chosenTemplate}
              onChange={(event) => setTemplate(event.target.value)}
            >
              {enabled.map((stack) => (
                <option key={stack.id} value={stack.scaffoldTemplate ?? ""}>
                  {stack.name} {stack.version}
                </option>
              ))}
            </select>
          )
        ) : null}
      </fieldset>
      <Field>
        <FieldLabel htmlFor="run-task">Task</FieldLabel>
        <textarea
          id="run-task"
          className="min-h-28 rounded-lg border border-input px-2.5 py-2 text-sm"
          value={task}
          onChange={(event) => setTask(event.target.value)}
        />
      </Field>
      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium">Acceptance criteria</legend>
        {criteria.map((item, index) => (
          <div key={index} className="flex gap-2">
            <Input
              aria-label={`Criterion ${index + 1}`}
              value={item}
              onChange={(event) => setCriteria(criteria.map((row, rowIndex) => (rowIndex === index ? event.target.value : row)))}
            />
            <Button
              type="button"
              variant="outline"
              onClick={() => setCriteria(criteria.filter((_, rowIndex) => rowIndex !== index))}
            >
              Remove
            </Button>
          </div>
        ))}
        <Button type="button" variant="outline" onClick={() => setCriteria([...criteria, ""])}>
          Add criterion
        </Button>
      </fieldset>
      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium">Attachments</legend>
        <input
          aria-label="Attachment files"
          type="file"
          multiple
          onChange={(event) => setFiles([...(event.target.files ?? [])].map((file) => file.name))}
        />
        {files.length > 0 ? <p className="text-sm text-muted-foreground">{files.join(", ")}</p> : null}
        <div className="flex gap-2">
          <Input aria-label="Attachment link" placeholder="https://…" value={link} onChange={(event) => setLink(event.target.value)} />
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              if (!link.trim()) return
              setLinks([...links, link.trim()])
              setLink("")
            }}
          >
            Add link
          </Button>
        </div>
        {links.map((item) => (
          <p key={item} className="text-sm">
            {item}
          </p>
        ))}
      </fieldset>
      <p className="text-sm">
        Spend cap ${Number(cap.data?.maxSpendPerRunUsd ?? 5).toFixed(2)}{" "}
        <Link href="/settings/runs" className="underline">
          Settings
        </Link>
      </p>
      {blocked && agentId ? <p className="text-sm text-muted-foreground">{blocked}</p> : null}
      <Button disabled={Boolean(blocked) || create.isPending} onClick={() => create.mutate()}>
        {create.isPending ? "Starting…" : "Start run"}
      </Button>
    </div>
  )
}
