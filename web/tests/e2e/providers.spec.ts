import { expect, test } from "@playwright/test"

test("providers page shows OpenAI and Gemini cards", async ({ page }) => {
  await page.goto("/settings/providers")
  await expect(page.getByRole("heading", { name: "Providers" })).toBeVisible()
  await expect(page.getByText("Google Gemini")).toBeVisible()
  await expect(page.getByText("OpenAI").first()).toBeVisible()
})

test("agent model picker groups providers", async ({ page }) => {
  await page.goto("/agents/new")
  await page.getByRole("button", { name: "Import Frontend Engineer" }).click()
  await expect(page.getByLabel("Model")).toBeVisible()
  const groups = page.locator("optgroup")
  await expect(groups).toHaveCount(await groups.count())
  const labels = await groups.evaluateAll((nodes) => nodes.map((node) => node.getAttribute("label")))
  expect(labels.some((label) => label?.includes("OpenAI") || label === "openai")).toBeTruthy()
})
