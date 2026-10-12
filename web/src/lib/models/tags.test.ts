import { describe, expect, it } from "vitest"
import { seedTags } from "@/lib/models/tags"

describe("seedTags", () => {
  it("tags reasoning families for planning and review", () => {
    expect(seedTags("o3").tags).toEqual(["planning", "review"])
    expect(seedTags("gpt-5").note).toBe("heuristic, edit me")
  })

  it("tags mini, nano, and fast families as cheap and fast", () => {
    expect(seedTags("gpt-5-mini").tags).toEqual(["cheap", "fast"])
    expect(seedTags("gpt-4.1-nano").tags).toEqual(["cheap", "fast"])
  })

  it("leaves other chat models untagged", () => {
    expect(seedTags("gpt-4.1")).toEqual({ tags: [], note: "", heuristic: false })
  })
})
