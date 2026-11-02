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

type ProjectTemplate = components["schemas"]["ProjectTemplate"]

const projectTemplate = (
  id: string,
  name: string,
  category: string,
  entity: string,
  teamTemplateId: string,
): ProjectTemplate => ({
  id,
  name,
  category,
  description: `A starter ${name} built with Agent Studio.`,
  teamTemplateId,
  entity,
  fields: [{ name: "name", label: "Name", kind: "text" }],
})

const PROJECT_TEMPLATES: ProjectTemplate[] = [
  projectTemplate("hr-system", "HR System", "Business", "Employee", "fullstack-web"),
  projectTemplate("crm", "CRM", "Business", "Contact", "fullstack-web"),
  projectTemplate("task-tracker", "Project / Task Tracker", "Productivity", "Task", "frontend-only"),
  projectTemplate("ecommerce-catalog", "E-commerce Catalog", "Commerce", "Product", "fullstack-web"),
  projectTemplate("inventory", "Inventory Management", "Commerce", "Item", "fullstack-web"),
  projectTemplate("booking", "Booking & Appointments", "Business", "Booking", "fullstack-web"),
  projectTemplate("helpdesk", "Help Desk / Ticketing", "Business", "Ticket", "fullstack-web"),
  projectTemplate("blog-cms", "Blog / CMS", "Content", "Post", "frontend-only"),
  projectTemplate("expense-tracker", "Expense Tracker", "Finance", "Expense", "fullstack-web"),
  projectTemplate("lms", "Learning Management (LMS)", "Education", "Course", "fullstack-web"),
]

export const templateHandlers = [
  http.get("/templates", () => HttpResponse.json(TEMPLATES)),
  http.get("/project-templates", () => HttpResponse.json(PROJECT_TEMPLATES)),
]
