import { describe, expect, it } from "vitest"
import { defaultsFromSchema, retainConfig, validateConfig, type JsonSchema } from "@/features/agents/config-schema"

const schema: JsonSchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    temperature: { type: "number", minimum: 0, maximum: 2, default: 0.2 },
    reasoningEffort: { type: "string", enum: ["low", "medium", "high"], default: "medium" },
    webSearch: { type: "boolean", default: false },
  },
}

describe("config schema", () => {
  it("fills defaults and accepts a config the schema describes", () => {
    expect(defaultsFromSchema(schema)).toEqual({
      temperature: 0.2,
      reasoningEffort: "medium",
      webSearch: false,
    })
    expect(validateConfig(schema, { temperature: 0.2, reasoningEffort: "low", webSearch: true })).toBeNull()
  })

  it("keeps values that still validate on the next schema", () => {
    const next: JsonSchema = {
      type: "object",
      additionalProperties: false,
      properties: {
        temperature: { type: "number", minimum: 0, maximum: 2, default: 0.4 },
        webSearch: { type: "boolean", default: false },
      },
    }
    expect(retainConfig(next, { reasoningEffort: "high", webSearch: true, temperature: 9 })).toEqual({
      temperature: 0.4,
      webSearch: true,
    })
  })

  it("rejects values and keys the schema does not allow", () => {
    expect(validateConfig(schema, { temperature: 3 })).toMatch(/at most 2/)
    expect(validateConfig(schema, { reasoningEffort: "max" })).toMatch(/one of/)
    expect(validateConfig(schema, { webSearch: "yes" })).toMatch(/boolean/)
    expect(validateConfig(schema, { topP: 1 })).toMatch(/not a setting/)
  })
})
