import { expect, test } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"

const MODEL_IDS = ["o3", "gpt-5", "gpt-4.1", "gpt-4.1-mini"]

async function axe(page: import("@playwright/test").Page) {
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
}

async function mockModelRoute(page: import("@playwright/test").Page) {
  await page.route("**/api/providers/openai/models**", (route) => route.fulfill({ json: { ids: MODEL_IDS } }))
  await page.addInitScript((ids) => {
    sessionStorage.setItem("atelier-discovered-models", JSON.stringify(ids))
    const original = window.fetch.bind(window)
    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
      if (url.includes("/api/providers/openai/models")) {
        return Promise.resolve(
          new Response(JSON.stringify({ ids }), { status: 200, headers: { "content-type": "application/json" } }),
        )
      }
      return original(input, init)
    }
  }, MODEL_IDS)
}

test("skills, discovered models, and the tools registry", async ({ page }) => {
  test.setTimeout(120_000)
  await mockModelRoute(page)

  await page.goto("/skills/new")
  await page.getByLabel("Name").fill("button-copy")
  await page.getByLabel("Description").fill("Load when adding a button.")
  await page.getByRole("textbox", { name: "Body" }).fill("Write the label in the button.")
  await page.getByRole("button", { name: "Save" }).click()
  await page.waitForURL(/\/skills\/skill_/)
  await expect(page.getByText("button-copy").first()).toBeVisible()
  await axe(page)

  await page.getByRole("button", { name: "Import" }).click()
  await page.getByLabel("GitHub URL").fill("https://github.com/vercel-labs/agent-skills")
  await page.getByLabel("Folder path").fill("skills/react-best-practices")
  await page.getByRole("button", { name: "Preview" }).click()
  await expect(page.getByText("Prefer server components.")).toBeVisible()
  await page.getByRole("button", { name: "Confirm" }).click()
  await expect(page.getByText("react-best-practices").first()).toBeVisible()

  await page.goto("/settings/providers")
  await page.getByRole("button", { name: "Refresh models" }).click()
  await expect(page.getByText("o3", { exact: true })).toBeVisible()
  await expect(page.getByText("gpt-4.1-mini", { exact: true })).toBeVisible()
  const cached = page.getByText("4 models cached")
  await expect(cached).toBeVisible()
  await expect(cached).toHaveCount(0, { timeout: 10_000 })
  await axe(page)

  await page.goto("/tools")
  await expect(page.getByRole("heading", { name: "Tools" })).toBeVisible()
  await axe(page)
  await page.getByRole("tab", { name: "MCP" }).click()
  await page.getByRole("button", { name: "Add server" }).click()
  await page.getByLabel("Name").fill("Repo")
  await page.getByLabel("URL").fill("https://mcp.example")
  await page.getByRole("button", { name: "Discover" }).click()
  await page.getByRole("checkbox", { name: "repo.search read" }).check()
  await page.getByRole("checkbox", { name: "repo.web external" }).check()
  await page.getByRole("button", { name: "Confirm" }).click()
  await expect(page.getByText("repo.search").first()).toBeVisible()
  await expect(page.getByText("untrusted").first()).toBeVisible()

  await page.getByRole("tab", { name: "APIs" }).click()
  await page.getByRole("button", { name: "Import spec" }).click()
  await page.getByLabel("OpenAPI").fill("paths:\n  /users:\n    get:\n      operationId: listUsers\n      summary: List users\n")
  await page.getByRole("button", { name: "Preview" }).click()
  await page.getByRole("checkbox", { name: /GET \/users List users/ }).check()
  await page.getByRole("button", { name: "Confirm" }).click()
  await expect(page.getByText("listUsers").first()).toBeVisible()

  await page.getByRole("tab", { name: "Data" }).click()
  await page.getByRole("button", { name: "Add source" }).click()
  await page.getByLabel("Name").fill("React docs")
  await page.getByLabel("Ref", { exact: true }).fill("https://react.dev")
  await page.getByRole("button", { name: "Add source" }).click()
  await expect(page.getByRole("cell", { name: "React docs" })).toBeVisible()
  await page.getByRole("button", { name: "Refresh" }).click()
  await expect(page.getByRole("cell", { name: "1", exact: true })).toBeVisible()

  await page.goto("/agents/new")
  await page.getByRole("button", { name: "Import Frontend Engineer" }).click()
  await expect(page.getByRole("heading", { name: "Frontend Engineer" })).toBeVisible()
  await page.getByLabel("Model", { exact: true }).selectOption("gpt-5")
  await expect(page.getByRole("button", { name: "high", exact: true })).toBeVisible()
  await page.getByLabel("Model", { exact: true }).selectOption("gpt-4.1")
  await expect(page.getByLabel("Temperature")).toBeVisible()
  await expect(page.getByRole("button", { name: "high", exact: true })).toHaveCount(0)
  await page.getByLabel("Model", { exact: true }).selectOption("gpt-5")
  await page.getByRole("checkbox", { name: "react-best-practices" }).check()
  await page.getByRole("checkbox", { name: "repo.search" }).check()
  await expect(page.getByText("react-best-practices: Load when writing React UI.")).toBeVisible()
  await expect(page.getByText("repo.search: Search the connected repository.")).toBeVisible()
  await axe(page)
})
