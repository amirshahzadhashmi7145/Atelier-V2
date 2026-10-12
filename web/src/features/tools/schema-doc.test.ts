import { describe, expect, it } from "vitest"
import { validateSchemaText } from "@/features/tools/schema-doc"

describe("JSON schema document", () => {
  it("accepts an object schema and reports errors", () => {
    expect(validateSchemaText('{"type":"object","properties":{"q":{"type":"string"}}}')).toBeNull()
    expect(validateSchemaText("{")).toMatch(/JSON/)
    expect(validateSchemaText('{"type":"object","properties":{"q":"nope"}}')).toMatch(/must be an object/)
    expect(validateSchemaText('{"type":"widget"}')).toMatch(/not a JSON Schema type/)
  })
})
