"use client"

import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { suggestedForRole, type OwnStat } from "@/lib/models/stats"
import { tagsFor, type TagRecord } from "@/lib/models/tags"

type Model = {
  name: string
  provider?: string
  ownStats?: OwnStat[]
}

export function ModelPicker({
  models,
  value,
  roleKey = "",
  tags = {},
  onChange,
  allowEmpty = false,
  emptyLabel = "Choose a model",
}: {
  models: Model[]
  value: string
  roleKey?: string
  tags?: Record<string, TagRecord>
  onChange: (name: string) => void
  allowEmpty?: boolean
  emptyLabel?: string
}) {
  const [query, setQuery] = useState("")
  const needle = query.trim().toLowerCase()
  const shown = models.filter((model) => !needle || model.name.toLowerCase().includes(needle) || model.name === value)
  const groups = shown.reduce<Record<string, Model[]>>((acc, model) => {
    const key = model.provider || "openai"
    acc[key] = acc[key] ?? []
    acc[key].push(model)
    return acc
  }, {})
  const providerLabel: Record<string, string> = { openai: "OpenAI", gemini: "Google Gemini" }
  const selected = tagsFor(value, value ? tags[value] : undefined)
  const stat = models.find((model) => model.name === value)?.ownStats?.find((item) => item.roleKey === roleKey)
  const pick = suggestedForRole(
    models.map((model) => ({ name: model.name, ownStats: model.ownStats ?? [] })),
    roleKey,
  )
  const suggested = Boolean(pick && pick.name === value)
  const reason = stat?.reason || (stat && stat.runs < 5 ? "not enough data yet" : pick?.reason)
  return (
    <div className="flex flex-col gap-2">
      <Input aria-label="Search models" value={query} placeholder="Search models" onChange={(event) => setQuery(event.target.value)} />
      <select
        aria-label="Model"
        className="h-8 rounded-lg border border-input bg-background px-2.5 text-sm text-foreground"
        title={selected.note}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{emptyLabel}</option>
        {Object.entries(groups).map(([provider, items]) => (
          <optgroup key={provider} label={providerLabel[provider] ?? provider.replace(/\b\w/g, (char) => char.toUpperCase())}>
            {items.map((model) => {
              const record = tagsFor(model.name, tags[model.name])
              const mark = pick?.name === model.name
              return (
                <option key={model.name} value={model.name} title={record.note}>
                  {mark ? `${model.name} (Suggested)` : model.name}
                </option>
              )
            })}
          </optgroup>
        ))}
        {value && !shown.some((model) => model.name === value) ? <option value={value}>{value}</option> : null}
      </select>
      {value ? (
        <div className="flex flex-wrap gap-1" title={selected.note}>
          {selected.tags.map((tag) => (
            <Badge key={tag} variant="secondary">
              {tag}
            </Badge>
          ))}
          {suggested ? <Badge>Suggested</Badge> : null}
        </div>
      ) : allowEmpty ? null : null}
      {value && roleKey ? (
        <p className="text-sm text-muted-foreground">{reason || "not enough data yet"}</p>
      ) : null}
    </div>
  )
}
