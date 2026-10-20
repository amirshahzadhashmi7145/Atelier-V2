import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { RolesForm } from "@/features/settings/components/RolesForm"

function renderForm() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <RolesForm />
    </QueryClientProvider>,
  )
}

describe("RolesForm", () => {
  it("edits a seed role and resets it to default", async () => {
    renderForm()
    const name = await screen.findByLabelText("backend-engineer name")
    const row = name.closest("tr")
    expect(row).toBeTruthy()
    fireEvent.change(name, { target: { value: "API Worker" } })
    fireEvent.click(within(row as HTMLElement).getByRole("button", { name: "Save" }))
    await waitFor(() => expect(screen.getByLabelText("backend-engineer name")).toHaveValue("API Worker"))
    fireEvent.click(within(row as HTMLElement).getByRole("button", { name: "Reset to default" }))
    await waitFor(() => expect(screen.getByLabelText("backend-engineer name")).toHaveValue("Backend Engineer"))
  })
})
