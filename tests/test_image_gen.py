"""Offline checks for the generation layer and the Chainlit wiring.

Run with:  python tests/test_image_gen.py

No network and no browser needed. The HTTP client is faked, so these cover the
real logic: URL and prompt construction from the settings, handling a successful
image, retrying transient failures, seed behaviour, and the errors a user would
actually see. The app module is imported to confirm every decorator registers.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from image_gen import (  # noqa: E402
    SIZES,
    ImageGenerator,
    ImageGenError,
    build_prompt,
    build_url,
)

failures: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        failures.append(label)


def image_response(status: int = 200, content: bytes = b"\xff\xd8\xffJPEG", ctype: str = "image/jpeg"):
    return httpx.Response(
        status_code=status,
        content=content,
        headers={"content-type": ctype},
        request=httpx.Request("GET", "https://image.pollinations.ai/"),
    )


class FakeClient:
    """Stands in for httpx.Client, recording the URLs it was asked for."""

    def __init__(self, responses=None, raises=None):
        self.urls: list[str] = []
        self._responses = list(responses or [image_response()])
        self._raises = list(raises or [])

    def get(self, url: str):
        self.urls.append(url)
        if self._raises:
            exc = self._raises.pop(0)
            if exc is not None:
                raise exc
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


# ---- prompt and URL construction -----------------------------------------


def test_prompt_building():
    print("\nStyle is folded into the prompt, and only when set")
    check(build_prompt("a cat", "None") == "a cat", "no suffix when style is None")
    check("watercolour style" in build_prompt("a cat", "Watercolour"), "style is appended")


def test_url_construction():
    print("\nThe request URL carries the size and seed")
    url = build_url("a red bike", 1280, 720, 4242)
    check(url.startswith("https://image.pollinations.ai/prompt/"), "hits the Pollinations endpoint")
    check("a%20red%20bike" in url, "the prompt is URL encoded")
    check("width=1280" in url and "height=720" in url, "dimensions are passed")
    check("seed=4242" in url, "the seed is passed")
    check("nologo=true" in url, "the watermark is disabled")


# ---- generation -----------------------------------------------------------


def test_generate_returns_image():
    print("\nA successful generation returns bytes plus metadata")
    client = FakeClient()
    result = ImageGenerator(client=client).generate(
        "a red bicycle", size_label="Landscape (16:9)", style="Cinematic", seed=7
    )
    check(result.image.startswith(b"\xff\xd8\xff"), "image bytes are returned")
    check(result.mime_type == "image/jpeg", "mime type is captured")
    check(result.prompt == "a red bicycle", "the user's wording is preserved")
    check(result.seed == 7, "the requested seed is recorded")
    check(result.size_label == "Landscape (16:9)", "the chosen size is recorded")
    width, height = SIZES["Landscape (16:9)"]
    check(f"width={width}" in client.urls[0], "the size maps to real dimensions")


def test_seed_is_random_when_unset():
    print("\nAn unspecified seed is chosen randomly, so repeats differ")
    gen = ImageGenerator(client=FakeClient())
    seeds = {gen.generate("a tree").seed for _ in range(5)}
    check(len(seeds) > 1, "successive generations use different seeds")


def test_empty_prompt_rejected():
    print("\nAn empty prompt is refused before any request")
    client = FakeClient()
    try:
        ImageGenerator(client=client).generate("   ")
        check(False, "should raise")
    except ImageGenError:
        check(client.urls == [], "no request is made")


def test_non_image_response_explained():
    print("\nA non-image response gives a useful message")
    client = FakeClient([image_response(ctype="text/html", content=b"<html>")])
    try:
        ImageGenerator(client=client).generate("something")
        check(False, "should raise")
    except ImageGenError as exc:
        check("not an image" in str(exc), "says it was not an image")


def test_transient_error_is_retried():
    print("\nA transient 503 is retried, then succeeds")
    import time as _t

    original = _t.sleep
    _t.sleep = lambda *_: None
    try:
        client = FakeClient([image_response(status=503), image_response()])
        result = ImageGenerator(client=client).generate("a fox")
        check(len(client.urls) == 2, "retried once before succeeding")
        check(result.image.startswith(b"\xff\xd8\xff"), "returns the image after recovery")

        limited = FakeClient([image_response(status=429)])
        try:
            ImageGenerator(client=limited).generate("a fox")
            check(False, "should give up eventually")
        except ImageGenError as exc:
            check("rate limiting" in str(exc).lower(), "explains the rate limit plainly")
    finally:
        _t.sleep = original


def test_timeout_is_explained():
    print("\nA timeout is reported in plain words")
    import time as _t

    original = _t.sleep
    _t.sleep = lambda *_: None
    try:
        client = FakeClient(raises=[httpx.TimeoutException("slow"), httpx.TimeoutException("slow"),
                                    httpx.TimeoutException("slow")])
        try:
            ImageGenerator(client=client).generate("a fox")
            check(False, "should raise")
        except ImageGenError as exc:
            check("too long" in str(exc), "suggests a smaller size or retry")
    finally:
        _t.sleep = original


# ---- chainlit wiring ------------------------------------------------------


def test_decorators_are_registered():
    print("\nEvery Chainlit decorator in app.py is registered")
    import chainlit as cl

    import app  # noqa: F401  importing runs the decorators

    cfg = cl.config.config.code
    for hook in ("on_chat_start", "on_message", "on_settings_update", "on_chat_end", "set_starters"):
        check(getattr(cfg, hook, None) is not None, f"@cl.{hook} is registered")
    check(len(cfg.action_callbacks) >= 2, "both action callbacks are registered")


def test_stylesheet_route_is_served_and_prioritised():
    print("\nThe stylesheet is served by its own route, ahead of the SPA catch-all")
    import app  # noqa: F401  registers the route
    import theme_route
    from chainlit.server import app as chainlit_app

    paths = [getattr(r, "path", None) for r in chainlit_app.routes]
    check(theme_route.CSS_ROUTE in paths, "the route is registered")
    check(paths.index(theme_route.CSS_ROUTE) == 0, "it sits ahead of the catch-all route")

    css = theme_route._CSS
    for label, needle in (
        ("aurora", "mirage-drift-a"),
        ("palette", "258 90% 66%"),
        ("display font", "Syncopate"),
        ("glassmorphism", "backdrop-filter"),
        ("reduced motion", "prefers-reduced-motion"),
        ("focus ring", "focus-visible"),
    ):
        check(needle in css, f"the stylesheet carries the {label}")


def test_no_fake_model_selector():
    print("\nThe UI does not offer a model choice that would do nothing")
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    check('id="model"' not in source, "no model selector is rendered")


if __name__ == "__main__":
    for test in (
        test_prompt_building,
        test_url_construction,
        test_generate_returns_image,
        test_seed_is_random_when_unset,
        test_empty_prompt_rejected,
        test_non_image_response_explained,
        test_transient_error_is_retried,
        test_timeout_is_explained,
        test_decorators_are_registered,
        test_stylesheet_route_is_served_and_prioritised,
        test_no_fake_model_selector,
    ):
        test()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All checks passed.")
