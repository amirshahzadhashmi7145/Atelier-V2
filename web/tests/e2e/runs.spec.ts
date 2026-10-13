import { expect, test, type Page } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"

const MODEL_IDS = ["o3", "gpt-5", "gpt-4.1", "gpt-4.1-mini"]

async function mockModelRoute(page: Page) {
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

async function activateAgent(page: Page) {
  await mockModelRoute(page)
  await page.goto("/settings/providers")
  await page.getByRole("button", { name: "Test connection" }).click()
  await page.getByRole("button", { name: "Refresh models" }).click()
  await expect(page.getByText("gpt-5", { exact: true })).toBeVisible()
  await page.goto("/agents/new")
  await page.getByRole("button", { name: "Import Frontend Engineer" }).click()
  await expect(page.getByRole("heading", { name: "Frontend Engineer" })).toBeVisible()
  await page.getByLabel("Eval name").fill("Button visible")
  await page.getByLabel("Task").fill("Add a primary button")
  await page.getByLabel("Criteria").fill("The button is visible")
  await page.getByLabel("Pass rule").fill("The build passes")
  await page.getByRole("button", { name: "Add eval" }).click()
  await expect(page.getByText("Button visible")).toBeVisible()
  await page.getByRole("button", { name: "Save as new version" }).click()
  await expect(page.getByText("Saved version 2")).toBeVisible()
  await page.getByRole("button", { name: "Run evals" }).click()
  await expect(page.getByText("Active version ready")).toBeVisible()
  await page.getByRole("button", { name: "Set active" }).click()
  await expect(page.getByText("Active version set")).toBeVisible()
}

test("start a run, answer it, and open the summary", async ({ page }) => {
  test.setTimeout(120_000)
  await activateAgent(page)
  await page.getByRole("button", { name: "Test run" }).click()
  await expect(page.getByRole("heading", { name: "New run" })).toBeVisible()
  await expect(page.getByLabel("Task")).toHaveValue("Add a primary button")
  await expect(page.getByText("Spend cap $5.00")).toBeVisible()
  const form = await new AxeBuilder({ page }).analyze()
  expect(form.violations).toEqual([])

  await page.getByRole("button", { name: "Start run" }).click()
  await expect(page.getByRole("heading", { name: "Run" })).toBeVisible()
  await expect(page.locator("[data-seq='1']")).toBeVisible({ timeout: 10_000 })
  const live = await new AxeBuilder({ page }).analyze()
  expect(live.violations).toEqual([])

  await expect(page.getByRole("button", { name: "Respond" })).toBeVisible({ timeout: 20_000 })
  await page.getByRole("button", { name: "Respond" }).click()
  await expect(page.getByLabel("Answer")).toBeVisible({ timeout: 20_000 })
  await page.getByLabel("Answer").fill("Go")
  await page.getByRole("button", { name: "Send answer" }).click()

  await page.reload()
  const started = page.getByRole("button", { name: "Run started", exact: true })
  await expect(started).toBeVisible()
  await page.waitForTimeout(2_000)
  await expect(started).toBeVisible()
  await started.click()
  await expect(page.locator("[data-seq]")).toHaveCount(1)

  await expect(page.getByText("Added a primary button to the page.")).toBeVisible({ timeout: 90_000 })
  await page.getByRole("tab", { name: "Diff" }).click()
  await expect(page.getByRole("button", { name: /src\/App\.tsx/ })).toBeVisible()
})

test("stop a run and see cancelled within 2 seconds", async ({ page }) => {
  test.setTimeout(90_000)
  await activateAgent(page)
  await page.getByRole("button", { name: "Test run" }).click()
  await page.getByRole("button", { name: "Start run" }).click()
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible()
  await page.getByRole("button", { name: "Stop" }).click()
  await page.getByRole("button", { name: "Stop now" }).click()
  await expect(page.getByText("cancelled", { exact: true })).toBeVisible({ timeout: 2000 })
})

test("runs list has no axe violations", async ({ page }) => {
  await page.goto("/runs")
  await expect(page.getByRole("heading", { name: "Runs" })).toBeVisible()
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})
