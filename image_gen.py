"""Image generation via Pollinations AI, kept separate from the Chainlit UI.

Pollinations is free and open source, and needs no API key: an image is just a
GET request to a URL containing the prompt. That is why this project uses it
rather than a paid image API, and it is also why the app deploys with no
secrets at all.

    https://image.pollinations.ai/prompt/<prompt>?width=..&height=..&seed=..

Isolating this from the UI means it can be tested without a browser or a
running Chainlit server.

A note on what is real, verified against the live service rather than assumed:
the width, height and seed parameters genuinely change the output, and the same
seed reproduces the same image. The `model` parameter currently does not: every
value, including nonsense ones, returns byte-identical images, so this module
deliberately does not pretend to offer a model choice.
"""

from __future__ import annotations

import random
import time
import urllib.parse
from dataclasses import dataclass

import httpx

ENDPOINT = "https://image.pollinations.ai/prompt/"

# Label -> (width, height). Pollinations takes pixel dimensions, not a ratio.
SIZES: dict[str, tuple[int, int]] = {
    "Square (1:1)": (1024, 1024),
    "Landscape (16:9)": (1280, 720),
    "Portrait (9:16)": (720, 1280),
    "Classic (4:3)": (1024, 768),
    "Tall (3:4)": (768, 1024),
}
DEFAULT_SIZE = "Square (1:1)"

STYLES = [
    "None",
    "Photorealistic",
    "Cinematic",
    "Watercolour",
    "Oil painting",
    "Line art",
    "Low poly 3D",
    "Pixel art",
    "Neon synthwave",
]

# Large images can take the best part of a minute, so the timeout is generous.
TIMEOUT_SECONDS = 180
_RETRY_STATUSES = (429, 500, 502, 503, 504)


class ImageGenError(RuntimeError):
    """Raised with a message intended to be shown to the user."""


@dataclass
class Generated:
    """One generation result."""

    image: bytes
    mime_type: str
    prompt: str
    size_label: str
    style: str
    seed: int
    seconds: float


def build_prompt(prompt: str, style: str) -> str:
    """Fold the chosen style into the prompt text.

    Pollinations takes artistic direction in the prompt itself, so style is
    expressed as words rather than as a separate parameter.
    """
    prompt = prompt.strip()
    if style and style != "None":
        return f"{prompt}, {style.lower()} style"
    return prompt


def build_url(prompt: str, width: int, height: int, seed: int) -> str:
    """The full request URL. Split out so tests can assert on it cheaply."""
    query = urllib.parse.urlencode(
        {"width": width, "height": height, "seed": seed, "nologo": "true"}
    )
    return f"{ENDPOINT}{urllib.parse.quote(prompt)}?{query}"


class ImageGenerator:
    """Generates images. `client` is injectable so tests need no network."""

    def __init__(self, client: httpx.Client | None = None):
        self._client = client

    def _get(self, url: str) -> httpx.Response:
        if self._client is not None:
            return self._client.get(url)
        with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
            return client.get(url)

    def generate(
        self,
        prompt: str,
        size_label: str = DEFAULT_SIZE,
        style: str = "None",
        seed: int | None = None,
        attempts: int = 3,
    ) -> Generated:
        if not prompt.strip():
            raise ImageGenError("Describe the image you would like first.")

        width, height = SIZES.get(size_label, SIZES[DEFAULT_SIZE])
        if seed is None:
            seed = random.randint(1, 1_000_000)

        full_prompt = build_prompt(prompt, style)
        url = build_url(full_prompt, width, height, seed)
        started = time.perf_counter()

        last_status: int | None = None
        for attempt in range(attempts):
            try:
                response = self._get(url)
            except httpx.TimeoutException:
                if attempt == attempts - 1:
                    raise ImageGenError(
                        "Pollinations took too long to respond. Try a smaller size, "
                        "or try again in a moment."
                    ) from None
                time.sleep(2**attempt)
                continue
            except httpx.HTTPError as exc:
                raise ImageGenError(f"Could not reach Pollinations: {exc}") from None

            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("image"):
                    raise ImageGenError(
                        "Pollinations returned something that was not an image. "
                        "Try rewording the prompt."
                    )
                return Generated(
                    image=response.content,
                    mime_type=content_type.split(";")[0] or "image/jpeg",
                    prompt=prompt.strip(),
                    size_label=size_label,
                    style=style,
                    seed=seed,
                    seconds=round(time.perf_counter() - started, 1),
                )

            last_status = response.status_code
            if response.status_code not in _RETRY_STATUSES or attempt == attempts - 1:
                break
            time.sleep(2**attempt)

        if last_status == 429:
            raise ImageGenError(
                "Pollinations is rate limiting requests right now. Wait a few "
                "seconds and try again."
            )
        raise ImageGenError(f"Pollinations returned HTTP {last_status}. Try again shortly.")
