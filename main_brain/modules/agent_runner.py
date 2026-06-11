import logging

from config.settings import LLM
from modules.agent_tools import build_default_registery

log = logging.getLogger(__name__)

class AgentRunner:
    def __init__(self, memory_ref: None):
        self._host = LLM["ollama_host"]
        self._model = LLM["model"]
        self._registery = build_default_registery()
        self._memory = memory_ref # injected so reminder tool can write DB

    def needs_tools(self, user_input: str) -> bool:
        triggers = [
            "search", "look up", "find", "google", "what is", "who is",
            "weather", "temperature", "rain", "forecast",
            "news", "headlines", "latest",
            "email", "send", "mail", "message to",
            "remind", "reminder", "remind me",
            "calculate", "what is", "how much", "convert",
            "joke", "funny", "make me laugh",
            "time", "date", "day", "today",
            "wikipedia",
        ]
        low = user_input.lower()
        return any(t in low for t in triggers)

    def run(
            self,
            user_input: str,
            system_prompt: str,
            history: list[dict],
            emotion: str = "neutral",
            active_user: str = "Guest",
    ) -> tuple[str, list[str]]:
        pass
