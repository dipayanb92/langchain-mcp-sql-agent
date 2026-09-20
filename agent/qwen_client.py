"""
Thin wrapper around a local Ollama server running a Qwen model.
No LangChain / heavy framework — just plain HTTP so every step the
agent takes is easy to see and debug.
"""
from dataclasses import dataclass

import requests


class OllamaConnectionError(RuntimeError):
    pass


@dataclass
class QwenClient:
    model: str = "qwen3:8b"
    host: str = "http://localhost:11434"
    temperature: float = 0.1

    def _url(self, path: str) -> str:
        return f"{self.host.rstrip('/')}{path}"

    def is_available(self) -> tuple[bool, str]:
        try:
            resp = requests.get(self._url("/api/tags"), timeout=5)
            resp.raise_for_status()
            tags = [m["name"] for m in resp.json().get("models", [])]
            if not any(self.model.split(":")[0] in t for t in tags):
                return False, (
                    f"Ollama is running but model '{self.model}' isn't pulled yet. "
                    f"Run: ollama pull {self.model}"
                )
            return True, "ok"
        except requests.exceptions.RequestException as exc:
            return False, (
                f"Can't reach Ollama at {self.host} ({exc}). "
                f"Start it with 'ollama serve' (or open the Ollama app) and make sure "
                f"'{self.model}' is pulled."
            )

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": self.temperature},
            # Qwen3 is a hybrid-reasoning model and emits <think>...</think>
            # by default. We want clean SQL/JSON out, not a reasoning trace,
            # so turn thinking off. Ollama (>=0.9) ignores this for models
            # that don't support it, so it's safe to always send.
            "think": False,
        }
        if json_mode:
            payload["format"] = "json"

        try:
            resp = requests.post(self._url("/api/chat"), json=payload, timeout=120)
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise OllamaConnectionError(str(exc)) from exc

        data = resp.json()
        return data.get("message", {}).get("content", "").strip()
