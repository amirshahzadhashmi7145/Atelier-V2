import math

from store import db


def compile_prompt(sections: dict, tool_ids: list[str], skill_ids: list[str], stack_ids: list[str]) -> dict:
    tools = {item["id"]: item for item in db.listing("tool")}
    skills = {item["id"]: item for item in db.listing("skill")}
    stacks = {item["id"]: item for item in db.listing("stack")}
    skill_lines = []
    for skill_id in skill_ids:
        skill = skills.get(skill_id)
        if skill:
            skill_lines.append(f"{skill['name']}: {skill['description']}")
    tool_lines = []
    ordered = [*tool_ids, *[name for name in ("load_skill", "complete", "raise_clarification", "escalate") if name not in tool_ids]]
    for tool_id in ordered:
        tool = tools.get(tool_id)
        if tool:
            tool_lines.append(f"{tool['name']}: {tool['description']}")
    stack_lines = []
    for stack_id in stack_ids:
        stack = stacks.get(stack_id)
        if stack:
            stack_lines.append(f"{stack['name']} {stack['version']}")
    compiled = "\n\n".join(
        [
            f"# Role\n{sections.get('role', '')}",
            f"# Goal and definition of done\n{sections.get('goal', '')}",
            f"# How to work\n{sections.get('instructions', '')}",
            f"# Constraints\n{sections.get('constraints', '')}",
            f"# Output\n{sections.get('output', '')}",
            "\n".join(
                [
                    "# Enabled stacks",
                    *stack_lines,
                    "Do not use or propose any other framework. If the task requires one, call raise_clarification.",
                ]
            ),
            "\n".join(["# Tools", *tool_lines]),
            "\n".join(["# Skills", *skill_lines, "Call load_skill(name) before using a skill."]),
        ]
    )
    # ponytail: character count divided by four until a tokenizer is wired in
    return {"compiled": compiled, "tokenCount": math.ceil(len(compiled) / 4)}
