import { expect, test } from "@playwright/test"

test("a message creates a project run and shows the summary", async ({ page, request }) => {
  test.setTimeout(90_000)
  const agent = await request.post("http://127.0.0.1:8000/agents", {
    data: {
      name: "Frontend",
      roleKey: "frontend",
      description: "Builds pages",
      model: { provider: "openai", name: "gpt-5", config: {} },
      toolIds: ["files", "preview_deploy"],
    },
  })
  expect(agent.ok()).toBeTruthy()
  const created = (await agent.json()) as { id: string }
  const version = await request.post(`http://127.0.0.1:8000/agents/${created.id}/versions`, {
    data: { sections: { role: "Role", goal: "Goal", instructions: "Work", constraints: "Stay", output: "Done" } },
  })
  const saved = (await version.json()) as { version: number }
  const active = await request.post(`http://127.0.0.1:8000/agents/${created.id}/versions/${saved.version}/activate`)
  expect(active.ok()).toBeTruthy()

  await page.goto("/chat")
  await page.getByRole("button", { name: "New project" }).click()
  await page.getByLabel("Name").fill("Site")
  await page.getByLabel("Agent").selectOption({ label: "Frontend" })
  await page.getByRole("button", { name: "Create" }).click()
  await expect(page.getByRole("heading", { name: "Site" })).toBeVisible()
  await expect(page.getByText("DEV LOCAL MODE")).toBeVisible()
  await page.getByLabel("Message").fill("Create a landing page with a hero and three feature cards")
  await page.getByRole("button", { name: "Send" }).click()
  await expect(page.getByText("Landing page with a hero and three feature cards.")).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText("index.html")).toBeVisible()
})
