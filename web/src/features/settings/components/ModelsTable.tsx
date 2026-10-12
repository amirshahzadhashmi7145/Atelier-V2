"use client"

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { listModels } from "@/features/settings/api"
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
    </div>
  )
}
