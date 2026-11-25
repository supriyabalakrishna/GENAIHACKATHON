import json
import requests
from pydantic import BaseModel
from config.settings import settings

class OllamaError(RuntimeError):
    pass

def health() -> tuple[bool, str]:
    try:
        r = requests.get(f"{settings.ollama_host}/api/tags", timeout=3)
        r.raise_for_status()
        names = {m["name"] for m in r.json().get("models", [])}
        installed_bases = {name.split(":")[0] for name in names}
        missing = [
            model for model in ("qwen2.5:3b", "nomic-embed-text")
            if model not in names and model.split(":")[0] not in installed_bases
        ]
        if missing:
            return False, "Missing Ollama models: " + ", ".join(
                f"{model} (ollama pull {model})" for model in missing
            )
        return True, "Ollama ready"
    except Exception as exc:
        return False, f"Ollama unavailable: {exc}"

def ensure_models() -> None:
    r = requests.get(f"{settings.ollama_host}/api/tags", timeout=5)
    r.raise_for_status()
    names = {m["name"] for m in r.json().get("models", [])}
    for model in ("qwen2.5:3b", "nomic-embed-text"):
        if model not in names and model.split(":")[0] not in {n.split(":")[0] for n in names}:
            raise OllamaError(f"Missing model {model}. Run: ollama pull {model}")

def generate(system: str, prompt: str, schema: type[BaseModel]) -> BaseModel:
    output_schema = schema.model_json_schema()
    repair_prompt = prompt
    last_error = None
    payload = {
        "model": "qwen2.5:3b",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": repair_prompt}],
        "stream": False,
        "format": output_schema,
        "options": {"temperature": 0, "seed": 42},
    }
    for attempt in range(2):
        content = ""
        try:
            r = requests.post(f"{settings.ollama_host}/api/chat", json=payload, timeout=(10, 180))
            r.raise_for_status()
            content = r.json()["message"]["content"]
            result = schema.model_validate(json.loads(content))
            return result
        except requests.RequestException as exc:
            last_error = exc
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            last_error = exc
            if attempt == 0:
                repair_prompt = (
                    f"{prompt}\n\nYour previous response did not match the required output schema. "
                    f"Validation error: {exc}\nPrevious response: {content}\n"
                    "Return the complete corrected JSON object, not an individual list item."
                )
                payload["messages"] = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": repair_prompt},
                ]
    raise OllamaError(f"Model inference failed or returned invalid JSON after one retry: {last_error}") from last_error

def embed_many(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    try:
        r = requests.post(
            f"{settings.ollama_host}/api/embed",
            json={"model": "nomic-embed-text", "input": texts},
            timeout=(10, 300),
        )
        r.raise_for_status()
        embeddings = r.json().get("embeddings")
        if not embeddings or len(embeddings) != len(texts):
            raise OllamaError("Embedding service returned an unexpected number of vectors")
        return embeddings
    except requests.RequestException as exc:
        raise OllamaError(
            f"Embedding timed out or failed. Check that Ollama is running and "
            f"'nomic-embed-text' is available, then re-index. Details: {exc}"
        ) from exc

def embed(text: str) -> list[float]:
    return embed_many([text])[0]
