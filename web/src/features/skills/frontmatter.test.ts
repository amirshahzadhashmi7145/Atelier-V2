import { describe, expect, it } from "vitest"
import { parseSkillMarkdown } from "@/features/skills/frontmatter"

describe("SKILL.md frontmatter", () => {
  it("reads name and description and leaves the body", () => {
    const parsed = parseSkillMarkdown("---\nname: react-best-practices\ndescription: Load when writing React UI.\n---\n# Body\n")
    expect(parsed).toEqual({
      name: "react-best-practices",
      description: "Load when writing React UI.",
      body: "# Body",
    })
  })

  it("rejects a file without frontmatter", () => {
    expect(() => parseSkillMarkdown("# Just a heading")).toThrow(/frontmatter/)
  })
})
