import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ImportReview } from "@/features/skills/components/ImportReview"

describe("ImportReview", () => {
  it("shows the body and a re-import diff before confirm", () => {
    render(
      <ImportReview
        name="react-best-practices"
        description="Load when writing React UI."
        body={"# React best practices\n\nPrefer server components."}
        files={[{ name: "notes.md" }]}
        diff={[{ path: "SKILL.md", before: "old", after: "new" }]}
        onConfirm={vi.fn()}
      />,
    )
    expect(screen.getByText(/Prefer server components/)).toBeInTheDocument()
    expect(screen.getByText("SKILL.md")).toBeInTheDocument()
    expect(screen.getByText("notes.md")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Confirm" })).toBeInTheDocument()
  })
})
