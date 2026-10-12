"use client"

import { useState } from "react"
import { Input } from "@/components/ui/input"

export function ModelPicker({
  models,
  value,
  onChange,
}: {
  models: { name: string }[]
  value: string
  onChange: (name: string) => void
}) {
  const [query, setQuery] = useState("")
  const needle = query.trim().toLowerCase()
  const shown = models.filter((model) => !needle || model.name.toLowerCase().includes(needle) || model.name === value)
  return (
    <div className="flex flex-col gap-2">
      <Input aria-label="Search models" value={query} placeholder="Search models" onChange={(event) => setQuery(event.target.value)} />
      <select
        aria-label="Model"
        className="h-8 rounded-lg border border-input bg-background px-2.5 text-sm text-foreground"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Choose a model</option>
        {shown.map((model) => (
          <option key={model.name} value={model.name}>
            {model.name}
          </option>
        ))}
        {value && !shown.some((model) => model.name === value) ? <option value={value}>{value}</option> : null}
      </select>
    </div>
  )
}
