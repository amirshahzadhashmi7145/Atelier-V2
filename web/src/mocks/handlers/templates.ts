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

const ACCENTS: Record<string, string> = {
  Business: "indigo",
  Productivity: "emerald",
  Commerce: "amber",
  Content: "rose",
  Finance: "teal",
  Education: "violet",
}

const projectTemplate = (
  id: string,
  name: string,
  category: string,
  entity: string,
  teamTemplateId: string,
  icon: string,
): ProjectTemplate => ({
  id,
  name,
  category,
  description: `A starter ${name} built with Agent Studio.`,
  teamTemplateId,
  entity,
  icon,
  accent: ACCENTS[category] ?? "indigo",
  fields: [
    { name: "name", label: "Name", kind: "text" },
    { name: "status", label: "Status", kind: "text" },
    { name: "owner", label: "Owner", kind: "text" },
  ],
  sample: [
    { name: `${entity} Alpha`, status: "Active", owner: "Ava Chen" },
    { name: `${entity} Beta`, status: "Pending", owner: "Marcus Reed" },
  ],
})

const PROJECT_TEMPLATES: ProjectTemplate[] = [
  projectTemplate("hr-system", "HR System", "Business", "Employee", "fullstack-web", "users"),
  projectTemplate("crm", "CRM", "Business", "Contact", "fullstack-web", "contact"),
  projectTemplate("task-tracker", "Project / Task Tracker", "Productivity", "Task", "frontend-only", "square-check-big"),
  projectTemplate("ecommerce-catalog", "E-commerce Catalog", "Commerce", "Product", "fullstack-web", "shopping-bag"),
  projectTemplate("inventory", "Inventory Management", "Commerce", "Item", "fullstack-web", "package"),
  projectTemplate("booking", "Booking & Appointments", "Business", "Booking", "fullstack-web", "calendar-check"),
  projectTemplate("helpdesk", "Help Desk / Ticketing", "Business", "Ticket", "fullstack-web", "life-buoy"),
  projectTemplate("blog-cms", "Blog / CMS", "Content", "Post", "frontend-only", "file-text"),
  projectTemplate("expense-tracker", "Expense Tracker", "Finance", "Expense", "fullstack-web", "wallet"),
  projectTemplate("lms", "Learning Management (LMS)", "Education", "Course", "fullstack-web", "graduation-cap"),
]

export const templateHandlers = [
  http.get("/templates", () => HttpResponse.json(TEMPLATES)),
  http.get("/project-templates", () => HttpResponse.json(PROJECT_TEMPLATES)),
]
