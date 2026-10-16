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
  await expect(page.getByRole("heading", { name: "Frontend Engineer" })).toBeVisible()
  const picker = page.getByLabel("Model")
  await expect(picker).toBeVisible()
  const groups = picker.locator("optgroup")
  await expect(groups.first()).toBeAttached()
  const labels = await groups.evaluateAll((nodes) => nodes.map((node) => node.getAttribute("label")))
  expect(labels.some((label) => label?.includes("OpenAI") || label === "openai")).toBeTruthy()
})
