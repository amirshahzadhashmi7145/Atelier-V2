import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ToolCard } from "@/features/tools/components/ToolCard"

const base = {
  id: "tool_1",
  name: "repo.search",
  description: "Search the repo",
  permission: "read" as const,
  enabled: true,
  config: { trust: "untrusted" },
}

describe("ToolCard", () => {
  it("shows the cost note, usage, trust, and toggles the switch", () => {
    const onEnabled = vi.fn()
    render(<ToolCard tool={{ ...base, kind: "mcp" }} usedBy={2} onEnabled={onEnabled} onConfigure={vi.fn()} />)
    expect(screen.getByText("Calls another server")).toBeInTheDocument()
    expect(screen.getByText("used by 2 agents")).toBeInTheDocument()
    expect(screen.getByText("untrusted")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("switch", { name: "Enable repo.search" }))
    expect(onEnabled).toHaveBeenCalledWith(false)
  })

  it("marks a client tool as needing a browser session", () => {
    render(
      <ToolCard
        tool={{ ...base, kind: "client", name: "confirm_copy", config: {} }}
        usedBy={0}
        onEnabled={vi.fn()}
        onConfigure={vi.fn()}
      />,
    )
    expect(screen.getByText("needs an open browser session")).toBeInTheDocument()
    expect(screen.getByText("used by 0 agents")).toBeInTheDocument()
  })
})
