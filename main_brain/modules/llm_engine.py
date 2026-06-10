import logging
import re
import requests
from typing import Generator
import json

from config.settings import LLM

log = logging.getLogger(__name__)

_GESTURE_PATTERN = re.compile(r"\[FESTURE:(\w+)\]", re.IGNORECASE)

class LLMEngine:
    def __init__(self):
        self._host = LLM["ollama_host"]
        self._model = LLM["model"]
        self._available = self._check_ollama()

    def _check_ollama(self) -> bool:
        try:
            r = requests.get(f"{self._host}/api/tags", timeout=3)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                log.info(f"[LLM] Ollama up. Models: {models}")

                if not any(self._model in m for m in models):
                    log.warning(
                        f"[LLM] Model '{self._model}' not found. "
                        f"Run: ollama pull {self._model}"
                    )

                return True
            
        except Exception as e:
            log.warning(f"[LLM] Ollama not reachable: {e}")
        return False
    
    @property
    def available(self) -> bool:
        return self._available
    
    _FALLBACKS = [
        "I'm thinking, but my brain needs a moment to warm up.",
        "That's a great question. Let me think about it.",
        "I heard you. Give me just a second.",
        "Interesting! I'm processing that.",
        "I'm here. My AI mind is just loading.",
    ]
    _fallback_idx = 0
    
    def _fallback(self, messages: list[dict]) -> str:
        last_user = ""
        for m in reversed(messages):
            if m["role"] == "user":
                last_user = m["content"].lower()
                break

        # Simple keyword fallbacks
        if any(w in last_user for w in ["hello", "hi", "hey"]):
            return "Hello! Great to see you. [GESTURE:wave]"
        if any(w in last_user for w in ["bye", "goodbye", "see you"]):
            return "Goodbye! Take care. [GESTURE:wave]"
        if any(w in last_user for w in ["how are you", "are you okay"]):
            return "I'm doing well, thank you for asking! [GESTURE:nod]"

        msg = self._FALLBACKS[self._fallback_idx % len(self._FALLBACKS)]
        self._fallback_idx += 1
        return msg
    
    @staticmethod
    def extract_gesture(text: str) -> tuple[str, list[str]]:
        gestures = _GESTURE_PATTERN.findall(text)
        clean = _GESTURE_PATTERN.sub("", text).strip()

        return clean, [g.lower() for g in gestures]

    def generate_response(
            self,
            user_input: str,
            memory_context: str = "",
            emotion: str = "neutral",
            history: list = None
    ) -> tuple[str, list[str]]:
        messages = self._build_messages(
            user_input, memory_context, emotion, history or []
        )
        raw = self.chat(messages)
        return self.extract_gesture(raw)
    
    def chat_stream(self, messages: list[dict]) -> Generator[str, None, None]:
        if not self._available:
            yield self._fallback(messages)
            return
        
        try:
            resp = requests.post(
                f"{self._host}/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": LLM["temperature"],
                        "num_predict": LLM["max_tokens"],
                    },
                },
                timeout=LLM["timeout_seconds"],
                stream=True,
            )
            resp.raise_for_status()

            for line in resp.iter_lines():
                if line:
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break
        except Exception as e:
            log.error(f"[LLM] Stream error: {e}")
            yield self._fallback(messages)
    
    def chat(self, messages: list[dict]) -> str:
        return "".join(self.chat_stream(messages))

    def _build_messages(
            self,
            user_input: str,
            memory_context: str,
            emotion: str,
            history: list[dict],
    ) -> list[dict]:
        system_content = LLM["system_prompt"]
        if memory_context:
            system_content += f"\n\n--- User Context ---\n{memory_context}"
        if emotion and emotion != "neutral":
            system_content += (
                f"\n\nThe user appears emotionally {emotion}. "
                f"Respond with empathy and adjust your tone accordingly."
            )
        
        messages = [{"role": "system", "content": system_content}]

        # Include recent history (cap at context_messages)
        cap = LLM["content_messages"]
        if len(history) > cap:
            history = history[-cap:]
        messages.extend(history)

        messages.append({"role": "user", "content": user_input})
        return messages

