import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"
import { compilePrompt } from "@/features/agents/compile"

const fixture = JSON.parse(
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../../../fixtures/compile-preview.json"), "utf8"),
) as {
  input: Parameters<typeof compilePrompt>[0]
  expected: string
  tokenCount: number
}

describe("compilePrompt", () => {
  it("matches the shared fixture", () => {
    const result = compilePrompt(fixture.input)
    expect(result.compiled).toBe(fixture.expected)
    expect(result.tokenCount).toBe(fixture.tokenCount)
    expect(result.tokenCount).toBe(Math.ceil(result.compiled.length / 4))
  })
})
