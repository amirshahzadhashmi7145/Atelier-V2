from store import db


def token_count(text: str, model: str = "gpt-4o") -> int:
    import tiktoken

    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("o200k_base")
    return len(encoding.encode(text))


SCOPE_LINE = "If a task falls under 'never does', do not ask for approval and do not offer to do it. Reply that it is outside your role and name what you can do instead. You cannot enable stacks or change your own scope; only the user can."
FILES_LINE = "Prefer files.edit or files.append on existing files. Use files.write only for new files. After writes, run build_test before complete."


def scope_block(scope: dict | None) -> str:
    scope = scope or {}
    does = ", ".join(scope.get("does") or []) or "none"
    never = ", ".join(scope.get("neverDoes") or []) or "none"
    zones = ", ".join(scope.get("zones") or []) or "none"
    return "\n".join(["# Scope", f"Does: {does}", f"Never does: {never}", f"Zones: {zones}", SCOPE_LINE])


def compile_prompt(
    sections: dict,
    tool_ids: list[str],
    skill_ids: list[str],
    stack_ids: list[str],
    model: str = "gpt-4o",
    scope: dict | None = None,
    include_tools: bool = True,
    worker: bool = True,
) -> dict:
    tools = {item["id"]: item for item in db.listing("tool")}
    skills = {item["id"]: item for item in db.listing("skill")}
    stacks = {item["id"]: item for item in db.listing("stack")}
    skill_lines = []
    for skill_id in skill_ids:
        skill = skills.get(skill_id)
        if skill:
            skill_lines.append(f"{skill['name']}: {skill['description']}")
    tool_lines = []
    extra = ["load_skill", "complete", "raise_clarification", "escalate"] if worker else []
    ordered = [*tool_ids, *[name for name in extra if name not in tool_ids]]
    for tool_id in ordered:
        tool = tools.get(tool_id)
        if tool:
            tool_lines.append(f"{tool['name']}: {tool['description']}")
    stack_lines = []
    for stack_id in stack_ids:
        stack = stacks.get(stack_id)
        if stack:
            stack_lines.append(f"{stack['name']} {stack['version']}")
    how = sections.get("instructions", "")
    if worker and include_tools:
        how = f"{how}\n{FILES_LINE}"
    parts = [
        f"# Role\n{sections.get('role', '')}",
        f"# Goal and definition of done\n{sections.get('goal', '')}",
        f"# How to work\n{how}",
        f"# Constraints\n{sections.get('constraints', '')}",
        f"# Output\n{sections.get('output', '')}",
        "\n".join(
            [
                "# Enabled stacks",
                *stack_lines,
                "Do not use or propose any other framework. If the task requires one, call raise_clarification.",
            ]
        ),
    ]
    if include_tools:
        parts.append("\n".join(["# Tools", *tool_lines]))
    parts.append("\n".join(["# Skills", *skill_lines, "Call load_skill(name) before using a skill."]))
    parts.append(scope_block(scope))
    compiled = "\n\n".join(parts)
    return {"compiled": compiled, "tokenCount": token_count(compiled, model)}
