import logging
from typing import Optional
import requests
import re

from config.settings import LLM, AGENT
from modules.agent_tools import build_default_registery, ToolResult

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5 # prevent infinite loops

class AgentRunner:
    def __init__(self, memory_ref: None):
        self._host = LLM["ollama_host"]
        self._model = LLM["model"]
        self._registery = build_default_registery()
        self._memory = memory_ref # injected so reminder tool can write DB

    @property
    def tools(self) -> list[dict]:
        return self._registery.all_schemas()

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
    
    def _build_messages(
            self,
            user_input: str,
            system_prompt: str,
            history: list[dict],
    ) -> list[dict]:
        msgs = [{"role": "system", "content": system_prompt}]
        cap = LLM["context_messages"]
        msgs.extend(history[-cap:])
        msgs.append({"role": "user", "content": user_input})

        return msgs

    def _call_ollama(
            self,
            messages: list[dict],
            tools: bool = True,
    ) -> Optional[dict]:
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": LLM["temperature"],
                "num_predict": LLM["max_tokens"],
            }
        }

        if tools:
            payload["tools"] = self.tools

        try:
            r = requests.post(
                f"{self._host}/api/chat",
                json=payload,
                timeout=LLM["timeout_seconds"],
            )
            r.raise_for_status()
            return r.json().get("message", {})
        except Exception as e:
            log.error(f"[Agent] Ollama call failed: {e}")
            return None

    _GESTURE_PATTERN = re.compile(r"\[GESTURE:(\w+)\]", re.IGNORECASE)

    def _extract(self, text: str) -> tuple[str, list[str]]:
        """Strip gesture tags, return (clean_text, gestures)."""
        gestures = self._GESTURE_PATTERN.findall(text)
        clean    = self._GESTURE_PATTERN.sub("", text).strip()
        return clean, [g.lower() for g in gestures]
    
    def _needs_confirmation(self, tool_name: str, args: dict, active_user: str) -> bool:
        log.info(f"[Agent] Auto-confirming {tool_name} for {active_user}")
        return True 

    def run(
            self,
            user_input: str,
            system_prompt: str,
            history: list[dict],
            emotion: str = "neutral",
            active_user: str = "Guest",
    ) -> tuple[str, list[str]]:
        messages = self._build_messages(user_input, system_prompt, history)

        for round_num in range(MAX_TOOL_ROUNDS):
            response = self._call_ollama(messages)
            if response is None:
                break

            # Check if model wants to call a tool
            tool_calls = response.get("tool_calls") or []

            if not tool_calls:
                content = response.get("content", "")
                return self._extract(content)
            
            # Execute all tool calls
            # Add assistant message with tool_calls to history
            messages.append({"role": "assistant", "content": None, "tool_cals": tool_calls})

            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", {})

                # Confirmation guard for destructive tools
                if name in AGENT.get("confirm_before", []):
                    confirmed = self._needs_confirmation(name, args, active_user)
                    if not confirmed:
                        messages.append({
                            "role": "tool",
                            "content": "User cancelled this action",
                            "name": name,
                        })
                        continue

                result: ToolResult = self._registery.call(name, args)

                # Feed tool result back to conversation
                messages.append({
                    "role": "tool",
                    "content": result.output,
                    "name": name
                })

            log.debug(f"[Agent] Round {round_num + 1} done, continuing...")

        # Ran out of rounds - ask for final summary
        messages.append({
            "role": "user",
            "content": "Please summarize what you found and give me a final answer."
        })
        final = self._call_ollama(messages, tools=False)
        if final:
            return self._extract(final.get("content", ""))
        
        return "I ran into some trouble finind that. Try again?", []