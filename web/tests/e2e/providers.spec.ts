import { expect, test } from "@playwright/test"

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

test("providers page shows OpenAI and Gemini cards", async ({ page }) => {
  await page.goto("/settings/providers")
  await expect(page.getByRole("heading", { name: "Providers" })).toBeVisible()
  await expect(page.getByText("Google Gemini")).toBeVisible()
  await expect(page.getByText("OpenAI").first()).toBeVisible()
  await expect(page.locator("#provider-key-openai")).toBeVisible()
  await expect(page.locator("#provider-key-gemini")).toBeVisible()
  await expect(page.getByRole("button", { name: "Save key" }).first()).toBeVisible()
})

test("agent model picker groups providers", async ({ page }) => {
  await mockModelRoute(page)
  await page.goto("/agents/new")
  await page.getByRole("button", { name: "Import Frontend Engineer" }).click()
  await expect(page.getByRole("heading", { name: "Frontend Engineer" })).toBeVisible()
  const picker = page.getByLabel("Model", { exact: true })
  await expect(picker).toBeVisible()
  const groups = picker.locator("optgroup")
  await expect(groups.first()).toBeAttached()
  const labels = await groups.evaluateAll((nodes) => nodes.map((node) => node.getAttribute("label")))
  expect(labels.some((label) => label?.includes("OpenAI") || label === "openai")).toBeTruthy()
})
