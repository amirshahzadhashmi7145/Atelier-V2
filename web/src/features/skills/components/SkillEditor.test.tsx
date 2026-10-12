import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { SkillEditor } from "@/features/skills/components/SkillEditor"

describe("SkillEditor", () => {
  it("counts the description and lists versions and agents", () => {
    render(
      <SkillEditor
        initial={{
          name: "react-best-practices",
          description: "Load",
          body: "# Body",
          files: [],
          versions: [{ version: 1, createdAt: "2026-10-01T00:00:00.000Z" }],
          origin: "studio",
        }}
        agents={[{ id: "agt_1", name: "Frontend Engineer" }]}
        onSave={vi.fn()}
      />,
    )
    expect(screen.getByText("say when to load it")).toBeInTheDocument()
    expect(screen.getByText("4 characters")).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Load when writing UI" } })
    expect(screen.getByText("20 characters")).toBeInTheDocument()
    expect(screen.getByText(/Version 1/)).toBeInTheDocument()
    expect(screen.getByText("Frontend Engineer")).toBeInTheDocument()
  })
})
