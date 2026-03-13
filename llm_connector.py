import requests


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

        response = requests.post(self.base_url, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        return str(response.json().get("response", ""))
