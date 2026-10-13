"""The only module the HTTP routes use to reach the runtime and the model gateway."""

from gateway import openai_gateway
from runtime import compile as compiler
from runtime import evals, loop, route_task as routing, sandbox, tools
from app.worker import start_run

__all__ = ["compare_evals", "compile_prompt", "list_model_ids", "local_mode", "route_task", "run_evals", "start_run", "stop_preview", "wake"]


def compile_prompt(sections, tool_ids, skill_ids, stack_ids, model: str = "gpt-4o"):
    return compiler.compile_prompt(sections, tool_ids, skill_ids, stack_ids, model)


def run_evals(agent: dict, version: dict) -> dict:
    return evals.run_version(agent, version)


def compare_evals(agent: dict, version: dict, models: list[str]) -> dict:
    return evals.compare_models(agent, version, models)


def wake(run_id: str) -> None:
    loop.wake(run_id)


def route_task(project: dict, task: dict) -> dict:
    return routing.route_task(project, task)


def local_mode() -> bool:
    return sandbox.local_mode()


def stop_preview(project_id: str) -> None:
    tools.stop_preview(project_id)


def list_model_ids() -> list[str]:
    return openai_gateway.list_model_ids()
