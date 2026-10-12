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

test("run settings, model tags, and stacks", async ({ page }) => {
  test.setTimeout(90_000)
  await mockModelRoute(page)
  await page.goto("/settings/runs")
  await expect(page.getByLabel("Max spend per run")).toHaveValue("5")
  await expect(page.getByLabel("Max iterations")).toBeHidden()
  await page.getByText("Advanced", { exact: true }).click()
  await expect(page.getByLabel("Max iterations")).toBeVisible()
  const runs = await new AxeBuilder({ page }).analyze()
  expect(runs.violations).toEqual([])

  await page.goto("/agents/new")
  await page.getByRole("button", { name: "Import Frontend Engineer" }).click()
  await expect(page.getByRole("heading", { name: "Frontend Engineer" })).toBeVisible()
  await expect(page.getByLabel("Max iterations")).toHaveCount(0)
  const editor = await new AxeBuilder({ page }).analyze()
  expect(editor.violations).toEqual([])

  await page.goto("/settings/models")
  await expect(page.getByRole("heading", { name: "Models" })).toBeVisible()
  const row = page.getByRole("row", { name: /gpt-5/ })
  await row.getByLabel("gpt-5 frontend").check()
  await row.getByRole("button", { name: "Save" }).click()
  await expect(page.getByText("Saved gpt-5")).toBeVisible()

  await page.goto("/agents")
  await page.getByRole("link", { name: "Frontend Engineer" }).click()
  await expect(page.getByText("frontend", { exact: true })).toBeVisible()

  await page.getByRole("button", { name: "New stack" }).click()
  await page.locator("#stack-name").fill("Vite")
  await page.locator("#stack-version").fill("1.0")
  await page.getByRole("button", { name: "Create stack" }).click()
  await expect(page.getByText("Vite 1.0")).toBeVisible()
  await expect(page.getByText("# Enabled stacks")).toBeVisible()

  await page.getByRole("button", { name: "Import React" }).click()
  await expect(page.getByText("React 19.3.0", { exact: true })).toBeVisible()
})
