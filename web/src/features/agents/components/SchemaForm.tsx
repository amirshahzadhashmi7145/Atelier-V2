"use client"

import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { labelFor, type JsonSchema } from "@/features/agents/config-schema"

export function SchemaForm({
  schema,
  value,
  onChange,
}: {
  schema: JsonSchema
  value: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
}) {
  const properties = schema.properties ?? {}
  return (
    <FieldGroup>
      {Object.entries(properties).map(([key, property]) => (
        <SchemaField
          key={key}
          name={key}
          property={property}
          value={value[key] ?? property.default}
          onChange={(next) => onChange({ ...value, [key]: next })}
        />
      ))}
    </FieldGroup>
  )
}

function SchemaField({
  name,
  property,
  value,
  onChange,
}: {
  name: string
  property: JsonSchema
  value: unknown
  onChange: (next: unknown) => void
}) {
  const label = labelFor(name)
  if (property.enum && property.enum.every((item) => typeof item === "string")) {
    const current = typeof value === "string" ? value : String(property.default ?? property.enum[0])
    return (
      <Field>
        <FieldLabel>{label}</FieldLabel>
        {property.description ? <FieldDescription>{property.description}</FieldDescription> : null}
        <ToggleGroup
          variant="outline"
          size="sm"
          spacing={0}
          value={[current]}
          onValueChange={(next: string[]) => {
            const picked = next.at(-1)
            if (picked) onChange(picked)
          }}
          aria-label={label}
        >
          {property.enum.map((option) => (
            <ToggleGroupItem key={String(option)} value={String(option)} aria-label={String(option)}>
              {String(option)}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Field>
    )
  }
  if (property.type === "boolean") {
    return (
      <Field orientation="horizontal">
        <Switch
          id={name}
          checked={value === true}
          onCheckedChange={(checked) => onChange(checked)}
          aria-label={label}
        />
        <FieldLabel htmlFor={name}>{label}</FieldLabel>
      </Field>
    )
  }
  if (property.type === "number" || property.type === "integer") {
    return (
      <Field>
        <FieldLabel htmlFor={name}>{label}</FieldLabel>
        {property.description ? <FieldDescription>{property.description}</FieldDescription> : null}
        <Input
          id={name}
          type="number"
          min={property.minimum}
          max={property.maximum}
          step={property.type === "integer" ? 1 : "any"}
          value={typeof value === "number" ? value : ""}
          onChange={(event) => {
            const next = event.target.value
            if (next === "") return
            onChange(property.type === "integer" ? Number.parseInt(next, 10) : Number(next))
          }}
        />
      </Field>
    )
  }
  return (
    <Field>
      <FieldLabel htmlFor={name}>{label}</FieldLabel>
      <Input id={name} value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)} />
    </Field>
  )
}
