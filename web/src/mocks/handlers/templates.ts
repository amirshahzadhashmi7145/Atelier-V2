import { http, HttpResponse } from "msw"
import type { components } from "@/lib/api/generated/types"

type Template = components["schemas"]["Template"]

const member = (roleKey: string, name: string, kind: "worker" | "supervisor", tags: string[]) => ({
  roleKey,
  name,
  kind,
  tags,
})

const TEMPLATES: Template[] = [
  {
    id: "fullstack-web",
    name: "Full-stack web app",
    description:
      "A Team Lead and QA reviewer supervising a Frontend and a Backend engineer. Best for web apps with a UI and an API.",
    members: [
      member("team-lead", "Team Lead", "supervisor", ["supervisor", "review", "planning"]),
      member("qa-engineer", "QA Engineer", "supervisor", ["supervisor", "review"]),
      member("frontend-engineer", "Frontend Engineer", "worker", ["frontend"]),
      member("backend-engineer", "Backend Engineer", "worker", ["backend"]),
    ],
  },
  {
    id: "frontend-only",
    name: "Frontend only",
    description: "A Team Lead reviewing a Frontend engineer. Best for static sites, SPAs, and UI-focused work.",
    members: [
      member("team-lead", "Team Lead", "supervisor", ["supervisor", "review", "planning"]),
      member("frontend-engineer", "Frontend Engineer", "worker", ["frontend"]),
    ],
  },
  {
    id: "backend-api",
    name: "Backend / API service",
    description: "A Team Lead reviewing a Backend engineer. Best for APIs, services, and server-side logic.",
    members: [
      member("team-lead", "Team Lead", "supervisor", ["supervisor", "review", "planning"]),
      member("backend-engineer", "Backend Engineer", "worker", ["backend"]),
    ],
  },
]

export const templateHandlers = [http.get("/templates", () => HttpResponse.json(TEMPLATES))]
