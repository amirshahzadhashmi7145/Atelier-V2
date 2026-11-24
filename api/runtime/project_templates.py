"""Starter PROJECT templates: pre-built full-stack apps (HR system, CRM, …) a user
can start from. Picking one copies a fresh app into a brand-new project folder, so the
template itself is never touched — the new project owns its own git history (its
versions). Each template is a real Vite + React + Tailwind frontend plus an Express +
Prisma (SQLite) backend, generated from a compact per-domain config so all templates
stay consistent and maintainable.

The template "code" is this generator plus the DOMAINS config; `build(template_id,
folder)` writes a complete, runnable app into `folder`. Because it always writes from
the config, there is no mutable on-disk template to corrupt."""

from __future__ import annotations

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Field + domain model
# ---------------------------------------------------------------------------
# A field: {"name","label","kind"} where kind in {text, number, select, date}.
# `options` is required for select. The first text field is used as the row title.


def _field(name: str, label: str, kind: str = "text", options: list[str] | None = None) -> dict:
    field = {"name": name, "label": label, "kind": kind}
    if options:
        field["options"] = options
    return field


DOMAINS: list[dict] = [
    {
        "id": "hr-system",
        "name": "HR System",
        "category": "Business",
        "description": "Manage employees: roles, departments, status and salary. A starting point for an HR/people app.",
        "entity": "Employee",
        "plural": "employees",
        "teamTemplateId": "fullstack-web",
        "fields": [
            _field("name", "Name"),
            _field("email", "Email"),
            _field("department", "Department", "select", ["Engineering", "Sales", "Marketing", "People", "Finance"]),
            _field("role", "Role"),
            _field("status", "Status", "select", ["Active", "On leave", "Terminated"]),
            _field("salary", "Salary", "number"),
            _field("startedAt", "Start date", "date"),
        ],
        "seed": [
            {"name": "Ava Chen", "email": "ava@acme.co", "department": "Engineering", "role": "Staff Engineer", "status": "Active", "salary": 165000, "startedAt": "2022-03-14"},
            {"name": "Marcus Reed", "email": "marcus@acme.co", "department": "Sales", "role": "Account Executive", "status": "Active", "salary": 98000, "startedAt": "2023-07-01"},
            {"name": "Priya Nair", "email": "priya@acme.co", "department": "People", "role": "HR Manager", "status": "On leave", "salary": 112000, "startedAt": "2021-11-09"},
        ],
    },
    {
        "id": "crm",
        "name": "CRM",
        "category": "Business",
        "description": "Track contacts and their deal stage, owner and value. A starting point for a sales CRM.",
        "entity": "Contact",
        "plural": "contacts",
        "teamTemplateId": "fullstack-web",
        "fields": [
            _field("name", "Name"),
            _field("company", "Company"),
            _field("email", "Email"),
            _field("stage", "Stage", "select", ["Lead", "Qualified", "Proposal", "Won", "Lost"]),
            _field("owner", "Owner"),
            _field("value", "Deal value", "number"),
        ],
        "seed": [
            {"name": "Dana Ruiz", "company": "Northwind", "email": "dana@northwind.com", "stage": "Qualified", "owner": "Marcus", "value": 24000},
            {"name": "Tom Fischer", "company": "Globex", "email": "tom@globex.com", "stage": "Proposal", "owner": "Ava", "value": 56000},
            {"name": "Lena Park", "company": "Initech", "email": "lena@initech.com", "stage": "Won", "owner": "Marcus", "value": 18000},
        ],
    },
    {
        "id": "task-tracker",
        "name": "Project / Task Tracker",
        "category": "Productivity",
        "description": "Plan work as tasks with status, assignee and due date. A starting point for a project board.",
        "entity": "Task",
        "plural": "tasks",
        "teamTemplateId": "frontend-only",
        "fields": [
            _field("title", "Title"),
            _field("assignee", "Assignee"),
            _field("status", "Status", "select", ["Backlog", "In progress", "In review", "Done"]),
            _field("priority", "Priority", "select", ["Low", "Medium", "High", "Urgent"]),
            _field("dueAt", "Due date", "date"),
        ],
        "seed": [
            {"title": "Design onboarding flow", "assignee": "Priya", "status": "In progress", "priority": "High", "dueAt": "2026-11-20"},
            {"title": "Fix checkout bug", "assignee": "Ava", "status": "In review", "priority": "Urgent", "dueAt": "2026-11-12"},
            {"title": "Write launch post", "assignee": "Marcus", "status": "Backlog", "priority": "Medium", "dueAt": "2026-12-01"},
        ],
    },
    {
        "id": "ecommerce-catalog",
        "name": "E-commerce Catalog",
        "category": "Commerce",
        "description": "A product catalog with price, stock and category. A starting point for a store admin.",
        "entity": "Product",
        "plural": "products",
        "teamTemplateId": "fullstack-web",
        "fields": [
            _field("name", "Name"),
            _field("sku", "SKU"),
            _field("category", "Category", "select", ["Apparel", "Home", "Electronics", "Beauty"]),
            _field("price", "Price", "number"),
            _field("stock", "Stock", "number"),
            _field("status", "Status", "select", ["Draft", "Active", "Archived"]),
        ],
        "seed": [
            {"name": "Merino Beanie", "sku": "APP-001", "category": "Apparel", "price": 29.0, "stock": 120, "status": "Active"},
            {"name": "Ceramic Mug", "sku": "HOM-014", "category": "Home", "price": 14.5, "stock": 60, "status": "Active"},
            {"name": "USB-C Cable", "sku": "ELE-203", "category": "Electronics", "price": 9.99, "stock": 0, "status": "Draft"},
        ],
    },
    {
        "id": "inventory",
        "name": "Inventory Management",
        "category": "Commerce",
        "description": "Track stock items by SKU, quantity and location. A starting point for a warehouse app.",
        "entity": "Item",
        "plural": "items",
        "teamTemplateId": "fullstack-web",
        "fields": [
            _field("name", "Name"),
            _field("sku", "SKU"),
            _field("location", "Location", "select", ["A1", "A2", "B1", "B2", "Overflow"]),
            _field("quantity", "Quantity", "number"),
            _field("reorderAt", "Reorder at", "number"),
        ],
        "seed": [
            {"name": "Widget", "sku": "W-100", "location": "A1", "quantity": 340, "reorderAt": 100},
            {"name": "Gadget", "sku": "G-200", "location": "B2", "quantity": 45, "reorderAt": 50},
            {"name": "Sprocket", "sku": "S-300", "location": "Overflow", "quantity": 12, "reorderAt": 25},
        ],
    },
    {
        "id": "booking",
        "name": "Booking & Appointments",
        "category": "Business",
        "description": "Schedule appointments with a customer, service and status. A starting point for a booking app.",
        "entity": "Booking",
        "plural": "bookings",
        "teamTemplateId": "fullstack-web",
        "fields": [
            _field("customer", "Customer"),
            _field("service", "Service", "select", ["Consultation", "Haircut", "Checkup", "Repair"]),
            _field("when", "Date", "date"),
            _field("status", "Status", "select", ["Requested", "Confirmed", "Completed", "Cancelled"]),
            _field("notes", "Notes"),
        ],
        "seed": [
            {"customer": "Jo Blake", "service": "Consultation", "when": "2026-11-10", "status": "Confirmed", "notes": "First visit"},
            {"customer": "Sam Okoro", "service": "Repair", "when": "2026-11-11", "status": "Requested", "notes": ""},
            {"customer": "Mia Khan", "service": "Checkup", "when": "2026-11-09", "status": "Completed", "notes": "Follow-up in 6mo"},
        ],
    },
    {
        "id": "helpdesk",
        "name": "Help Desk / Ticketing",
        "category": "Business",
        "description": "Support tickets with priority, status and requester. A starting point for a help desk.",
        "entity": "Ticket",
        "plural": "tickets",
        "teamTemplateId": "fullstack-web",
        "fields": [
            _field("subject", "Subject"),
            _field("requester", "Requester"),
            _field("priority", "Priority", "select", ["Low", "Normal", "High", "Urgent"]),
            _field("status", "Status", "select", ["Open", "Pending", "Resolved", "Closed"]),
            _field("assignee", "Assignee"),
        ],
        "seed": [
            {"subject": "Cannot log in", "requester": "dana@northwind.com", "priority": "High", "status": "Open", "assignee": "Ava"},
            {"subject": "Billing question", "requester": "tom@globex.com", "priority": "Normal", "status": "Pending", "assignee": "Priya"},
            {"subject": "Feature request: dark mode", "requester": "lena@initech.com", "priority": "Low", "status": "Open", "assignee": ""},
        ],
    },
    {
        "id": "blog-cms",
        "name": "Blog / CMS",
        "category": "Content",
        "description": "Posts with author, status and publish date. A starting point for a content CMS.",
        "entity": "Post",
        "plural": "posts",
        "teamTemplateId": "frontend-only",
        "fields": [
            _field("title", "Title"),
            _field("author", "Author"),
            _field("status", "Status", "select", ["Draft", "Scheduled", "Published"]),
            _field("tag", "Tag", "select", ["Product", "Engineering", "Company", "Guide"]),
            _field("publishedAt", "Publish date", "date"),
        ],
        "seed": [
            {"title": "Introducing Agent Studio", "author": "Ava", "status": "Published", "tag": "Product", "publishedAt": "2026-10-01"},
            {"title": "How our sandbox works", "author": "Priya", "status": "Draft", "tag": "Engineering", "publishedAt": ""},
            {"title": "Roadmap for Q1", "author": "Marcus", "status": "Scheduled", "tag": "Company", "publishedAt": "2026-12-15"},
        ],
    },
    {
        "id": "expense-tracker",
        "name": "Expense Tracker",
        "category": "Finance",
        "description": "Log expenses by category, amount and date. A starting point for a finance tool.",
        "entity": "Expense",
        "plural": "expenses",
        "teamTemplateId": "fullstack-web",
        "fields": [
            _field("description", "Description"),
            _field("category", "Category", "select", ["Travel", "Meals", "Software", "Office", "Other"]),
            _field("amount", "Amount", "number"),
            _field("spentAt", "Date", "date"),
            _field("status", "Status", "select", ["Submitted", "Approved", "Reimbursed"]),
        ],
        "seed": [
            {"description": "Flight to NYC", "category": "Travel", "amount": 420.0, "spentAt": "2026-10-18", "status": "Approved"},
            {"description": "Team lunch", "category": "Meals", "amount": 86.4, "spentAt": "2026-10-22", "status": "Submitted"},
            {"description": "Figma seats", "category": "Software", "amount": 180.0, "spentAt": "2026-10-01", "status": "Reimbursed"},
        ],
    },
    {
        "id": "lms",
        "name": "Learning Management (LMS)",
        "category": "Education",
        "description": "Courses with instructor, enrolment and status. A starting point for a learning platform.",
        "entity": "Course",
        "plural": "courses",
        "teamTemplateId": "fullstack-web",
        "fields": [
            _field("title", "Title"),
            _field("instructor", "Instructor"),
            _field("level", "Level", "select", ["Beginner", "Intermediate", "Advanced"]),
            _field("students", "Students", "number"),
            _field("status", "Status", "select", ["Draft", "Open", "Full", "Archived"]),
        ],
        "seed": [
            {"title": "Intro to TypeScript", "instructor": "Ava", "level": "Beginner", "students": 128, "status": "Open"},
            {"title": "System Design", "instructor": "Marcus", "level": "Advanced", "students": 42, "status": "Full"},
            {"title": "Design Foundations", "instructor": "Priya", "level": "Intermediate", "students": 0, "status": "Draft"},
        ],
    },
]

_BY_ID = {domain["id"]: domain for domain in DOMAINS}


def public_list() -> list[dict]:
    return [_public(domain) for domain in DOMAINS]


def get(template_id: str) -> dict | None:
    domain = _BY_ID.get(template_id)
    return _public(domain) if domain else None


# A lucide icon name + a Tailwind color family per template, used for the thumbnail on
# the New Project cards and to theme the generated app itself.
_ICONS = {
    "hr-system": "users",
    "crm": "contact",
    "task-tracker": "square-check-big",
    "ecommerce-catalog": "shopping-bag",
    "inventory": "package",
    "booking": "calendar-check",
    "helpdesk": "life-buoy",
    "blog-cms": "file-text",
    "expense-tracker": "wallet",
    "lms": "graduation-cap",
}
_ACCENTS = {
    "Business": "indigo",
    "Productivity": "emerald",
    "Commerce": "amber",
    "Content": "rose",
    "Finance": "teal",
    "Education": "violet",
}


def _accent(domain: dict) -> str:
    return _ACCENTS.get(domain["category"], "indigo")


def _public(domain: dict) -> dict:
    return {
        "id": domain["id"],
        "name": domain["name"],
        "category": domain["category"],
        "description": domain["description"],
        "teamTemplateId": domain["teamTemplateId"],
        "entity": domain["entity"],
        "icon": _ICONS.get(domain["id"], "layout-grid"),
        "accent": _accent(domain),
        "fields": [{"name": f["name"], "label": f["label"], "kind": f["kind"]} for f in domain["fields"]],
        # A couple of real seed rows so the New Project card can show an actual preview
        # of the app's data, not an empty skeleton.
        "sample": [{k: v for k, v in row.items()} for row in (domain.get("seed") or [])[:3]],
    }


# ---------------------------------------------------------------------------
# Type mapping helpers
# ---------------------------------------------------------------------------


def _prisma_type(field: dict) -> str:
    return "Float" if field["kind"] == "number" else "String"


def _ts_type(field: dict) -> str:
    return "number" if field["kind"] == "number" else "string"


def _default_value(field: dict) -> str:
    return "0" if field["kind"] == "number" else '""'


# ---------------------------------------------------------------------------
# File generation
# ---------------------------------------------------------------------------


def build(template_id: str, folder: Path) -> dict:
    """Write a complete full-stack starter app for `template_id` into `folder`.
    Returns a small manifest. Raises KeyError for an unknown template."""
    domain = _BY_ID[template_id]
    folder.mkdir(parents=True, exist_ok=True)
    _write_frontend(folder, domain)
    _write_backend(folder / "server", domain)
    _write_root_readme(folder, domain)
    (folder / ".gitignore").write_text("node_modules\ndist\nbuild\n*.log\n.DS_Store\nserver/dev.db\nserver/.env\n", encoding="utf-8")
    return {"id": template_id, "name": domain["name"]}


def _write_root_readme(folder: Path, domain: dict) -> None:
    name = domain["name"]
    plural = domain["plural"]
    readme = (
        f"# {name}\n\n"
        f"A starter {name} built with Agent Studio: a Vite + React + Tailwind frontend and an "
        f"Express + Prisma (SQLite) backend. Change anything — this is your own project now.\n\n"
        "## Run the frontend\n\n"
        "```bash\nnpm install\nnpm run dev\n```\n\n"
        "The UI shows seeded data even if the API is not running, so you can preview it immediately.\n\n"
        "## Run the backend (for live data)\n\n"
        "```bash\ncd server\nnpm install\nnpm run dev   # http://localhost:3001\n```\n\n"
        f"The frontend proxies `/api` to the backend and reads/writes `/{plural}`.\n"
    )
    (folder / "README.md").write_text(readme, encoding="utf-8")


def _write_frontend(folder: Path, domain: dict) -> None:
    plural = domain["plural"]
    name = domain["name"]
    fields = domain["fields"]

    package = {
        "name": domain["id"],
        "private": True,
        "type": "module",
        "scripts": {"dev": "vite", "build": "vite build", "test": "node -e \"process.exit(0)\""},
        "dependencies": {"react": "^19.0.0", "react-dom": "^19.0.0"},
        "devDependencies": {
            "@types/react": "^19.0.0",
            "@types/react-dom": "^19.0.0",
            "@vitejs/plugin-react": "^4.3.0",
            "autoprefixer": "^10.4.0",
            "postcss": "^8.4.0",
            "tailwindcss": "^3.4.0",
            "typescript": "^5.7.0",
            "vite": "^6.0.0",
        },
    }
    (folder / "package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")

    (folder / "index.html").write_text(
        f'<!doctype html>\n<html lang="en">\n  <head>\n    <meta charset="UTF-8" />\n'
        f'    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        f"    <title>{name}</title>\n  </head>\n  <body>\n"
        '    <div id="root"></div>\n    <script type="module" src="/src/main.tsx"></script>\n'
        "  </body>\n</html>\n",
        encoding="utf-8",
    )
    (folder / "vite.config.ts").write_text(
        'import { defineConfig } from "vite"\nimport react from "@vitejs/plugin-react"\n\n'
        "export default defineConfig({\n  plugins: [react()],\n"
        '  server: { proxy: { "/api": "http://localhost:3001" } },\n})\n',
        encoding="utf-8",
    )
    (folder / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2022",
                    "lib": ["ES2022", "DOM", "DOM.Iterable"],
                    "module": "ESNext",
                    "moduleResolution": "Bundler",
                    "jsx": "react-jsx",
                    "strict": True,
                    "skipLibCheck": True,
                    "noEmit": True,
                },
                "include": ["src"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (folder / "tailwind.config.js").write_text(
        'export default {\n  content: ["./index.html", "./src/**/*.{ts,tsx}"],\n  theme: { extend: {} },\n  plugins: [],\n}\n',
        encoding="utf-8",
    )
    (folder / "postcss.config.js").write_text(
        "export default {\n  plugins: { tailwindcss: {}, autoprefixer: {} },\n}\n", encoding="utf-8"
    )

    src = folder / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "index.css").write_text("@tailwind base;\n@tailwind components;\n@tailwind utilities;\n", encoding="utf-8")
    (src / "main.tsx").write_text(
        'import React from "react"\nimport { createRoot } from "react-dom/client"\n'
        'import App from "./App"\nimport "./index.css"\n\n'
        'createRoot(document.getElementById("root")!).render(\n'
        "  <React.StrictMode>\n    <App />\n  </React.StrictMode>,\n)\n",
        encoding="utf-8",
    )

    # fields.ts: field defs + typed record + seed data (the preview/offline fallback).
    field_lines = ",\n".join(
        "  { name: " + json.dumps(f["name"]) + ", label: " + json.dumps(f["label"]) + ", kind: " + json.dumps(f["kind"]) + (", options: " + json.dumps(f.get("options")) if f.get("options") else "") + " }"
        for f in fields
    )
    record_fields = "\n".join(f"  {f['name']}: {_ts_type(f)}" for f in fields)
    seed_rows = ",\n".join(
        "  { id: " + json.dumps(f"seed-{i+1}") + ", " + ", ".join(f"{k}: {json.dumps(v)}" for k, v in row.items()) + " }"
        for i, row in enumerate(domain["seed"])
    )
    (src / "fields.ts").write_text(
        "export type Field = { name: string; label: string; kind: string; options?: string[] }\n\n"
        f"export type {domain['entity']} = {{\n  id: string\n{record_fields}\n}}\n\n"
        f"export const FIELDS: Field[] = [\n{field_lines},\n]\n\n"
        f"export const SEED: {domain['entity']}[] = [\n{seed_rows},\n]\n",
        encoding="utf-8",
    )

    (src / "api.ts").write_text(_frontend_api_ts(domain), encoding="utf-8")
    (src / "App.tsx").write_text(_frontend_app_tsx(domain), encoding="utf-8")


def _frontend_api_ts(domain: dict) -> str:
    entity = domain["entity"]
    plural = domain["plural"]
    return (
        f'import type {{ {entity} }} from "./fields"\nimport {{ SEED }} from "./fields"\n\n'
        f'const BASE = "/api/{plural}"\n\n'
        "// Each call tries the backend and falls back to local seed data, so the app renders\n"
        "// in preview even before the Express server is running.\n"
        f"export async function list(): Promise<{entity}[]> {{\n"
        "  try {\n    const res = await fetch(BASE)\n    if (!res.ok) throw new Error(String(res.status))\n"
        "    return (await res.json()) as " + entity + "[]\n"
        "  } catch {\n    return SEED\n  }\n}\n\n"
        f"export async function create(input: Omit<{entity}, \"id\">): Promise<{entity} | null> {{\n"
        "  try {\n    const res = await fetch(BASE, {\n      method: \"POST\",\n"
        '      headers: { "Content-Type": "application/json" },\n      body: JSON.stringify(input),\n    })\n'
        "    if (!res.ok) throw new Error(String(res.status))\n    return (await res.json()) as " + entity + "\n"
        "  } catch {\n    return null\n  }\n}\n\n"
        "export async function remove(id: string): Promise<boolean> {\n"
        "  try {\n    const res = await fetch(`${BASE}/${id}`, { method: \"DELETE\" })\n    return res.ok\n"
        "  } catch {\n    return false\n  }\n}\n"
    )


_APP_TSX_TEMPLATE = r'''import { useEffect, useMemo, useState } from "react"
import type { __ENTITY__ } from "./fields"
import { FIELDS, SEED } from "./fields"
import { list, create, remove } from "./api"

type Draft = Omit<__ENTITY__, "id">
const EMPTY: Draft = __BLANK__

const TITLE = FIELDS[0]?.name
const SUBTITLE = FIELDS[1]?.name

function badgeClass(value: string) {
  const v = (value || "").toLowerCase()
  if (/(active|open|done|paid|in stock|published|completed|confirmed|approved|won)/.test(v)) return "bg-emerald-100 text-emerald-700"
  if (/(pending|on leave|processing|draft|low|waiting|review|new)/.test(v)) return "bg-amber-100 text-amber-700"
  if (/(closed|terminated|cancel|out of stock|overdue|rejected|lost|blocked)/.test(v)) return "bg-rose-100 text-rose-700"
  return "bg-__ACCENT__-100 text-__ACCENT__-700"
}

export default function App() {
  const [rows, setRows] = useState<__ENTITY__[]>(SEED)
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState("")
  const [open, setOpen] = useState(false)

  useEffect(() => {
    list().then((data) => { setRows(data); setLoading(false) })
  }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((r) => FIELDS.some((f) => String((r as any)[f.name] ?? "").toLowerCase().includes(q)))
  }, [rows, query])

  async function add(e: React.FormEvent) {
    e.preventDefault()
    const created = await create(draft)
    setRows((r) => [created ?? { ...draft, id: `local-${Date.now()}` }, ...r])
    setDraft(EMPTY)
    setOpen(false)
  }

  async function del(id: string) {
    await remove(id)
    setRows((r) => r.filter((x) => x.id !== id))
  }

  const inputClass =
    "h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-__ACCENT__-400 focus:ring-2 focus:ring-__ACCENT__-100"

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="bg-gradient-to-r from-__ACCENT__-600 to-__ACCENT__-500 text-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-end justify-between gap-4 px-6 py-10">
          <div>
            <p className="text-sm font-medium uppercase tracking-wide text-white/70">__NAME__</p>
            <h1 className="mt-1 text-3xl font-bold tracking-tight">__PLURAL_TITLE__</h1>
            <p className="mt-1 text-white/80">
              {loading ? "Loading…" : `${rows.length} ${rows.length === 1 ? "record" : "records"}`}
            </p>
          </div>
          <button
            onClick={() => setOpen((v) => !v)}
            className="h-11 rounded-xl bg-white/15 px-5 text-sm font-semibold text-white shadow-sm ring-1 ring-white/30 backdrop-blur transition hover:bg-white/25"
          >
            {open ? "Close" : "+ New __ENTITY__"}
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-6">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search __PLURAL__…"
            className="h-11 w-full rounded-2xl border border-slate-200 bg-white px-4 text-sm shadow-sm outline-none transition focus:border-__ACCENT__-400 focus:ring-2 focus:ring-__ACCENT__-100"
          />
        </div>

        {open && (
          <form
            onSubmit={add}
            className="mb-8 grid gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:grid-cols-2 lg:grid-cols-3"
          >
            {FIELDS.map((f) => (
              <label key={f.name} className="text-sm">
                <span className="mb-1.5 block font-medium text-slate-700">{f.label}</span>
                {f.options ? (
                  <select
                    className={inputClass}
                    value={String((draft as any)[f.name] ?? "")}
                    onChange={(e) => setDraft((d) => ({ ...d, [f.name]: e.target.value }))}
                  >
                    <option value="">—</option>
                    {f.options.map((o) => (
                      <option key={o} value={o}>{o}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    className={inputClass}
                    type={f.kind === "number" ? "number" : f.kind === "date" ? "date" : "text"}
                    value={String((draft as any)[f.name] ?? "")}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, [f.name]: f.kind === "number" ? Number(e.target.value) : e.target.value }))
                    }
                  />
                )}
              </label>
            ))}
            <div className="flex items-end sm:col-span-2 lg:col-span-3">
              <button
                type="submit"
                className="h-11 rounded-xl bg-__ACCENT__-600 px-6 text-sm font-semibold text-white shadow-sm transition hover:bg-__ACCENT__-700"
              >
                Save __ENTITY__
              </button>
            </div>
          </form>
        )}

        {filtered.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-16 text-center">
            <p className="text-slate-500">No __PLURAL__ yet. Click “+ New __ENTITY__” to add one.</p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((row) => (
              <div
                key={row.id}
                className="group relative rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
              >
                <button
                  onClick={() => del(row.id)}
                  aria-label="Delete"
                  className="absolute right-3 top-3 grid h-7 w-7 place-items-center rounded-full text-slate-300 opacity-0 transition hover:bg-rose-50 hover:text-rose-600 group-hover:opacity-100"
                >
                  ✕
                </button>
                {TITLE && (
                  <h3 className="pr-7 text-base font-semibold text-slate-900">
                    {String((row as any)[TITLE] ?? "Untitled")}
                  </h3>
                )}
                {SUBTITLE && <p className="truncate text-sm text-slate-500">{String((row as any)[SUBTITLE] ?? "")}</p>}
                <dl className="mt-4 space-y-2 border-t border-slate-100 pt-4">
                  {FIELDS.slice(2).map((f) => (
                    <div key={f.name} className="flex items-center justify-between gap-3 text-sm">
                      <dt className="text-slate-400">{f.label}</dt>
                      <dd className="font-medium text-slate-700">
                        {f.options ? (
                          <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${badgeClass(String((row as any)[f.name] ?? ""))}`}>
                            {String((row as any)[f.name] ?? "—")}
                          </span>
                        ) : (
                          String((row as any)[f.name] ?? "—")
                        )}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
'''


def _frontend_app_tsx(domain: dict) -> str:
    entity = domain["entity"]
    name = domain["name"]
    plural = domain["plural"]
    accent = _accent(domain)
    fields = domain["fields"]
    blank = "{ " + ", ".join(f"{f['name']}: {_default_value(f)}" for f in fields) + " }"
    template = _APP_TSX_TEMPLATE
    return (
        template.replace("__ENTITY__", entity)
        .replace("__NAME__", name)
        .replace("__PLURAL_TITLE__", plural[:1].upper() + plural[1:])
        .replace("__PLURAL__", plural)
        .replace("__BLANK__", blank)
        .replace("__ACCENT__", accent)
    )


def _write_backend(folder: Path, domain: dict) -> None:
    entity = domain["entity"]
    plural = domain["plural"]
    fields = domain["fields"]
    folder.mkdir(parents=True, exist_ok=True)

    package = {
        "name": f"{domain['id']}-server",
        "private": True,
        "type": "module",
        "scripts": {
            "dev": "prisma db push --skip-generate --accept-data-loss && tsx watch src/index.ts",
            "build": "prisma generate && tsc -p tsconfig.json",
            "test": "node -e \"process.exit(0)\"",
            "seed": "tsx prisma/seed.ts",
            "postinstall": "prisma generate",
        },
        "dependencies": {"@prisma/client": "^6.0.0", "cors": "^2.8.5", "express": "^4.21.0"},
        "devDependencies": {
            "@types/cors": "^2.8.0",
            "@types/express": "^4.17.0",
            "@types/node": "^20.0.0",
            "prisma": "^6.0.0",
            "tsx": "^4.19.0",
            "typescript": "^5.7.0",
        },
    }
    (folder / "package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    (folder / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2022",
                    "module": "ESNext",
                    "moduleResolution": "Bundler",
                    "strict": True,
                    "skipLibCheck": True,
                    "esModuleInterop": True,
                    "outDir": "dist",
                },
                "include": ["src"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (folder / ".env.example").write_text('DATABASE_URL="file:./dev.db"\n', encoding="utf-8")
    (folder / ".env").write_text('DATABASE_URL="file:./dev.db"\n', encoding="utf-8")

    prisma_dir = folder / "prisma"
    prisma_dir.mkdir(parents=True, exist_ok=True)
    model_fields = "\n".join(f"  {f['name']} {_prisma_type(f)}" for f in fields)
    (prisma_dir / "schema.prisma").write_text(
        'generator client {\n  provider = "prisma-client-js"\n}\n\n'
        'datasource db {\n  provider = "sqlite"\n  url      = env("DATABASE_URL")\n}\n\n'
        f"model {entity} {{\n  id String @id @default(cuid())\n{model_fields}\n  createdAt DateTime @default(now())\n}}\n",
        encoding="utf-8",
    )

    seed_objects = ",\n".join(
        "    { " + ", ".join(f"{k}: {json.dumps(v)}" for k, v in row.items()) + " }"
        for row in domain["seed"]
    )
    lower_entity = entity[0].lower() + entity[1:]
    (prisma_dir / "seed.ts").write_text(
        'import { PrismaClient } from "@prisma/client"\n\nconst prisma = new PrismaClient()\n\n'
        "async function main() {\n"
        f"  const count = await prisma.{lower_entity}.count()\n"
        "  if (count > 0) return\n"
        f"  await prisma.{lower_entity}.createMany({{ data: [\n{seed_objects},\n  ] }})\n"
        "}\n\nmain().finally(() => prisma.$disconnect())\n",
        encoding="utf-8",
    )

    allowed = json.dumps([f["name"] for f in fields])
    (folder / "src").mkdir(parents=True, exist_ok=True)
    (folder / "src" / "index.ts").write_text(
        'import express from "express"\nimport cors from "cors"\nimport { PrismaClient } from "@prisma/client"\n\n'
        "const prisma = new PrismaClient()\nconst app = express()\napp.use(cors())\napp.use(express.json())\n\n"
        f"const FIELDS = {allowed} as const\n\n"
        f'app.get("/{plural}", async (_req, res) => {{\n'
        f"  const rows = await prisma.{lower_entity}.findMany({{ orderBy: {{ createdAt: \"desc\" }} }})\n"
        "  res.json(rows)\n})\n\n"
        f'app.post("/{plural}", async (req, res) => {{\n'
        "  const data: Record<string, unknown> = {}\n"
        "  for (const f of FIELDS) if (f in req.body) data[f] = req.body[f]\n"
        f"  const row = await prisma.{lower_entity}.create({{ data: data as any }})\n"
        "  res.status(201).json(row)\n})\n\n"
        f'app.delete("/{plural}/:id", async (req, res) => {{\n'
        f"  await prisma.{lower_entity}.delete({{ where: {{ id: req.params.id }} }}).catch(() => null)\n"
        "  res.status(204).end()\n})\n\n"
        "const port = Number(process.env.PORT) || 3001\n"
        'app.listen(port, () => console.log(`API on http://localhost:${port}`))\n',
        encoding="utf-8",
    )
    (folder / "CONTRACT.md").write_text(
        f"# API contract\n\n| Method | Path | Body | Response |\n| --- | --- | --- | --- |\n"
        f"| GET | /{plural} | | {entity}[] |\n"
        f"| POST | /{plural} | {entity} fields | {entity} |\n"
        f"| DELETE | /{plural}/:id | | 204 |\n",
        encoding="utf-8",
    )
