import { expect, test } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"

const pages = [
  ["/agents", "Agents", "No agents yet"],
  ["/tools", "Tools", "shell"],
  ["/skills", "Skills", "No skills yet"],
  ["/runs", "Runs", "No runs yet"],
  ["/settings/providers", "Providers", ".env.local"],
] as const

for (const [path, heading, text] of pages) {
  test(`${heading} page loads and has no axe violations`, async ({ page }) => {
    await page.goto(path)
    await expect(page.getByRole("heading", { name: heading })).toBeVisible()
    await expect(page.getByText(text).first()).toBeVisible()
    const results = await new AxeBuilder({ page }).analyze()
    expect(results.violations).toEqual([])
  })
}

test("studio nav opens tools", async ({ page }) => {
  await page.goto("/agents")
  await page.getByRole("link", { name: "Tools" }).click()
  await expect(page.getByRole("heading", { name: "Tools" })).toBeVisible()
})
