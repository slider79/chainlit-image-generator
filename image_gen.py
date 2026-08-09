"""Gemini image generation, kept separate from the Chainlit UI.

Isolating this means the generation logic can be tested without a browser or a
running Chainlit server, and the UI file stays about the UI.

Gemini's image models return their result as inline binary data on a response
part, alongside any text the model wrote, so a response is parsed into both.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

# Free-tier friendly models, fastest first. The label is what the UI shows.
MODELS: dict[str, str] = {
    "gemini-2.5-flash-image": "Flash Image 2.5 (fast, stable)",
    "gemini-3.1-flash-image": "Flash Image 3.1 (newer)",
    "gemini-3-pro-image": "Pro Image 3 (highest quality, slower)",
}
DEFAULT_MODEL = "gemini-2.5-flash-image"

ASPECT_RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4"]
DEFAULT_ASPECT = "1:1"

# Rate limiting is the failure to expect on a free key, so retry it.
_RETRYABLE = (429, 500, 502, 503, 504)


class ImageGenError(RuntimeError):
    """Raised with a message intended to be shown to the user."""


@dataclass
class Generated:
    """One generation result: the image bytes plus anything the model said."""

    image: bytes | None = None
    mime_type: str = "image/png"
    text: str = ""
    model: str = DEFAULT_MODEL
    seconds: float = 0.0
    prompt: str = ""
    notes: list[str] = field(default_factory=list)


def _redact(text: str) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if key and len(key) >= 8:
        text = text.replace(key, "[redacted]")
    return text


def _build_prompt(prompt: str, aspect: str, style: str) -> str:
    """Fold the UI settings into the prompt.

    The image models take direction in plain language rather than separate
    parameters, so aspect ratio and style are expressed as instructions.
    """
    parts = [prompt.strip()]
    if style and style != "None":
        parts.append(f"Style: {style}.")
    if aspect and aspect != "1:1":
        parts.append(f"Compose it with a {aspect} aspect ratio.")
    return " ".join(p for p in parts if p)


class ImageGenerator:
    def __init__(self, api_key: str | None = None, client=None):
        if client is not None:
            self.client = client
            return
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ImageGenError(
                "GEMINI_API_KEY is not set. Add it to a .env file or your environment."
            )
        try:
            from google import genai

            self.client = genai.Client(api_key=key)
        except ImportError as exc:  # pragma: no cover
            raise ImageGenError("google-genai is not installed. Run: pip install google-genai") from exc

    def generate(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        aspect: str = DEFAULT_ASPECT,
        style: str = "None",
        attempts: int = 3,
    ) -> Generated:
        if not prompt.strip():
            raise ImageGenError("Describe the image you would like first.")

        full_prompt = _build_prompt(prompt, aspect, style)
        started = time.perf_counter()

        for attempt in range(attempts):
            try:
                response = self.client.models.generate_content(model=model, contents=full_prompt)
                break
            except Exception as exc:  # noqa: BLE001
                code = getattr(exc, "code", None)
                if code not in _RETRYABLE or attempt == attempts - 1:
                    if code == 429:
                        raise ImageGenError(
                            "Gemini's free tier is rate limited right now. Wait a minute "
                            "and try again, or switch model in the settings panel."
                        ) from None
                    raise ImageGenError(f"Generation failed: {_redact(str(exc))}") from None
                time.sleep(2**attempt)

        result = Generated(
            model=model, seconds=round(time.perf_counter() - started, 1), prompt=prompt.strip()
        )
        self._collect(response, result)

        if result.image is None:
            raise ImageGenError(
                "The model replied without an image. That usually means the prompt was "
                "refused or misread; try rewording it."
                + (f' It said: "{result.text[:180]}"' if result.text else "")
            )
        return result

    @staticmethod
    def _collect(response, result: Generated) -> None:
        """Pull image bytes and text out of a response, tolerating odd shapes."""
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return
        content = getattr(candidates[0], "content", None)
        for part in (getattr(content, "parts", None) or []):
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                result.image = inline.data
                result.mime_type = getattr(inline, "mime_type", None) or "image/png"
            elif getattr(part, "text", None):
                result.text += part.text
