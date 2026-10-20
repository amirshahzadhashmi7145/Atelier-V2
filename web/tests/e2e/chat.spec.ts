import { expect, test } from "@playwright/test"

const API = process.env.E2E_API_URL || `http://127.0.0.1:${process.env.E2E_API_PORT || "8000"}`

test("a message creates a project run and shows the summary", async ({ page, request }) => {
  test.setTimeout(90_000)
  const agent = await request.post(`${API}/agents`, {
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
  const version = await request.post(`${API}/agents/${created.id}/versions`, {
    data: { sections: { role: "Role", goal: "Goal", instructions: "Work", constraints: "Stay", output: "Done" } },
  })
  const saved = (await version.json()) as { version: number }
  const active = await request.post(`${API}/agents/${created.id}/versions/${saved.version}/activate`)
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
  await expect(page.locator("[data-streaming]")).toContainText("Building", { timeout: 15_000 })
  await expect(page.getByText("Landing page with a hero and three feature cards.", { exact: true })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText("Files changed: index.html", { exact: true })).toBeVisible()
})

test("run evals shows chips and enables set active", async ({ page, request }) => {
  test.setTimeout(90_000)
  const agent = await request.post(`${API}/agents`, {
    data: { name: "Eval Agent", roleKey: "frontend", description: "Evals", model: { provider: "openai", name: "gpt-5", config: {} }, toolIds: ["files", "build_test", "headless_browser"] },
  })
  expect(agent.ok()).toBeTruthy()
  const created = (await agent.json()) as { id: string }
  const added = await request.post(`${API}/agents/${created.id}/evals`, {
    data: { name: "Hero", task: "Ship a page", criteria: ["Hero is visible"], passRule: "build_and_tests" },
  })
  expect(added.ok()).toBeTruthy()
  const version = await request.post(`${API}/agents/${created.id}/versions`, {
    data: { sections: { role: "Role", goal: "Goal", instructions: "Work", constraints: "Stay", output: "Done" } },
  })
  expect(version.ok()).toBeTruthy()
  await page.goto(`/agents/${created.id}`)
  await expect(page.getByRole("button", { name: "Set active" })).toBeDisabled()
  await page.getByRole("button", { name: "Run evals" }).click()
  await expect(page.locator("[data-eval-status='pass']")).toBeVisible({ timeout: 60_000 })
  await expect(page.getByRole("button", { name: "Set active" })).toBeEnabled()
})

test("a failed run shows the error and try again", async ({ page, request }) => {
  test.setTimeout(90_000)
  const agent = await request.post(`${API}/agents`, {
    data: { name: "Retry Agent", roleKey: "frontend", description: "Builds pages", model: { provider: "openai", name: "gpt-5", config: {} }, toolIds: ["files"] },
  })
  const created = (await agent.json()) as { id: string }
  const version = await request.post(`${API}/agents/${created.id}/versions`, {
    data: { sections: { role: "Role", goal: "Goal", instructions: "Work", constraints: "Stay", output: "Done" } },
  })
  const saved = (await version.json()) as { version: number }
  expect((await request.post(`${API}/agents/${created.id}/versions/${saved.version}/activate`)).ok()).toBeTruthy()
  await page.goto("/chat")
  await page.getByRole("button", { name: "New project" }).click()
  await page.getByLabel("Name").fill("Retry")
  await page.getByLabel("Agent").selectOption({ label: "Retry Agent" })
  await page.getByRole("button", { name: "Create" }).click()
  await page.getByLabel("Message").fill("force-fail the build")
  await page.getByRole("button", { name: "Send" }).click()
  await expect(page.locator("article.rounded p.whitespace-pre-wrap").filter({ hasText: "The run exceeded the spend cap." })).toBeVisible({
    timeout: 30_000,
  })
  await page.getByRole("button", { name: "Try again" }).click()
  await expect(page.getByText("Previous attempt failed:")).toBeVisible()
})

async function activateAgent(request: import("@playwright/test").APIRequestContext, name: string, toolIds: string[]) {
  const agent = await request.post(`${API}/agents`, {
    data: { name, roleKey: "frontend", description: name, model: { provider: "openai", name: "gpt-5", config: {} }, toolIds },
  })
  expect(agent.ok()).toBeTruthy()
  const created = (await agent.json()) as { id: string }
  const version = await request.post(`${API}/agents/${created.id}/versions`, {
    data: { sections: { role: "Role", goal: "Goal", instructions: "Work", constraints: "Stay", output: "Done" } },
  })
  const saved = (await version.json()) as { version: number }
  expect((await request.post(`${API}/agents/${created.id}/versions/${saved.version}/activate`)).ok()).toBeTruthy()
  return created.id
}

async function openChat(page: import("@playwright/test").Page, project: string, agent: string) {
  await page.goto("/chat")
  await page.getByRole("button", { name: "New project" }).click()
  await page.getByLabel("Name").fill(project)
  const picker = page.getByLabel("Agent")
  await expect(picker.locator("option", { hasText: agent })).toHaveCount(1, { timeout: 15_000 })
  await picker.selectOption({ label: agent })
  await page.getByRole("button", { name: "Create" }).click()
  await expect(page.getByRole("heading", { name: project })).toBeVisible()
}

async function addMemberById(page: import("@playwright/test").Page, agentId: string) {
  const addMember = page.locator("#add-member")
  await expect(addMember.locator(`option[value="${agentId}"]`)).toHaveCount(1, { timeout: 15_000 })
  await addMember.selectOption(agentId)
  const submit = page.getByRole("button", { name: "Add agent to project", exact: true })
  await expect(submit).toBeEnabled({ timeout: 10_000 })
  await submit.click()
}

test("interleaved model calls stay in two bubbles", async ({ page, request }) => {
  test.setTimeout(60_000)
  await activateAgent(request, "Bubble Agent", ["files"])
  await openChat(page, "Bubbles", "Bubble Agent")
  await page.getByLabel("Message").fill("interleave-bubbles please")
  await page.getByRole("button", { name: "Send" }).click()
  await expect(page.locator("[data-bubble='a']")).toContainText("First bubble.", { timeout: 20_000 })
  await expect(page.locator("[data-bubble='b']")).toContainText("Second bubble.")
})

test("hello gets a direct reply and no run", async ({ page, request }) => {
  await activateAgent(request, "Hello Agent", ["files"])
  await openChat(page, "Hello", "Hello Agent")
  await page.getByLabel("Message").fill("hello")
  await page.getByRole("button", { name: "Send" }).click()
  await expect(page.getByText("without starting a run")).toBeVisible()
  await expect(page.locator("[data-label='chat']")).toBeVisible()
  await expect(page.getByRole("button", { name: "Working" })).toHaveCount(0)
})

test("a long command shows running with the command", async ({ page, request }) => {
  test.setTimeout(60_000)
  await activateAgent(request, "Shell Agent", ["shell"])
  await openChat(page, "Shell", "Shell Agent")
  await page.getByLabel("Message").fill("slow-command please")
  await page.getByRole("button", { name: "Send" }).click()
  await expect(page.locator("[data-thinking]")).toContainText(/running: sleep 8/, { timeout: 20_000 })
})

test("teach creates a skill and the preview updates", async ({ page, request }) => {
  const id = await activateAgent(request, "Teach Agent", ["files"])
  await page.goto(`/agents/${id}`)
  await page.getByRole("button", { name: "Teach" }).click()
  await page.getByLabel("Repo URL").fill("https://example.com/demo.git")
  await page.getByRole("button", { name: "Draft rules" }).click()
  await expect(page.getByLabel("Rules")).toHaveValue(/example.com\/demo.git/)
  await page.getByLabel("Tech name").fill("Hono")
  await page.getByLabel("Version").fill("4")
  await page.getByLabel("Docs URL").fill("https://hono.dev")
  await page.getByRole("button", { name: "Save" }).click()
  const preview = page.locator("pre").filter({ hasText: "Load when writing Hono." })
  await preview.scrollIntoViewIfNeeded()
  await expect(preview).toBeVisible({ timeout: 15_000 })
})

test("agent without build tools shows a warning", async ({ page, request }) => {
  const id = await activateAgent(request, "Bare Agent", ["files"])
  await page.goto(`/agents/${id}`)
  await expect(page.getByText("this agent cannot build or run anything")).toBeVisible()
})

test("a queued message is shown while another run is active", async ({ page, request }) => {
  test.setTimeout(60_000)
  await activateAgent(request, "Queue Agent", ["shell"])
  await openChat(page, "Queue", "Queue Agent")
  await page.getByLabel("Message").fill("slow-command please")
  await page.getByRole("button", { name: "Send" }).click()
  await expect(page.getByText("agent is working")).toBeVisible({ timeout: 15_000 })
  await page.getByLabel("Message").fill("second task while busy")
  await page.getByRole("button", { name: "Send" }).click()
  await expect(page.getByText("queued, will start after the current task")).toBeVisible()
})

test("the composer stop button stops the active run", async ({ page, request }) => {
  test.setTimeout(60_000)
  await activateAgent(request, "Stop Agent", ["shell"])
  await openChat(page, "StopRun", "Stop Agent")
  await page.getByLabel("Message").fill("slow-command please")
  await page.getByRole("button", { name: "Send" }).click()
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible({ timeout: 15_000 })
  await page.getByRole("button", { name: "Stop" }).click()
  await expect(page.getByText("stopped")).toBeVisible({ timeout: 15_000 })
})

test("complete it after a failed run starts a task run", async ({ page, request }) => {
  test.setTimeout(60_000)
  await activateAgent(request, "Follow Agent", ["files"])
  await openChat(page, "Follow", "Follow Agent")
  await page.getByLabel("Message").fill("force-fail please")
  await page.getByRole("button", { name: "Send" }).click()
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible({ timeout: 30_000 })
  await page.getByLabel("Message").fill("complete it")
  await page.getByRole("button", { name: "Send" }).click()
  await expect(page.locator("[data-label='task']")).toBeVisible()
  await expect(page.getByText("without starting a run")).toHaveCount(0)
})

test("a project can add a member, flags overlap in red, and colours agent replies", async ({ page, request }) => {
  test.setTimeout(90_000)
  const front = await activateAgent(request, "Overlap Frontend Engineer", ["files"])
  expect(
    (
      await request.patch(`${API}/agents/${front}`, {
        data: {
          zones: ["src/**", "package.json"],
          scope: { does: ["user interfaces"], neverDoes: [], zones: ["src/**", "package.json"] },
        },
      })
    ).ok(),
  ).toBeTruthy()
  const back = await request.post(`${API}/agents`, {
    data: {
      name: "Overlap Backend Engineer",
      roleKey: "backend-engineer",
      description: "APIs",
      model: { provider: "openai", name: "gpt-5", config: {} },
      toolIds: ["files"],
      zones: ["api/**", "package.json", "tsconfig*.json"],
      scope: {
        does: ["HTTP APIs", "auth backends"],
        neverDoes: ["user interfaces", "styling"],
        zones: ["api/**", "package.json", "tsconfig*.json"],
      },
    },
  })
  expect(back.ok()).toBeTruthy()
  const backId = ((await back.json()) as { id: string }).id
  const backVersion = await request.post(`${API}/agents/${backId}/versions`, {
    data: { sections: { role: "Role", goal: "Goal", instructions: "Work", constraints: "Stay", output: "Done" } },
  })
  const backSaved = (await backVersion.json()) as { version: number }
  expect((await request.post(`${API}/agents/${backId}/versions/${backSaved.version}/activate`)).ok()).toBeTruthy()
  const clash = await request.post(`${API}/agents`, {
    data: {
      name: "Overlap Clash Agent",
      roleKey: "frontend",
      description: "Clash",
      model: { provider: "openai", name: "gpt-5", config: {} },
      toolIds: ["files"],
      zones: ["src/**"],
      scope: { does: ["user interfaces"], neverDoes: [], zones: ["src/**"] },
    },
  })
  expect(clash.ok()).toBeTruthy()
  const clashId = ((await clash.json()) as { id: string }).id
  const clashVersion = await request.post(`${API}/agents/${clashId}/versions`, {
    data: { sections: { role: "Role", goal: "Goal", instructions: "Work", constraints: "Stay", output: "Done" } },
  })
  const clashSaved = (await clashVersion.json()) as { version: number }
  expect((await request.post(`${API}/agents/${clashId}/versions/${clashSaved.version}/activate`)).ok()).toBeTruthy()
  await openChat(page, "Team", "Overlap Frontend Engineer")
  await addMemberById(page, backId)
  await expect(page.locator("[data-member='Overlap Backend Engineer']")).toBeVisible()
  await addMemberById(page, clashId)
  await expect(page.locator("[data-zone-overlap]")).toBeVisible()
  const message = page.getByLabel("Message", { exact: true })
  await message.scrollIntoViewIfNeeded()
  await message.fill("@Backend hello")
  await page.getByRole("button", { name: "Send", exact: true }).click()
  await expect(page.locator("[data-agent='Overlap Backend Engineer']")).toBeVisible({ timeout: 15_000 })
  await message.fill("@Frontend hello")
  await page.getByRole("button", { name: "Send", exact: true }).click()
  await expect(page.locator("[data-agent='Overlap Frontend Engineer']")).toBeVisible({ timeout: 15_000 })
})

async function activateRole(
  request: import("@playwright/test").APIRequestContext,
  body: Record<string, unknown>,
) {
  const agent = await request.post(`${API}/agents`, { data: body })
  expect(agent.ok()).toBeTruthy()
  const created = (await agent.json()) as { id: string }
  const version = await request.post(`${API}/agents/${created.id}/versions`, {
    data: { sections: { role: "Role", goal: "Goal", instructions: "Work", constraints: "Stay", output: "Done" } },
  })
  const saved = (await version.json()) as { version: number }
  expect((await request.post(`${API}/agents/${created.id}/versions/${saved.version}/activate`)).ok()).toBeTruthy()
  return created.id
}

test("a team lead plan can be edited and approved and the review verdict shows", async ({ page, request }) => {
  test.setTimeout(120_000)
  await activateRole(request, {
    name: "S13 Team Lead",
    roleKey: "team-lead",
    description: "Splits and reviews",
    model: { provider: "openai", name: "gpt-5", config: {} },
    toolIds: ["files", "shell", "build_test", "headless_browser"],
    zones: [],
    capabilities: { stacks: [], skills: [], tags: ["supervisor"] },
    scope: {
      does: ["splitting requests into tasks", "assigning tasks", "reviewing code against the task", "deciding when work is done"],
      neverDoes: ["writing application code", "editing files"],
      zones: [],
    },
  })
  const backId = await activateRole(request, {
    name: "S13 Backend Engineer",
    roleKey: "backend-engineer",
    description: "APIs",
    model: { provider: "openai", name: "gpt-5", config: {} },
    toolIds: ["files", "build_test"],
    zones: ["server/**", "package.json", "tsconfig*.json"],
    scope: {
      does: ["HTTP APIs", "auth backends"],
      neverDoes: ["user interfaces", "styling"],
      zones: ["server/**", "package.json", "tsconfig*.json"],
    },
  })
  const frontId = await activateRole(request, {
    name: "S13 Frontend Engineer",
    roleKey: "frontend-engineer",
    description: "UI",
    model: { provider: "openai", name: "gpt-5", config: {} },
    toolIds: ["files", "build_test"],
    zones: ["src/**", "app/**", "public/**", "package.json", "tsconfig*.json"],
    scope: {
      does: ["user interfaces", "client-side state"],
      neverDoes: ["servers", "databases"],
      zones: ["src/**", "app/**", "public/**", "package.json", "tsconfig*.json"],
    },
  })
  await page.goto("/settings/runs")
  const approvePlans = page.getByLabel("Approve plans before running")
  await expect(approvePlans).toBeVisible({ timeout: 15_000 })
  if (!(await approvePlans.isChecked())) {
    await approvePlans.check()
    await page.getByRole("button", { name: "Save", exact: true }).click()
    await expect(page.getByText("Run settings saved")).toBeVisible()
  }
  await openChat(page, "LeadReview", "S13 Team Lead")
  await addMemberById(page, backId)
  await expect(page.locator("[data-member='S13 Backend Engineer']")).toBeVisible()
  await addMemberById(page, frontId)
  await expect(page.locator("[data-member='S13 Frontend Engineer']")).toBeVisible()
  await page.getByLabel("Message", { exact: true }).fill("build a todo app with login")
  await page.getByRole("button", { name: "Send", exact: true }).click()
  const plan = page.locator("[data-plan]")
  await expect(plan).toBeVisible({ timeout: 30_000 })
  await expect(page.locator("[data-label='plan']")).toBeVisible()
  const firstStep = plan.locator("textarea").first()
  await firstStep.fill("Implement login and the notes API")
  const approved = page.waitForResponse(
    (response) => response.url().includes("/approve") && response.request().method() === "POST",
    { timeout: 15_000 },
  )
  await plan.getByRole("button", { name: "Approve" }).evaluate((node: HTMLElement) => node.click())
  expect((await approved).ok(), await (await approved).text()).toBeTruthy()
  await expect(page.locator("[data-verdict='approve']").first()).toBeVisible({ timeout: 60_000 })
  await expect(page.locator("[data-label='review']").first()).toBeVisible()
})

test("the chat page is exactly the viewport", async ({ page, request }) => {
  await activateAgent(request, "Layout Agent", ["files"])
  await openChat(page, "Layout", "Layout Agent")
  for (const width of [1920, 1280, 768]) {
    await page.setViewportSize({ width, height: 800 })
    expect(await page.evaluate(() => document.documentElement.scrollHeight === window.innerHeight)).toBe(true)
  }
  await expect(page.getByRole("button", { name: "Preview", exact: true })).toBeVisible()
})
