import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ModelPicker } from "@/features/agents/components/ModelPicker"

const models = [{ name: "o3" }, { name: "gpt-5" }, { name: "gpt-4.1" }, { name: "gpt-4.1-mini" }]

describe("ModelPicker", () => {
  it("filters the list from the search box", () => {
    render(<ModelPicker models={models} value="" onChange={vi.fn()} />)
    fireEvent.change(screen.getByLabelText("Search models"), { target: { value: "4.1" } })
    const options = screen.getAllByRole("option").map((option) => option.textContent)
    expect(options).toEqual(["Choose a model", "gpt-4.1", "gpt-4.1-mini"])
  })

  it("shows clean Gemini names grouped by provider", () => {
    render(
      <ModelPicker
        models={[
          { name: "gpt-4.1-mini", provider: "openai" },
          { name: "models/gemini-3.1-pro-preview", provider: "gemini" },
        ]}
        value="models/gemini-3.1-pro-preview"
        onChange={vi.fn()}
      />,
    )
    const picker = screen.getByLabelText("Model")
    expect(picker).toHaveValue("gemini-3.1-pro-preview")
    expect(screen.getByRole("option", { name: "gemini-3.1-pro-preview" })).toBeTruthy()
    expect(screen.queryByRole("option", { name: "models/gemini-3.1-pro-preview" })).toBeNull()
    const groups = picker.querySelectorAll("optgroup")
    expect([...groups].map((group) => group.getAttribute("label"))).toEqual(["OpenAI", "Google Gemini"])
  })
})
