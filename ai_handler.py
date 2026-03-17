import requests
from urllib.parse import urlparse, urlunparse

class AIModelManager:
    def __init__(
        self,
        local_endpoint="http://localhost:8000/llm",
        local_provider="custom",  # "custom" or "ollama"
        local_model=None,
        cloud_endpoint="https://api.openai.com/v1/chat/completions",
        cloud_api_key=None,
    ):
        self.local_endpoint = local_endpoint
        self.local_provider = local_provider
        self.local_model = local_model
        self.cloud_endpoint = cloud_endpoint
        self.cloud_api_key = cloud_api_key

    @staticmethod
    def _ollama_base_url(local_endpoint: str) -> str:
        """
        Accepts either a base URL like http://localhost:11434 or a full path like
        http://localhost:11434/api/generate and returns the base URL.
        """
        p = urlparse(local_endpoint)
        return urlunparse((p.scheme, p.netloc, "", "", "", ""))

    def list_local_models(self):
        """
        If using Ollama, return a list of available model names.
        Returns [] if unavailable.
        """
        if self.local_provider != "ollama":
            return []
        base = self._ollama_base_url(self.local_endpoint)
        try:
            resp = requests.get(f"{base}/api/tags", timeout=3)
            if resp.status_code != 200:
                return []
            data = resp.json() or {}
            models = data.get("models") or []
            names = []
            for m in models:
                name = m.get("name")
                if name:
                    names.append(name)
            return sorted(set(names))
        except Exception:
            return []

    def generate(self, prompt, **kwargs):
        # Try local LLM first
        try:
            if self.local_provider == "ollama":
                base = self._ollama_base_url(self.local_endpoint)
                model = kwargs.get("model") or self.local_model
                if not model:
                    raise RuntimeError("No local model selected for Ollama")
                local_payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                }
                # Map a few common knobs if provided
                if "temperature" in kwargs:
                    local_payload["options"] = {"temperature": kwargs["temperature"]}
                resp = requests.post(f"{base}/api/generate", json=local_payload, timeout=30)
                if resp.status_code == 200:
                    return {"source": "local", "result": resp.json()}
            else:
                local_payload = {"prompt": prompt}
                local_payload.update(kwargs)
                resp = requests.post(self.local_endpoint, json=local_payload, timeout=5)
                if resp.status_code == 200:
                    return {"source": "local", "result": resp.json()}
            # If there is a response but not 200, treat as failure and fall back
        except Exception as e:
            pass  # Fall back to cloud

        # Try cloud API
        if self.cloud_api_key:
            headers = {
                "Authorization": f"Bearer {self.cloud_api_key}",
                "Content-Type": "application/json"
            }
            cloud_payload = {
                "model": kwargs.get("model", "gpt-4o-mini"),
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant that outputs strictly valid JSON when asked."},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": kwargs.get("max_tokens", 256),
                "temperature": kwargs.get("temperature", 0.2),
            }
            try:
                resp = requests.post(self.cloud_endpoint, headers=headers, json=cloud_payload, timeout=10)
                if resp.status_code == 200:
                    return {"source": "cloud", "result": resp.json()}
            except Exception as e:
                pass  # Prepare error below

        # If both failed
        return {
            "error": True,
            "message": "Both local and cloud AI models are unavailable.",
            "local_endpoint": self.local_endpoint,
            "cloud_endpoint": self.cloud_endpoint
        }