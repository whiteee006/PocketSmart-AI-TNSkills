import json
import os
from pathlib import Path
from typing import Any

try:
    from google import genai
except ImportError:
    genai = None


def _client():
    key = os.getenv("GEMINI_API_KEY")
    if not key or genai is None:
        return None
    return genai.Client(api_key=key)


def _clean_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except Exception:
        return None


async def generate_json(prompt: str, image_path: str | None = None):
    client = _client()
    if not client:
        return None

    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    contents = [prompt]

    if image_path and Path(image_path).exists():
        from google.genai import types
        contents.append(types.Part.from_bytes(
            data=Path(image_path).read_bytes(),
            mime_type=_mime(image_path)
        ))

    response = client.models.generate_content(model=model, contents=contents)
    return _clean_json(response.text or "")


def _mime(path):
    suffix = Path(path).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "image/jpeg")
