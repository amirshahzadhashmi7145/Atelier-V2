import { http, HttpResponse } from "msw"
import { CANNED_SKILL_MD, parseSkillMarkdown } from "@/features/skills/frontmatter"
import { skillFromEntries, unzip } from "@/features/skills/zip"
import { db, nid, now } from "@/mocks/db"

function error(status: number, code: string, message: string) {
  return HttpResponse.json({ code, message }, { status })
}

function filesFrom(items: { name: string; size: number }[]) {
  return items.map((item) => ({ id: nid("file"), name: item.name, size: item.size }))
}

function makeSkill(input: {
  name: string
  description: string
  body: string
  origin: string
  files?: { name: string; size: number }[]
  id?: string
}) {
  const existing = db.skills.find((item) => item.origin === input.origin && input.origin !== "studio")
  const createdAt = existing?.createdAt ?? now()
  const version = (existing?.version ?? 0) + 1
  const skill = {
    id: input.id ?? existing?.id ?? nid("skill"),
    name: input.name,
    description: input.description,
    body: input.body,
    files: input.files ? filesFrom(input.files) : (existing?.files ?? []),
    version,
    versions: [...(existing?.versions ?? []), { version, createdAt: now() }],
    origin: input.origin,
    createdAt,
  }
  return { skill, existing }
}

export const skillHandlers = [
  http.get("/skills", () => HttpResponse.json(db.skills)),
  http.post("/skills/import", async ({ request }) => {
    const contentType = request.headers.get("content-type") ?? ""
    if (contentType.includes("multipart/form-data")) {
      const form = await request.formData()
      const file = form.get("file")
      if (!(file instanceof File)) return error(400, "invalid", "file is required")
      const preview = form.get("preview") !== "false"
      let parsed: ReturnType<typeof skillFromEntries>
      try {
        parsed = skillFromEntries(await unzip(await file.arrayBuffer()))
      } catch (cause) {
        return error(400, "invalid", cause instanceof Error ? cause.message : "Could not read the zip")
      }
      const { skill, existing } = makeSkill({ ...parsed, origin: `zip:${file.name}` })
      if (!preview) {
        if (existing) Object.assign(existing, skill)
        else db.skills.push(skill)
      }
      return HttpResponse.json(
        {
          skill,
          persisted: !preview,
          diff: existing ? [{ path: "SKILL.md", before: existing.body, after: skill.body }] : [],
        },
        { status: preview ? 200 : 201 },
      )
    }
    const body = (await request.json()) as { repoUrl?: string; path?: string; preview?: boolean }
    if (!body.repoUrl || !body.path) return error(400, "invalid", "repoUrl and path are required")
    const parsed = parseSkillMarkdown(CANNED_SKILL_MD)
    const origin = body.repoUrl
    const { skill, existing } = makeSkill({
      ...parsed,
      body: `${parsed.body}\n\nSource: ${body.repoUrl} ${body.path}`,
      origin,
    })
    if (!body.preview) {
      if (existing) Object.assign(existing, skill)
      else db.skills.push(skill)
    }
    return HttpResponse.json(
      {
        skill,
        persisted: !body.preview,
        diff: existing ? [{ path: "SKILL.md", before: existing.body, after: skill.body }] : [],
      },
      { status: body.preview ? 200 : 201 },
    )
  }),
  http.post("/skills", async ({ request }) => {
    const body = (await request.json()) as {
      name?: string
      description?: string
      body?: string
      origin?: string
      files?: { name: string; size: number }[]
    }
    if (!body.name || !body.description || body.body === undefined) {
      return error(422, "invalid", "name, description, and body are required")
    }
    const createdAt = now()
    const skill = {
      id: nid("skill"),
      name: body.name,
      description: body.description,
      body: body.body,
      files: filesFrom(body.files ?? []),
      version: 1,
      versions: [{ version: 1, createdAt }],
      origin: body.origin ?? "studio",
      createdAt,
    }
    db.skills.push(skill)
    return HttpResponse.json(skill, { status: 201 })
  }),
  http.get("/skills/:id", ({ params }) => {
    const skill = db.skills.find((item) => item.id === String(params.id))
    if (!skill) return error(404, "not_found", "Skill not found")
    return HttpResponse.json(skill)
  }),
  http.patch("/skills/:id", async ({ params, request }) => {
    const skill = db.skills.find((item) => item.id === String(params.id))
    if (!skill) return error(404, "not_found", "Skill not found")
    const body = (await request.json()) as {
      name?: string
      description?: string
      body?: string
      files?: { name: string; size: number }[]
    }
    if (body.name) skill.name = body.name
    if (body.description !== undefined) skill.description = body.description
    if (body.files) skill.files = filesFrom(body.files)
    if (body.body !== undefined && body.body !== skill.body) {
      skill.body = body.body
      skill.version += 1
      skill.versions.push({ version: skill.version, createdAt: now() })
    }
    return HttpResponse.json(skill)
  }),
]
