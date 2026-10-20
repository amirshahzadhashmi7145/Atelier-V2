// Documented reasoning.effort values:
// https://developers.openai.com/api/docs/guides/reasoning
const REASONING_EFFORT = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]

const BLOCKED =
  /embedding|tts|whisper|dall-e|moderation|realtime|image|imagen|audio|video|veo|sora|music|lyria|voice|chirp|live|transcribe|computer[-_ ]?use|robotic|deep[-_ ]?research|search/i
const RETIRED = /retired|deprecated/i

export function modelId(id: string) {
  let text = id.trim()
  if (text.toLowerCase().startsWith("models/")) text = text.slice(7)
  if (text.includes("/")) text = text.split("/").pop() ?? text
  return text
}

const temperature = {
  type: "number",
  minimum: 0,
  maximum: 2,
  default: 0.2,
  description: "Sampling temperature",
}
const maxOutputTokens = {
  type: "integer",
  minimum: 1,
  maximum: 128000,
  default: 4096,
  description: "Maximum tokens to generate",
}
const reasoningEffort = {
  type: "string",
  enum: REASONING_EFFORT,
  default: "medium",
  description: "How hard the model thinks",
}
const webSearch = { type: "boolean", default: false, description: "Allow the model to search the web" }
const structuredOutputs = { type: "boolean", default: false, description: "Require a JSON schema response" }

function objectSchema(properties: Record<string, unknown>) {
  return { type: "object", additionalProperties: false, properties }
}

export function isChatModel(id: string) {
  const ident = modelId(id)
  return Boolean(ident) && !BLOCKED.test(ident)
}

export function isRetiredModel(id: string) {
  return RETIRED.test(modelId(id))
}

function isReasoning(id: string) {
  if (/chat/i.test(id)) return false
  return /^(o\d|gpt-5)([-.]|$)/i.test(id)
}

export function configSchemaFor(id: string) {
  const common = { webSearch, structuredOutputs }
  if (isReasoning(id)) return objectSchema({ maxOutputTokens, reasoningEffort, ...common })
  if (/^(gpt-|chatgpt-)/i.test(id)) return objectSchema({ temperature, maxOutputTokens, ...common })
  return objectSchema(common)
}

function speedFor(id: string): "fast" | "balanced" | "slow" {
  if (/mini|nano/i.test(id)) return "fast"
  if (/^o\d/i.test(id)) return "slow"
  return "balanced"
}

export function modelInfoFromId(id: string) {
  const provider = /^gemini/i.test(id) ? ("gemini" as const) : ("openai" as const)
  return {
    provider,
    name: id,
    // ponytail: the models list has no context window or price
    contextWindow: 128000,
    priceInPerM: null,
    priceOutPerM: null,
    speedTier: speedFor(id),
    fitLine: null,
    configSchema: configSchemaFor(id),
    benchmarks: [] as [],
  }
}
