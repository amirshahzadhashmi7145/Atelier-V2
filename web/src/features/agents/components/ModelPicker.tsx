"use client"

import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { modelId } from "@/lib/models/schema"
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
  label = "Model",
}: {
  models: Model[]
  value: string
  roleKey?: string
  tags?: Record<string, TagRecord>
  onChange: (name: string) => void
  allowEmpty?: boolean
  emptyLabel?: string
  label?: string
}) {
  const [query, setQuery] = useState("")
  const needle = query.trim().toLowerCase()
  const current = modelId(value)
  const shown = models.filter((model) => {
    const ident = modelId(model.name)
    return !needle || ident.toLowerCase().includes(needle) || ident === current
  })
  const groups = shown.reduce<Record<string, Model[]>>((acc, model) => {
    const key = model.provider || (/^gemini/i.test(modelId(model.name)) ? "gemini" : "openai")
    acc[key] = acc[key] ?? []
    acc[key].push(model)
    return acc
  }, {})
  const providerLabel: Record<string, string> = { openai: "OpenAI", gemini: "Google Gemini" }
  const selected = tagsFor(current, current ? tags[current] : undefined)
  const stat = models.find((model) => modelId(model.name) === current)?.ownStats?.find((item) => item.roleKey === roleKey)
  const pick = suggestedForRole(
    models.map((model) => ({ name: modelId(model.name), ownStats: model.ownStats ?? [] })),
    roleKey,
  )
  const suggested = Boolean(pick && pick.name === current)
  const reason = stat?.reason || (stat && stat.runs < 5 ? "not enough data yet" : pick?.reason)
  return (
    <div className="flex flex-col gap-2">
      <Input
        aria-label={label === "Model" ? "Search models" : `Search ${label.toLowerCase()}s`}
        value={query}
        placeholder="Search models"
        onChange={(event) => setQuery(event.target.value)}
      />
      <select
        aria-label={label}
        className="h-8 rounded-lg border border-input bg-background px-2.5 text-sm text-foreground"
        title={selected.note}
        value={current}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{emptyLabel}</option>
        {Object.entries(groups).map(([provider, items]) => (
          <optgroup key={provider} label={providerLabel[provider] ?? provider.replace(/\b\w/g, (char) => char.toUpperCase())}>
            {items.map((model) => {
              const ident = modelId(model.name)
              const record = tagsFor(ident, tags[ident])
              const mark = pick?.name === ident
              return (
                <option key={`${provider}-${ident}`} value={ident} title={record.note}>
                  {mark ? `${ident} (Suggested)` : ident}
                </option>
              )
            })}
          </optgroup>
        ))}
        {current && !shown.some((model) => modelId(model.name) === current) ? <option value={current}>{current}</option> : null}
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
