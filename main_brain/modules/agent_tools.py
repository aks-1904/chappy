import logging
from dataclasses import dataclass
from typing import Callable, Any, Optional
import requests
from html.parser import HTMLParser
import re
import time
from datetime import datetime
import urllib.parse
import math

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
    try:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1,
        }
        r= requests.get(url, params=params, timeout=8)
        data = r.json()

        results = []

        # Abstract (best single answer)
        if data.get("AbstractText"):
            results.append(f"Summary: {data['AbstractText']}")

        # Answer
        if data.get("Answer"):
            results.append(f"Answer: {data['Answer']}")

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"- {topic['Text'][:200]}")

        if results:
            return ToolResult(
                success=True,
                output=f"Web search results for '{query}':\n" + "\n".join(results),
                data=data,
            )
        
        # FallBack
        lite_url = "https://lite.duckduckgo.com/lite/"
        lite_r = requests.get(
            lite_url,
            params={"q": query},
            headers={"User-Agent": "CompanionRobot/1.0"},
            timeout=8,
        )
        # Parse plain text snippets from lite HTML
        class _SnippetParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.snippets = []
                self._in_result = False

            def handle_data(self, data):
                t = data.strip()
                if len(t) > 40:
                    self.snippets.append(t)

        parser = _SnippetParser()
        parser.feed(lite_r.text)
        snippets = [s for s in parser.snippets if len(s) > 40][:max_results]

        if snippets:
            return ToolResult(
                success=True,
                output=f"Web search for '{query}':\n" + "\n".join(f"• {s}" for s in snippets),
            )

        return ToolResult(False, f"No results found for '{query}'")
    
    except Exception as e:
        return ToolResult(False, f"Web search failed: {e}")

def _parse_when(when: str) -> Optional[float]:
    now = time.time()
    w = when.lower().strip()

    # "in N minutes/hours"
    m = re.search(r"in\s+(\d+)\s+(minute|hour|second)", w)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        mult = {"second": 1, "minute": 60, "hour": 3600}[unit]
        return now + n * mult
    
    # "at HH:MM" or "at H PM"
    m = re.search(r"at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", w)
    if m:
        h, mn, meridiem = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if meridiem == "pm" and h != 12:
            h += 12
        elif meridiem == "am" and h == 12:
            h = 0
        dt = datetime.now().replace(hour=h, minute=mn, second=0, microsecond=0)
        ts = dt.timestamp()
        if ts < now:
            ts += 86400   # next day
        return ts
    
    # Plain numbers: "30 minutes"
    m = re.search(r"(\d+)\s*(minute|hour|second)", w)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        mult = {"second": 1, "minute": 60, "hour": 3600}[unit]
        return now + n * mult

    return None

def _set_reminder_tool(
        person: str,
        text: str,
        when: str,
        memory_ref = None, # Injected by AgentRunner
) -> ToolResult:
    due_time = _parse_when(when)
    if due_time is None:
        return ToolResult(False, f"Could not understand time: '{when}'. Try '30 minutes' or '8 PM'.")
    if memory_ref:
        memory_ref.add_reminder(person, text, due_time)
        readable = datetime.fromtimestamp(due_time).strftime("%I:%M %p")
        return ToolResult(
            success=True,
            output=f"Reminder set for {person} at {readable}: {text}",
        )
    return ToolResult(False, "Reminder system unavailable.")

def _wikipedia_lookup(topic: str) -> ToolResult:
    try:
        encoded = urllib.parse.quote(topic.replace(" ", "_"))
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        r = requests.get(url, timeout=8,
                         headers={"User-Agent": "CompanionRobot/1.0"})
        if r.status_code == 200:
            data = r.json()
            extract = data.get("extract", "")
            title   = data.get("title", topic)
            if extract:
                # Keep first 3 sentences
                sentences = extract.split(". ")[:3]
                summary = ". ".join(sentences).strip()
                return ToolResult(
                    success=True,
                    output=f"{title}: {summary}",
                    data=data,
                )
        return ToolResult(False, f"Wikipedia page not found for '{topic}'")
    except Exception as e:
        return ToolResult(False, f"Wikipedia error: {e}")

def _calculate(expression: str) -> ToolResult:
    """Safely evaluate a math expression."""
    # Whitelist: only safe math operations
    allowed = set("0123456789+-*/().%, ")
    allowed.update(["*", "/", "//", "**"])
    clean = expression.replace("^", "**")   # ^ → ** for power

    # Allow math functions by replacing names
    safe_names = {
        "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "abs": abs, "round": round, "pi": math.pi, "e": math.e,
        "pow": pow, "floor": math.floor, "ceil": math.ceil,
    }
    try:
        result = eval(clean, {"__builtins__": {}}, safe_names)   # noqa: S307
        return ToolResult(
            success=True,
            output=f"{expression} = {result}",
            data=result,
        )
    except Exception as e:
        return ToolResult(False, f"Could not calculate '{expression}': {e}")
    
def _get_time_date(timezone: str = "local") -> ToolResult:
    now = datetime.now()
    result = now.strftime("Today is %A, %B %d %Y. The time is %I:%M %p.")
    return ToolResult(success=True, output=result, data=now.isoformat())

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

REMINDER_TOOL = ToolDefinition(
    name="set_reminder",
    description=(
        "Set a reminder for a person at a specific time. "
        "Use when someone says 'remind me to X in Y minutes' or 'remind me at Z'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "person": {"type": "string",  "description": "Name of person to remind"},
            "text":   {"type": "string",  "description": "What to remind them about"},
            "when":   {"type": "string",  "description": "When, e.g. 'in 30 minutes', 'at 8 PM'"},
        },
        "required": ["person", "text", "when"],
    },
    fn=_set_reminder_tool,
)

WIKIPEDIA_TOOL = ToolDefinition(
    name="wikipedia_lookup",
    description=(
        "Look up factual information about a person, place, concept, or event "
        "from Wikipedia. Good for definitions, history, and general knowledge."
    ),
    parameters={
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Topic to look up"},
        },
        "required": ["topic"],
    },
    fn=_wikipedia_lookup,
)

CALCULATE_TOOL = ToolDefinition(
    name="calculate",
    description=(
        "Evaluate a mathematical expression. Supports +, -, *, /, **, sqrt(), "
        "sin(), cos(), log(), pi, e, etc."
    ),
    parameters={
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "Math expression, e.g. '2 * pi * 5'"},
        },
        "required": ["expression"],
    },
    fn=_calculate,
)

TIME_DATE_TOOL = ToolDefinition(
    name="get_time_date",
    description="Get the current date and time.",
    parameters={
        "type": "object",
        "properties": {
            "timezone": {"type": "string", "description": "Timezone (default: local)", "default": "local"},
        },
    },
    fn=_get_time_date,
)

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        self._tools[tool.name] = tool
        log.debug(f"[Tools] Registered: {tool.name}")

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def all_schemas(self) -> list[dict]:
        return [t.to_ollama_schema() for t in self._tools.values()]
    
    def call(self, name: str, arguments: dict) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(False, f"Unkown tool: {name}")
        try:
            log.info(f"[Tools] Calling {name}({arguments})")
            result = tool.fn(**arguments)
            log.info(f"[Tools] {name} -> {result.output[:80]}...")
            return result
        except Exception as e:
            log.error(f"[Tools] {name} error: {e}")
            return ToolResult(False, f"Tool error: {e}")

def build_default_registery() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(WEB_SEARCH_TOOL)
    registry.register(REMINDER_TOOL)
    registry.register(WIKIPEDIA_TOOL)
    registry.register(CALCULATE_TOOL)
    registry.register(TIME_DATE_TOOL)

    return registry