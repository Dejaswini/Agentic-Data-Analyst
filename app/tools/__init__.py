"""Tool registry for the multi-agent data analyst.

Each tool is a callable with metadata (name, description, category).
Agents pick tools dynamically based on the question.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Tool:
    """A registered tool that agents can invoke."""

    name: str
    description: str
    func: Callable[..., dict[str, Any]]
    category: str = "general"
    parameters: dict[str, str] = field(default_factory=dict)


class ToolRegistry:
    """Central registry of all available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        category: str = "general",
        parameters: dict[str, str] | None = None,
    ):
        """Decorator to register a function as a tool."""

        def decorator(func: Callable) -> Callable:
            self._tools[name] = Tool(
                name=name,
                description=description,
                func=func,
                category=category,
                parameters=parameters or {},
            )
            return func

        return decorator

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    def call(self, name: str, **kwargs) -> dict[str, Any]:
        """Call a tool by name."""
        tool = self.get(name)
        return tool.func(**kwargs)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def describe_all(self) -> str:
        """Human-readable tool descriptions for LLM prompts."""
        lines = []
        for t in self._tools.values():
            params = ", ".join(f"{k}: {v}" for k, v in t.parameters.items())
            lines.append(f"- {t.name}({params}): {t.description}")
        return "\n".join(lines)


# Global registry — tools register themselves on import.
registry = ToolRegistry()
