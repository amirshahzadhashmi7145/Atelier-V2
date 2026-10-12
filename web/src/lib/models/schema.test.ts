import { describe, expect, it } from "vitest"
import { configSchemaFor, isChatModel } from "@/lib/models/schema"

describe("model id filter", () => {
  it("drops non-chat families and keeps chat ids", () => {
    const ids = [
      "text-embedding-3-small",
      "tts-1",
      "whisper-1",
      "dall-e-3",
      "omni-moderation-latest",
      "gpt-4o-realtime-preview",
      "gpt-image-1",
      "gpt-4o-audio-preview",
      "gpt-4.1",
      "o3",
    ]
    expect(ids.filter(isChatModel)).toEqual(["gpt-4.1", "o3"])
  })
})

describe("family schema", () => {
  it("gives reasoning models effort and no temperature", () => {
    for (const id of ["o3", "o4-mini", "gpt-5", "gpt-5.4"]) {
      const properties = configSchemaFor(id).properties as Record<string, { enum?: string[] }>
      expect(properties).toHaveProperty("reasoningEffort")
      expect(properties).not.toHaveProperty("temperature")
      expect(properties).toHaveProperty("webSearch")
      expect(properties).toHaveProperty("structuredOutputs")
      expect(properties.reasoningEffort.enum).toContain("high")
    }
  })

  it("gives other chat models temperature", () => {
    const properties = configSchemaFor("gpt-4.1-mini").properties as Record<string, unknown>
    expect(properties).toHaveProperty("temperature")
    expect(properties).toHaveProperty("maxOutputTokens")
    expect(properties).not.toHaveProperty("reasoningEffort")
    expect(properties).toHaveProperty("webSearch")
  })

  it("uses the base schema for an unknown pattern", () => {
    const properties = configSchemaFor("custom-chat").properties
    expect(Object.keys(properties)).toEqual(["webSearch", "structuredOutputs"])
  })
})
