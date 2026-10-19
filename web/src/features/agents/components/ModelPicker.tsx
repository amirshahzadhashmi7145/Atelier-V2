"use client"

import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { bestForRole } from "@/lib/models/stats"
import { tagsFor, type TagRecord } from "@/lib/models/tags"

type Model = {
  name: string
  provider?: string
  ownStats?: { roleKey: string; runs: number; passed: number }[]
}

export function ModelPicker({
  models,
  value,
  roleKey = "",
  tags = {},
  onChange,
}: {
  models: Model[]
  value: string
  roleKey?: string
  tags?: Record<string, TagRecord>
  onChange: (name: string) => void
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
  const best = value && bestForRole(models.map((model) => ({ name: model.name, ownStats: model.ownStats ?? [] })), roleKey).includes(value)
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
        <option value="">Choose a model</option>
        {Object.entries(groups).map(([provider, items]) => (
          <optgroup key={provider} label={providerLabel[provider] ?? provider.replace(/\b\w/g, (char) => char.toUpperCase())}>
            {items.map((model) => {
              const record = tagsFor(model.name, tags[model.name])
              return (
                <option key={model.name} value={model.name} title={record.note}>
                  {model.name}
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
          {best ? <Badge>best in your runs for {roleKey}</Badge> : null}
        </div>
      ) : null}
      {stat && stat.runs >= 1 ? (
        <p className="text-sm text-muted-foreground">
          In your runs: {stat.passed} of {stat.runs} {roleKey} tasks passed
        </p>
      ) : null}
    </div>
  )
}
