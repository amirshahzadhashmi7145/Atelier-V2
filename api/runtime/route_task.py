"""Assign a task to an agent. A rule engine or a team lead can replace this function later."""


def route_task(project: dict, task: dict) -> dict:
    members = project.get("members") or []
    if len(members) == 1:
        task["assignedAgentId"] = members[0]
        task["routedBy"] = "user"
        return task
    raise ValueError("routing needs exactly one project member until a rule engine exists")
