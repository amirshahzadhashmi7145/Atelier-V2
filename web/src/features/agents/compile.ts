export type CompileInput = {
  sections: {
    role: string
    goal: string
    instructions: string
    constraints: string
    output: string
  }
  stacks: { name: string; version: string }[]
  tools: { name: string; description: string }[]
  skills: { name: string; description: string }[]
  scope?: { does: string[]; neverDoes: string[]; zones: string[] }
  worker?: boolean
}

const SCOPE_LINE =
  "If a task falls under 'never does', do not ask for approval and do not offer to do it. Reply that it is outside your role and name what you can do instead. You cannot enable stacks or change your own scope; only the user can."

function scopeBlock(scope?: CompileInput["scope"]) {
  const does = scope?.does.join(", ") || "none"
  const never = scope?.neverDoes.join(", ") || "none"
  const zones = scope?.zones.join(", ") || "none"
  return ["# Scope", `Does: ${does}`, `Never does: ${never}`, `Zones: ${zones}`, SCOPE_LINE].join("\n")
}

const STACK_RULE =
  "Do not use or propose any other framework. If the task requires one, call raise_clarification."
const SKILL_RULE = "Call load_skill(name) before using a skill."
const FILES_LINE =
  "Prefer files.edit or files.append on existing files. Use files.write only for new files. After writes, run build_test before complete."

export function compilePrompt(input: CompileInput): {
  compiled: string
  tokenCount: number
} {
  const worker = input.worker !== false
  const how = worker ? `${input.sections.instructions}\n${FILES_LINE}` : input.sections.instructions
  const compiled = [
    `# Role\n${input.sections.role}`,
    `# Goal and definition of done\n${input.sections.goal}`,
    `# How to work\n${how}`,
    `# Constraints\n${input.sections.constraints}`,
    `# Output\n${input.sections.output}`,
    [
      "# Enabled stacks",
      ...input.stacks.map((stack) => `${stack.name} ${stack.version}`),
      STACK_RULE,
    ].join("\n"),
    ["# Tools", ...input.tools.map((tool) => `${tool.name}: ${tool.description}`)].join(
      "\n",
    ),
    [
      "# Skills",
      ...input.skills.map((skill) => `${skill.name}: ${skill.description}`),
      SKILL_RULE,
    ].join("\n"),
    scopeBlock(input.scope),
  ].join("\n\n")

  return { compiled, tokenCount: Math.ceil(compiled.length / 4) }
}
