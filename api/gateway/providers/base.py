"""Provider protocol: gateway and runtime talk only through this surface."""

from __future__ import annotations

from typing import Iterator, Protocol, runtime_checkable


@runtime_checkable
class ModelProvider(Protocol):
    id: str

    def list_models(self) -> list[str]: ...

    def config_schema(self, model: str) -> dict: ...

    def pricing(self, model: str) -> dict | None: ...

    def complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        config: dict,
        *,
        stream: bool = True,
        tool_choice: str | None = None,
    ) -> Iterator[dict]: ...
