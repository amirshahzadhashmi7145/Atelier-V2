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


def _public(domain: dict) -> dict:
    return {
        "id": domain["id"],
        "name": domain["name"],
        "category": domain["category"],
        "description": domain["description"],
        "teamTemplateId": domain["teamTemplateId"],
        "entity": domain["entity"],
        "fields": [{"name": f["name"], "label": f["label"], "kind": f["kind"]} for f in domain["fields"]],
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


def _frontend_app_tsx(domain: dict) -> str:
    entity = domain["entity"]
    name = domain["name"]
    fields = domain["fields"]
    blank = "{ " + ", ".join(f"{f['name']}: {_default_value(f)}" for f in fields) + " }"
    return (
        'import { useEffect, useMemo, useState } from "react"\n'
        f'import type {{ {entity} }} from "./fields"\n'
        'import { FIELDS, SEED } from "./fields"\n'
        'import { list, create, remove } from "./api"\n\n'
        f"type Draft = Omit<{entity}, \"id\">\n\n"
        f"const EMPTY: Draft = {blank}\n\n"
        "export default function App() {\n"
        f"  const [rows, setRows] = useState<{entity}[]>(SEED)\n"
        "  const [draft, setDraft] = useState<Draft>(EMPTY)\n"
        "  const [loading, setLoading] = useState(true)\n\n"
        "  useEffect(() => {\n    list().then((data) => {\n      setRows(data)\n      setLoading(false)\n    })\n  }, [])\n\n"
        "  const count = useMemo(() => rows.length, [rows])\n\n"
        "  async function add(e: React.FormEvent) {\n    e.preventDefault()\n"
        "    const created = await create(draft)\n"
        f"    const next = created ?? {{ ...draft, id: `local-${{Date.now()}}` }}\n"
        "    setRows((r) => [next, ...r])\n    setDraft(EMPTY)\n  }\n\n"
        "  async function del(id: string) {\n    await remove(id)\n    setRows((r) => r.filter((x) => x.id !== id))\n  }\n\n"
        "  return (\n"
        '    <div className="min-h-screen bg-slate-50 text-slate-900">\n'
        '      <header className="border-b bg-white">\n'
        '        <div className="mx-auto max-w-5xl px-4 py-4 flex items-center justify-between">\n'
        f'          <h1 className="text-xl font-semibold">{name}</h1>\n'
        '          <span className="text-sm text-slate-500">{loading ? "Loading…" : `${count} records`}</span>\n'
        "        </div>\n      </header>\n"
        '      <main className="mx-auto max-w-5xl px-4 py-6 grid gap-6">\n'
        '        <form onSubmit={add} className="grid gap-3 rounded-lg border bg-white p-4 sm:grid-cols-2 lg:grid-cols-3">\n'
        "          {FIELDS.map((f) => (\n"
        '            <label key={f.name} className="text-sm">\n'
        '              <span className="mb-1 block font-medium text-slate-600">{f.label}</span>\n'
        "              {f.options ? (\n"
        "                <select\n"
        '                  className="w-full rounded border px-2 py-1"\n'
        "                  value={String((draft as any)[f.name] ?? \"\")}\n"
        "                  onChange={(e) => setDraft((d) => ({ ...d, [f.name]: e.target.value }))}\n"
        "                >\n"
        '                  <option value="">—</option>\n'
        "                  {f.options.map((o) => (\n                    <option key={o} value={o}>{o}</option>\n                  ))}\n"
        "                </select>\n"
        "              ) : (\n"
        "                <input\n"
        '                  className="w-full rounded border px-2 py-1"\n'
        '                  type={f.kind === "number" ? "number" : f.kind === "date" ? "date" : "text"}\n'
        "                  value={String((draft as any)[f.name] ?? \"\")}\n"
        "                  onChange={(e) =>\n"
        '                    setDraft((d) => ({ ...d, [f.name]: f.kind === "number" ? Number(e.target.value) : e.target.value }))\n'
        "                  }\n"
        "                />\n"
        "              )}\n"
        "            </label>\n"
        "          ))}\n"
        '          <div className="flex items-end">\n'
        '            <button type="submit" className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white">Add</button>\n'
        "          </div>\n"
        "        </form>\n"
        '        <div className="overflow-x-auto rounded-lg border bg-white">\n'
        '          <table className="w-full text-sm">\n'
        '            <thead className="bg-slate-100 text-left text-slate-600">\n'
        "              <tr>\n"
        '                {FIELDS.map((f) => (\n                  <th key={f.name} className="px-3 py-2 font-medium">{f.label}</th>\n                ))}\n'
        '                <th className="px-3 py-2" />\n'
        "              </tr>\n"
        "            </thead>\n"
        "            <tbody>\n"
        "              {rows.map((row) => (\n"
        '                <tr key={row.id} className="border-t">\n'
        "                  {FIELDS.map((f) => (\n"
        '                    <td key={f.name} className="px-3 py-2">{String((row as any)[f.name] ?? "")}</td>\n'
        "                  ))}\n"
        '                  <td className="px-3 py-2 text-right">\n'
        '                    <button onClick={() => del(row.id)} className="text-slate-400 hover:text-red-600">Delete</button>\n'
        "                  </td>\n"
        "                </tr>\n"
        "              ))}\n"
        "            </tbody>\n"
        "          </table>\n"
        "        </div>\n"
        "      </main>\n"
        "    </div>\n"
        "  )\n}\n"
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
