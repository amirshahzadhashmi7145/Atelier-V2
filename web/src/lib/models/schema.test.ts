import { describe, expect, it } from "vitest"
import { configSchemaFor, isChatModel, isRetiredModel, modelId, modelInfoFromId } from "@/lib/models/schema"

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

  it("strips the Gemini models/ prefix and hides non-chat plus retired ids", () => {
    expect(modelId("models/gemini-3.1-pro-preview")).toBe("gemini-3.1-pro-preview")
    expect(modelInfoFromId("models/gemini-3.1-pro-preview").name).toBe("gemini-3.1-pro-preview")
    expect(modelInfoFromId("models/gemini-3.1-pro-preview").provider).toBe("gemini")
    expect(isChatModel("models/gemini-2.5-flash")).toBe(true)
    expect(isChatModel("models/gemini-2.0-flash-preview-image-generation")).toBe(false)
    expect(isChatModel("gemini-2.5-computer-use-preview-10-2025")).toBe(false)
    expect(isChatModel("sora-2")).toBe(false)
    expect(isRetiredModel("gpt-4o-retired")).toBe(true)
    expect(isRetiredModel("gpt-4.1")).toBe(false)
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
