import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { AgentEditor } from "@/features/agents/components/AgentEditor"
import { db } from "@/mocks/db"

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: { children?: unknown; href: string }) => (
    <a href={href} {...props}>
      {children as never}
    </a>
  ),
}))

function renderEditor(id: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AgentEditor id={id} />
    </QueryClientProvider>,
  )
}

function seedAgent(overrides: Record<string, unknown> = {}) {
  const agent = {
    id: "agt_test",
    name: "Test Agent",
    roleKey: "frontend-engineer",
    description: "Builds UI",
    model: { provider: "openai", name: "gpt-4.1", config: {} },
    activePromptVersionId: "pv_test",
    toolIds: ["files", "shell", "build_test", "preview_deploy", "search_data"],
    skillIds: [],
    stackIds: [],
    zones: ["src/**"],
    scope: { does: ["ui"], neverDoes: ["servers"], zones: ["src/**"] },
    evals: [],
    reportsTo: null,
    workerEngine: "loop",
    capabilities: { stacks: [], skills: [], tags: [] },
    createdAt: "2026-01-01T00:00:00.000Z",
    updatedAt: "2026-01-01T00:00:00.000Z",
    ...overrides,
  }
  db.agents.push(agent as (typeof db.agents)[number])
  db.versions.push({
    id: "pv_test",
    agentId: agent.id as string,
    version: 1,
    sections: { role: "Role", goal: "Goal", instructions: "Work", constraints: "Stay", output: "Done" },
    compiled: "compiled",
    tokenCount: 10,
    evalResults: [],
    createdAt: "2026-01-01T00:00:00.000Z",
  })
  return agent
}

describe("AgentEditor", () => {
  it("hides the worker engine toggle on supervisor pages", async () => {
    seedAgent({ name: "Team Lead", roleKey: "team-lead", toolIds: ["create_task", "record_review"] })
    renderEditor("agt_test")
    expect(await screen.findByDisplayValue("Team Lead")).toBeInTheDocument()
    expect(screen.queryByLabelText("Worker engine")).not.toBeInTheDocument()
  })

  it("warns when the model provider has no key", async () => {
    seedAgent()
    renderEditor("agt_test")
    expect(await screen.findByRole("alert")).toHaveTextContent("Add an API key for openai")
  })

  it("shows OpenHands tools on the Access page", async () => {
    seedAgent({ workerEngine: "openhands" })
    renderEditor("agt_test")
    expect(await screen.findByText("File editor")).toBeInTheDocument()
    expect(screen.getByText("Terminal")).toBeInTheDocument()
    expect(screen.getByText("Task tracker")).toBeInTheDocument()
    expect(screen.getByText(/zone, package, and build checks/)).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole("checkbox", { name: /files/ })).not.toBeInTheDocument())
    expect(screen.getByRole("checkbox", { name: /search_data/ })).toBeInTheDocument()
    expect(screen.getByRole("checkbox", { name: /load_skill/ })).toBeInTheDocument()
  })
})
