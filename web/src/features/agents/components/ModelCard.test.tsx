import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { ModelCard, type ModelCardModel } from "@/features/agents/components/ModelCard"

const base: ModelCardModel = {
  name: "gpt-5",
  contextWindow: 128000,
  speedTier: "balanced",
  fitLine: null,
  priceInPerM: null,
  priceOutPerM: null,
  benchmarks: [],
}

describe("ModelCard", () => {
  it("says no stats entered when a human has not added a sourced benchmark", () => {
    render(<ModelCard model={{ ...base, priceInPerM: 5, priceOutPerM: 15 }} />)
    expect(screen.getByText("no stats entered")).toBeInTheDocument()
    expect(screen.queryByText(/per million/)).not.toBeInTheDocument()
  })

  it("links a benchmark only when it has a source", () => {
    render(
      <ModelCard
        model={{
          ...base,
          priceInPerM: 1,
          priceOutPerM: 2,
          benchmarks: [{ name: "fixture", score: 1, sourceUrl: "https://example.com/source" }],
        }}
      />,
    )
    expect(screen.queryByText("no stats entered")).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: "fixture: 1" })).toHaveAttribute("href", "https://example.com/source")
    expect(screen.getByText(/\$1 in/)).toBeInTheDocument()
  })
})
