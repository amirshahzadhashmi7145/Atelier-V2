import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { parse } from "yaml"
import { describe, expect, it } from "vitest"

const spec = parse(
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../openapi/agent-studio.yaml"), "utf8"),
) as { paths: Record<string, Record<string, unknown>> }

const required: [string, string][] = [
  ["/agents", "get"],
  ["/agents", "post"],
  ["/agents/{id}", "patch"],
  ["/agents/{id}/versions", "post"],
  ["/agents/{id}/versions/{v}/activate", "post"],
  ["/agents/{id}/versions/{v}/diff", "get"],
  ["/agents/{id}/compile-preview", "post"],
  ["/tools", "get"],
  ["/tools/mcp/discover", "post"],
  ["/tools/api/import", "post"],
  ["/data-sources", "get"],
  ["/data-sources/{id}/refresh", "post"],
  ["/skills", "get"],
  ["/skills/import", "post"],
  ["/stacks", "get"],
  ["/stacks/{id}", "patch"],
  ["/models", "get"],
  ["/runs", "post"],
  ["/runs/{id}/events", "get"],
  ["/runs/{id}/stop", "post"],
  ["/runs/{id}/client-tool-result", "post"],
  ["/runs/{id}/answer", "post"],
  ["/runs/{id}/diff", "get"],
  ["/runs/{id}/artifacts", "get"],
]

describe("openapi contract", () => {
  it.each(required)("%s %s is declared", (path, method) => {
    expect(spec.paths[path]?.[method]).toBeTruthy()
  })
})
