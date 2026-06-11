import logging
from dataclasses import dataclass
from typing import Callable, Any

log = logging.getLogger(__name__)

@dataclass
class ToolResult:
    success: bool
    output: str # Human readable result for the LLM
    data: Any = None # Raw structured data

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict # JSON Schema for parameters
    fn: Callable[..., ToolResult]

    def to_ollama_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name":        self.name,
                "description": self.description,
                "parameters":  self.parameters,
            },
        }
    
def _web_search(query, max_results: int = 4) -> ToolResult:
    pass

WEB_SEARCH_TOOL = ToolDefinition(
    name="web_search",
    description=(
        "Search the internet for current information, news, facts, or any topic. "
        "Use this when you need up-to-date information or facts you're unsure about."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query":       {"type": "string",  "description": "The search query"},
            "max_results": {"type": "integer", "description": "Number of results (1-5)", "default": 3},
        },
        "required": ["query"],
    },
    fn=_web_search,
)

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        self._tools[tool.name] = tool
        log.debug(f"[Tools] Registered: {tool.name}")

def build_default_registery() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(WEB_SEARCH_TOOL)

    return registry