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

  it("omits worker-only lines for supervisors", () => {
    const result = compilePrompt({
      ...fixture.input,
      tools: [{ name: "create_task", description: "Create a child task" }],
      worker: false,
    })
    expect(result.compiled).not.toContain("Prefer files.edit")
    expect(result.compiled).not.toContain("build_test before complete")
    expect(result.compiled).toContain("create_task: Create a child task")
    expect(result.compiled).not.toContain("files:")
  })
})
