import os
import requests

class OllamaModel:
    def __init__(self, base_url: str = None):
        self.base = base_url or os.getenv("OLLAMA_URL")

    def ask(self, prompt: str, model: str = "mistral") -> str:
        """Send prompt to Ollama HTTP API. This is a lightweight placeholder."""
        if not self.base:
            return "No Ollama URL configured"
        url = f"{self.base}/api/generate"
        payload = {"model": model, "prompt": prompt}
        try:
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                return r.text
            return f"Model error: {r.status_code}"
        except Exception as e:
            return f"Exception: {e}"
