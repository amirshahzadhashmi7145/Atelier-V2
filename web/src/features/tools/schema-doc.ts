const TYPES = new Set(["object", "string", "number", "integer", "boolean", "array", "null"])

export function validateSchemaText(text: string): string | null {
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch {
    return "Schema must be JSON"
  }
  return validateSchemaNode(value, "schema")
}

function validateSchemaNode(value: unknown, path: string): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return `${path} must be an object`
  const node = value as Record<string, unknown>
  if (node.type !== undefined && (typeof node.type !== "string" || !TYPES.has(node.type))) {
    return `${path}.type is not a JSON Schema type`
  }
  if (node.properties !== undefined) {
    if (!node.properties || typeof node.properties !== "object" || Array.isArray(node.properties)) {
      return `${path}.properties must be an object`
    }
    for (const [key, child] of Object.entries(node.properties)) {
      const message = validateSchemaNode(child, `${path}.properties.${key}`)
      if (message) return message
    }
  }
  if (node.required !== undefined && !Array.isArray(node.required)) return `${path}.required must be an array`
  return null
}
