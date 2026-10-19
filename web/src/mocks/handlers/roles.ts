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
    Object.assign(role, body)
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
