import requests

class AIModelManager:
    def __init__(self, local_endpoint="http://localhost:8000/llm", cloud_endpoint="https://api.openai.com/v1/completions", cloud_api_key=None):
        self.local_endpoint = local_endpoint
        self.cloud_endpoint = cloud_endpoint
        self.cloud_api_key = cloud_api_key

    def generate(self, prompt, **kwargs):
        # Try local LLM first
        try:
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
                "model": kwargs.get("model", "gpt-3.5-turbo"),
                "prompt": prompt,
                "max_tokens": kwargs.get("max_tokens", 128),
                # Add other supported cloud LLM parameters here if needed
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