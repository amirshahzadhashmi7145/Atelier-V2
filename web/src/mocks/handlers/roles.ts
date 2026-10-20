import { http, HttpResponse } from "msw"
import { db, nid, remember } from "@/mocks/db"
import type { components } from "@/lib/api/generated/types"

function error(status: number, code: string, message: string) {
  return HttpResponse.json({ code, message }, { status })
}

export const roleHandlers = [
  http.get("/roles", () => HttpResponse.json(db.roles)),
  http.post("/roles", async ({ request }) => {
    const body = (await request.json()) as components["schemas"]["RoleWrite"]
    if (!body.name) return error(422, "invalid", "name is required")
    const id = body.id || nid("role")
    if (db.roles.some((item) => item.id === id)) return error(409, "exists", "A role with that id already exists")
    const role: components["schemas"]["Role"] = {
      id,
      name: body.name,
      kind: body.kind ?? "worker",
      reportsTo: body.reportsTo ?? null,
      layer: body.layer ?? 0,
      zones: body.zones ?? [],
      tags: body.tags ?? [],
      colour: body.colour ?? null,
      contractFile: body.contractFile ?? null,
    }
    db.roles.push(role)
    remember()
    return HttpResponse.json(role, { status: 201 })
  }),
  http.get("/roles/:id", ({ params }) => {
    const role = db.roles.find((item) => item.id === params.id)
    if (!role) return error(404, "not_found", "Not found")
    return HttpResponse.json(role)
  }),
  http.patch("/roles/:id", async ({ params, request }) => {
    const role = db.roles.find((item) => item.id === params.id)
    if (!role) return error(404, "not_found", "Not found")
    const body = (await request.json()) as components["schemas"]["RoleWrite"]
    const seed = ["frontend-engineer", "backend-engineer", "team-lead", "qa-engineer"].includes(role.id)
    const nextZones = body.zones ?? role.zones
    const nextContract = body.contractFile === undefined ? role.contractFile : body.contractFile
    if (nextContract) {
      const rel = nextContract.replaceAll("\\", "/").replace(/^\/+/, "")
      const inside = (nextZones ?? []).some((zone) => {
        const pattern = zone.replaceAll("\\", "/").replace(/^\/+/, "")
        return rel === pattern || (pattern.endsWith("/**") && rel.startsWith(pattern.slice(0, -3)))
      })
      if (!inside) return error(422, "invalid", "Contract file must be inside this role's zones")
    }
    Object.assign(role, body, seed ? { id: role.id, kind: role.kind } : {})
    remember()
    return HttpResponse.json(role)
  }),
  http.delete("/roles/:id", ({ params }) => {
    const index = db.roles.findIndex((item) => item.id === params.id)
    if (index < 0) return error(404, "not_found", "Not found")
    db.roles.splice(index, 1)
    remember()
    return new HttpResponse(null, { status: 204 })
  }),
  http.post("/roles/:id/reset", ({ params }) => {
    const role = db.roles.find((item) => item.id === params.id)
    if (!role) return error(404, "not_found", "Not found")
    const seed = db.roles.find((item) => item.id === params.id)
    if (!["frontend-engineer", "backend-engineer", "team-lead", "qa-engineer"].includes(String(params.id))) {
      return error(404, "not_found", "Not found")
    }
    const defaults: Record<string, components["schemas"]["Role"]> = {
      "frontend-engineer": {
        id: "frontend-engineer",
        name: "Frontend Engineer",
        kind: "worker",
        reportsTo: "team-lead",
        layer: 0,
        zones: ["src/**", "app/**", "public/**"],
        tags: ["frontend"],
        colour: "#2563eb",
        contractFile: null,
      },
      "backend-engineer": {
        id: "backend-engineer",
        name: "Backend Engineer",
        kind: "worker",
        reportsTo: "team-lead",
        layer: 0,
        zones: ["server/**"],
        tags: ["backend"],
        colour: "#d97706",
        contractFile: "server/CONTRACT.md",
      },
      "team-lead": {
        id: "team-lead",
        name: "Team Lead",
        kind: "supervisor",
        reportsTo: "qa-engineer",
        layer: 1,
        zones: [],
        tags: ["supervisor", "review", "planning"],
        colour: "#7c3aed",
        contractFile: null,
      },
      "qa-engineer": {
        id: "qa-engineer",
        name: "QA Engineer",
        kind: "supervisor",
        reportsTo: null,
        layer: 2,
        zones: [],
        tags: ["supervisor", "review"],
        colour: "#0f766e",
        contractFile: null,
      },
    }
    const next = defaults[String(params.id)]
    if (!seed || !next) return error(404, "not_found", "Not found")
    Object.assign(role, next)
    remember()
    return HttpResponse.json(role)
  }),
  http.get("/roles/:id/lessons", ({ params }) => {
    const role = db.roles.find((item) => item.id === params.id)
    if (!role) return error(404, "not_found", "Not found")
    return HttpResponse.json(db.lessons.filter((item) => item.roleKey === params.id))
  }),
  http.delete("/roles/:id/lessons/:lessonId", ({ params }) => {
    const index = db.lessons.findIndex((item) => item.id === params.lessonId && item.roleKey === params.id)
    if (index < 0) return error(404, "not_found", "Not found")
    db.lessons.splice(index, 1)
    remember()
    return new HttpResponse(null, { status: 204 })
  }),
  http.get("/roles/:id/suggestion", ({ params }) => {
    const role = db.roles.find((item) => item.id === params.id)
    if (!role) return error(404, "not_found", "Not found")
    return HttpResponse.json({ roleKey: params.id, name: null, provider: null, reason: "not enough data yet", tasks: 0 })
  }),
  http.get("/projects/:id/needs", () => HttpResponse.json(db.needs.filter((item) => !item.resolvedAt))),
  http.post("/needs/:id/answer", async ({ params, request }) => {
    const body = (await request.json()) as { text?: string }
    const row = db.needs.find((item) => item.id === params.id)
    if (!row) return error(404, "not_found", "Not found")
    row.resolvedAt = new Date().toISOString()
    row.answer = body.text || ""
    remember()
    return HttpResponse.json(row)
  }),
  http.get("/tags", () => {
    const tags: string[] = []
    for (const role of db.roles) {
      for (const tag of role.tags ?? []) {
        if (!tags.includes(tag)) tags.push(tag)
      }
    }
    for (const tag of ["review", "planning", "cheap", "fast"]) {
      if (!tags.includes(tag)) tags.push(tag)
    }
    return HttpResponse.json({ tags })
  }),
  http.get("/projects/:id/tasks/:taskId", ({ params }) => {
    const key = `${params.id}:${params.taskId}`
    const board = db.taskBoards[key]
    if (!board) return error(404, "not_found", "Not found")
    return HttpResponse.json(board)
  }),
]
