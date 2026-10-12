import { fireEvent, render, screen } from "@testing-library/react"
import { useState } from "react"
import { describe, expect, it } from "vitest"
import { SchemaForm } from "@/features/agents/components/SchemaForm"
import type { JsonSchema } from "@/features/agents/config-schema"

const schema: JsonSchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    temperature: { type: "number", minimum: 0, maximum: 2, default: 0.2 },
    reasoningEffort: { type: "string", enum: ["low", "medium", "high"], default: "medium" },
    webSearch: { type: "boolean", default: false },
  },
}

function Harness({ initial }: { initial: Record<string, unknown> }) {
  const [value, setValue] = useState(initial)
  return (
    <>
      <SchemaForm schema={schema} value={value} onChange={setValue} />
      <output>{JSON.stringify(value)}</output>
    </>
  )
}

describe("SchemaForm", () => {
  it("renders only the settings in the schema and writes reasoning effort and web search", () => {
    render(<Harness initial={{}} />)
    expect(screen.getByLabelText("Temperature")).toBeInTheDocument()
    expect(screen.getByRole("switch", { name: "Web search" })).toBeInTheDocument()
    expect(screen.queryByLabelText("Max output tokens")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "high" }))
    fireEvent.click(screen.getByRole("switch", { name: "Web search" }))
    expect(screen.getByText(/"reasoningEffort":"high"/)).toBeInTheDocument()
    expect(screen.getByText(/"webSearch":true/)).toBeInTheDocument()
  })
})
