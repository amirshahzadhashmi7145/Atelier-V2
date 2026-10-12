import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"
import { AgentList } from "@/features/agents/components/AgentList"
import { server } from "@/mocks/server"

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AgentList />
    </QueryClientProvider>,
  )
}

describe("AgentList", () => {
  it("shows agents returned by the API", async () => {
    server.use(
      http.get("/agents", () =>
        HttpResponse.json([
          { id: "agt_1", name: "Frontend Engineer", description: "Builds UI" },
        ]),
      ),
    )
    renderList()
    expect(await screen.findByRole("link", { name: "Frontend Engineer" })).toBeInTheDocument()
  })

  it("shows an empty state", async () => {
    server.use(http.get("/agents", () => HttpResponse.json([])))
    renderList()
    expect(await screen.findByText("No agents yet")).toBeInTheDocument()
  })

  it("shows an error state", async () => {
    server.use(
      http.get("/agents", () => HttpResponse.json({ code: "failed", message: "boom" }, { status: 400 })),
    )
    renderList()
    expect(await screen.findByText("boom")).toBeInTheDocument()
  })
})
