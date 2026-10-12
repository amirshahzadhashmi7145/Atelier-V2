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
}

const STACK_RULE =
  "Do not use or propose any other framework. If the task requires one, call raise_clarification."
const SKILL_RULE = "Call load_skill(name) before using a skill."

export function compilePrompt(input: CompileInput): {
  compiled: string
  tokenCount: number
} {
  const compiled = [
    `# Role\n${input.sections.role}`,
    `# Goal and definition of done\n${input.sections.goal}`,
    `# How to work\n${input.sections.instructions}`,
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
  ].join("\n\n")

  return { compiled, tokenCount: Math.ceil(compiled.length / 4) }
}
