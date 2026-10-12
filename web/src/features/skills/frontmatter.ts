import { parse } from "yaml"

export const CANNED_SKILL_MD = `---
name: react-best-practices
description: Load when writing React UI.
---
# React best practices

Prefer server components.
`

export function parseSkillMarkdown(markdown: string) {
  const match = markdown.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/)
  if (!match) throw new Error("SKILL.md is missing frontmatter")
  const meta = parse(match[1]) as { name?: unknown; description?: unknown }
  if (typeof meta?.name !== "string" || typeof meta.description !== "string") {
    throw new Error("SKILL.md needs name and description")
  }
  return { name: meta.name, description: meta.description, body: match[2].trim() }
}
