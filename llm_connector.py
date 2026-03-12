import json
from urllib import request


class OllamaConnector:
    # Connects to local Ollama API for text generation

    def __init__(self, base_url="http://localhost:11434/api/generate", model="tinyllama", timeout_seconds=60):
        self.base_url = base_url
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate(self, prompt, model=None):
        # Send sanitized prompt to Ollama and return the response
        payload = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")

        req = request.Request(
            url=self.base_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with request.urlopen(req, timeout=self.timeout_seconds) as response:
            raw = response.read()

        parsed = json.loads(raw.decode("utf-8"))
        return str(parsed.get("response", ""))
