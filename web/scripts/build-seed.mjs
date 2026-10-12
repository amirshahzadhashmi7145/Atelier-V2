import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { parse } from "yaml"

const root = join(dirname(fileURLToPath(import.meta.url)), "../..")
const createdAt = "2026-10-01T00:00:00.000Z"

function readYaml(path) {
  return parse(readFileSync(path, "utf8"))
}

function skillFromDir(id) {
  const dir = join(root, "skills", id)
  const markdown = readFileSync(join(dir, "SKILL.md"), "utf8")
  const match = markdown.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/)
  if (!match) throw new Error(`SKILL.md for ${id} is missing frontmatter`)
  const meta = parse(match[1])
  const files = readdirSync(dir)
    .filter((name) => name !== "SKILL.md")
    .map((name) => ({
      id: `${id}/${name}`,
      name,
      size: statSync(join(dir, name)).size,
    }))
  return {
    id,
    name: meta.name,
    description: meta.description,
    body: match[2].trim(),
    files,
    version: 1,
    versions: [{ version: 1, createdAt }],
    origin: "seed",
    createdAt,
  }
}

const role = readYaml(join(root, "roles/frontend-engineer.yaml"))
const stackFiles = readdirSync(join(root, "stacks")).filter((name) => name.endsWith(".yaml"))
const dataSources = []
const stacks = stackFiles.map((file) => {
  const stack = readYaml(join(root, "stacks", file))
  for (const source of stack.sources ?? []) {
    dataSources.push({
      ...source,
      lastPulledAt: null,
      pagesChanged: null,
      versionTag: null,
    })
  }
  delete stack.sources
  return stack
})

const skillIds = readdirSync(join(root, "skills")).filter((name) =>
  statSync(join(root, "skills", name)).isDirectory(),
)

const seed = {
  library: {
    agents: [
      {
        id: role.id,
        name: role.name,
        roleKey: role.roleKey,
        description: role.description,
        model: role.model,
        budgets: role.budgets,
        toolIds: role.toolIds,
        skillIds: role.skillIds,
        stackIds: role.stackIds,
        zones: role.zones,
        sections: role.sections,
        evals: role.evals ?? [],
      },
    ],
    skills: skillIds.map(skillFromDir),
    stacks,
    dataSources,
  },
}

writeFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../src/mocks/seed.generated.json"),
  `${JSON.stringify(seed, null, 2)}\n`,
)
