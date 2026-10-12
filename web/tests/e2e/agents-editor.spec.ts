import { expect, test } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"

const MODEL_IDS = ["o3", "gpt-5", "gpt-4.1", "gpt-4.1-mini"]

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

test("import a library agent, configure the model, and activate a version", async ({ page }) => {
  test.setTimeout(90_000)
  await mockModelRoute(page)
  await page.goto("/settings/providers")
  await page.getByRole("button", { name: "Test connection" }).click()
  await expect(page.getByText("Connected", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: "Refresh models" }).click()
  await expect(page.getByText("gpt-5", { exact: true })).toBeVisible()

  await page.goto("/agents/new")
  await page.getByRole("button", { name: "Import Frontend Engineer" }).click()
  await expect(page.getByRole("heading", { name: "Frontend Engineer" })).toBeVisible()
  const role = page.getByRole("textbox", { name: "Role", exact: true })
  await expect(role).toBeVisible()
  const editor = await new AxeBuilder({ page }).analyze()
  expect(editor.violations).toEqual([])

  await page.getByLabel("Model", { exact: true }).selectOption("gpt-5")
  await page.getByRole("button", { name: "high", exact: true }).click()
  await page.getByRole("switch", { name: "Web search" }).click()
  await role.fill("ROLE_MARKER you implement the UI.")

  await page.getByLabel("Eval name").fill("Button visible")
  await page.getByLabel("Task").fill("Add a primary button")
  await page.getByLabel("Criteria").fill("The button is visible")
  await page.getByLabel("Pass rule").fill("The build passes")
  await page.getByRole("button", { name: "Add eval" }).click()
  await expect(page.getByText("Button visible")).toBeVisible()

  await page.getByRole("button", { name: "Save as new version" }).click()
  await expect(page.getByText("Saved version 2")).toBeVisible()
  await expect(page.getByText("Evals have not all passed")).toBeVisible()

  await page.getByRole("button", { name: "Run evals" }).click()
  await expect(page.getByText("Active version ready")).toBeVisible()
  await page.getByRole("button", { name: "Set active" }).click()
  await expect(page.getByText("Active version set")).toBeVisible()

  await page.getByRole("button", { name: "Versions" }).click()
  await expect(page.getByRole("heading", { name: "Versions" })).toBeVisible()
  await expect(page.getByText("ROLE_MARKER").last()).toBeVisible()
})
