import { http, HttpResponse } from "msw"
import { db, nid, now } from "@/mocks/db"

function error(status: number, code: string, message: string) {
  return HttpResponse.json({ code, message }, { status })
}

function skillResult(skill: (typeof db.skills)[number], persisted: boolean) {
  const existing = db.skills.find((item) => item.name === skill.name && item.id !== skill.id)
  return {
    skill,
    persisted,
    diff: existing ? [{ path: "SKILL.md", before: existing.body, after: skill.body }] : [],
  }
}

export const skillHandlers = [
  http.get("/skills", () => HttpResponse.json(db.skills)),
  http.post("/skills/import", async ({ request }) => {
    const contentType = request.headers.get("content-type") ?? ""
    if (contentType.includes("multipart/form-data")) {
      const form = await request.formData()
      const file = form.get("file")
      if (!(file instanceof File)) return error(400, "invalid", "file is required")
      const preview = form.get("preview") === "true"
      const skill = {
        id: nid("skill"),
        name: file.name.replace(/\.zip$/i, ""),
        description: "Imported from a zip archive.",
        body: "Imported from zip.",
        files: [{ id: nid("file"), name: file.name, size: file.size }],
        version: 1,
        origin: "zip",
        createdAt: now(),
      }
      if (!preview) db.skills.push(skill)
      return HttpResponse.json(skillResult(skill, !preview), { status: preview ? 200 : 201 })
    }
    const body = (await request.json()) as { repoUrl?: string; path?: string; ref?: string; preview?: boolean }
    if (!body.repoUrl || !body.path) return error(400, "invalid", "repoUrl and path are required")
    const name = body.path.split("/").filter(Boolean).at(-1) ?? "imported-skill"
    const existing = db.skills.find((item) => item.id === name || item.name === name)
    const skill = {
      id: existing?.id ?? nid("skill"),
      name,
      description: `Imported from ${body.repoUrl}`,
      body: `# ${name}\n\nImported at ${body.ref ?? "HEAD"}.`,
      files: [],
      version: (existing?.version ?? 0) + 1,
      origin: body.repoUrl,
      createdAt: existing?.createdAt ?? now(),
    }
    const diff = existing ? [{ path: "SKILL.md", before: existing.body, after: skill.body }] : []
    if (!body.preview) {
      if (existing) Object.assign(existing, skill)
      else db.skills.push(skill)
    }
    return HttpResponse.json({ skill, persisted: !body.preview, diff }, { status: body.preview ? 200 : 201 })
  }),
  http.post("/skills", async ({ request }) => {
    const body = (await request.json()) as { name?: string; description?: string; body?: string }
    if (!body.name || !body.description || !body.body) {
      return error(422, "invalid", "name, description, and body are required")
    }
    const skill = {
      id: nid("skill"),
      name: body.name,
      description: body.description,
      body: body.body,
      files: [],
      version: 1,
      origin: "studio",
      createdAt: now(),
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
    const body = (await request.json()) as Partial<Pick<typeof skill, "name" | "description" | "body">>
    if (body.name) skill.name = body.name
    if (body.description) skill.description = body.description
    if (body.body) {
      skill.body = body.body
      skill.version += 1
    }
    return HttpResponse.json(skill)
  }),
]
