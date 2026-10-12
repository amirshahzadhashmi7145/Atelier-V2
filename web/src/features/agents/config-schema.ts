export type JsonSchema = {
  type?: string
  properties?: Record<string, JsonSchema>
  required?: string[]
  additionalProperties?: boolean
  enum?: unknown[]
  minimum?: number
  maximum?: number
  default?: unknown
  description?: string
}

export function asSchema(value: { [key: string]: unknown }): JsonSchema {
  return value as JsonSchema
}

export function labelFor(key: string) {
  const spaced = key.replace(/([A-Z])/g, " $1").replace(/[_-]/g, " ").trim().toLowerCase()
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function defaultsFromSchema(schema: JsonSchema): Record<string, unknown> {
  const config: Record<string, unknown> = {}
  for (const [key, property] of Object.entries(schema.properties ?? {})) {
    if (property.default !== undefined) config[key] = property.default
  }
  return config
}

export function validateConfig(schema: JsonSchema, config: Record<string, unknown>): string | null {
  const properties = schema.properties ?? {}
  if (schema.additionalProperties === false) {
    for (const key of Object.keys(config)) {
      if (!(key in properties)) return `${labelFor(key)} is not a setting for this model`
    }
  }
  for (const key of schema.required ?? []) {
    if (config[key] === undefined) return `${labelFor(key)} is required`
  }
  for (const [key, value] of Object.entries(config)) {
    const property = properties[key]
    if (!property) continue
    const message = checkValue(property, value, labelFor(key))
    if (message) return message
  }
  return null
}

function checkValue(property: JsonSchema, value: unknown, label: string): string | null {
  if (property.enum && !property.enum.includes(value)) {
    return `${label} must be one of ${property.enum.join(", ")}`
  }
  if (property.type === "boolean" && typeof value !== "boolean") return `${label} must be a boolean`
  if (property.type === "string" && typeof value !== "string") return `${label} must be text`
  if (property.type === "integer" && (typeof value !== "number" || !Number.isInteger(value))) {
    return `${label} must be an integer`
  }
  if ((property.type === "number" || property.type === "integer") && typeof value === "number") {
    if (property.minimum !== undefined && value < property.minimum) {
      return `${label} must be at least ${property.minimum}`
    }
    if (property.maximum !== undefined && value > property.maximum) {
      return `${label} must be at most ${property.maximum}`
    }
  }
  if (property.type === "number" && typeof value !== "number") return `${label} must be a number`
  return null
}
