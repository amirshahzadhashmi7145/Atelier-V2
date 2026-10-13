"use client"

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { compareEvalModels, listAgentVersions, listModels, listSettingsAgents } from "@/features/settings/api"
import { listModelTags, saveModelTag } from "@/lib/api/model-tags"
import { queryKeys } from "@/lib/api/query-keys"
import { MODEL_TAGS, tagsFor, type ModelTag } from "@/lib/models/tags"

function TagRow({
  name,
  initial,
}: {
  name: string
  initial: { tags: ModelTag[]; note: string; heuristic: boolean }
}) {
  const queryClient = useQueryClient()
  const [tags, setTags] = useState(initial.tags)
  const [note, setNote] = useState(initial.note)
  const save = useMutation({
    mutationFn: () => saveModelTag(name, tags, note),
    onSuccess: async () => {
      toast.success(`Saved ${name}`)
      await queryClient.invalidateQueries({ queryKey: queryKeys.modelTags })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Save failed"),
  })
  return (
    <tr className="border-t">
      <td className="py-2 pr-3 align-top">{name}</td>
      <td className="py-2 pr-3">
        <div className="flex flex-wrap gap-2">
          {MODEL_TAGS.map((tag) => (
            <label key={tag} className="flex items-center gap-1 text-sm">
              <input
                type="checkbox"
                aria-label={`${name} ${tag}`}
                checked={tags.includes(tag)}
                onChange={(event) =>
                  setTags((current) => (event.target.checked ? [...current, tag] : current.filter((item) => item !== tag)))
                }
              />
              {tag}
            </label>
          ))}
        </div>
      </td>
      <td className="py-2 pr-3">
        <Input aria-label={`${name} note`} value={note} onChange={(event) => setNote(event.target.value)} />
        {initial.heuristic ? <Badge variant="outline">heuristic, edit me</Badge> : null}
      </td>
      <td className="py-2 align-top">
        <Button type="button" variant="outline" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      </td>
    </tr>
  )
}

export function ModelsTable() {
  const models = useQuery({ queryKey: queryKeys.models, queryFn: listModels })
  const tags = useQuery({ queryKey: queryKeys.modelTags, queryFn: listModelTags })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Models" description="Tags and a one-line note. Heuristic tags are a guess until you edit them." />
      <QueryBody query={models} emptyTitle="No models" emptyDescription="Refresh models on the Providers page.">
        {(items) => (
          <QueryBody query={tags} emptyTitle="No tags" emptyDescription="Tags could not be loaded.">
            {(saved) => (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th className="py-2 pr-3">Model</th>
                    <th className="py-2 pr-3">Tags</th>
                    <th className="py-2 pr-3">Note</th>
                    <th className="py-2" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((model) => (
                    <TagRow key={model.name} name={model.name} initial={tagsFor(model.name, saved[model.name])} />
                  ))}
                </tbody>
              </table>
            )}
          </QueryBody>
        )}
      </QueryBody>
      <EvalCompare modelNames={(models.data ?? []).map((model) => model.name)} />
    </div>
  )
}

function EvalCompare({ modelNames }: { modelNames: string[] }) {
  const agents = useQuery({ queryKey: ["settings-agents"], queryFn: listSettingsAgents })
  const [agentId, setAgentId] = useState("")
  const [picked, setPicked] = useState<string[]>([])
  const versions = useQuery({
    queryKey: ["settings-versions", agentId],
    queryFn: () => listAgentVersions(agentId),
    enabled: Boolean(agentId),
  })
  const latest = [...(versions.data ?? [])].sort((a, b) => b.version - a.version)[0]
  const compare = useMutation({
    mutationFn: () => {
      if (!latest) throw new Error("Save a version first")
      return compareEvalModels(agentId, latest.version, picked)
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Eval compare failed"),
  })
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault()
        if (latest && picked.length) compare.mutate()
      }}
    >
      <h2 className="text-lg font-semibold">Run evals</h2>
      <label className="text-sm" htmlFor="eval-agent">
        Agent
        <select id="eval-agent" className="mt-1 block rounded border px-2 py-1" value={agentId} onChange={(event) => setAgentId(event.target.value)}>
          <option value="">Choose</option>
          {(agents.data ?? []).map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name}
            </option>
          ))}
        </select>
      </label>
      <div className="flex flex-wrap gap-3">
        {modelNames.map((name) => (
          <label key={name} className="flex items-center gap-1 text-sm">
            <input
              type="checkbox"
              aria-label={`Compare ${name}`}
              checked={picked.includes(name)}
              onChange={(event) => setPicked((current) => (event.target.checked ? [...current, name] : current.filter((item) => item !== name)))}
            />
            {name}
          </label>
        ))}
      </div>
      <Button type="submit" variant="outline" disabled={!latest || picked.length === 0 || compare.isPending}>
        {compare.isPending ? "Running…" : "Run evals"}
      </Button>
      {compare.data ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left">
              <th>Model</th>
              <th>Pass rate</th>
              <th>Avg cost</th>
              <th>Avg duration</th>
            </tr>
          </thead>
          <tbody>
            {compare.data.rows.map((row) => (
              <tr key={row.model} className="border-t">
                <td>{row.model}</td>
                <td>{Math.round(row.passRate * 100)}%</td>
                <td>${row.avgCostUsd.toFixed(4)}</td>
                <td>{Math.round(row.avgDurationMs)} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </form>
  )
}
