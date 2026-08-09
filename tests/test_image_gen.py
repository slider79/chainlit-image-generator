"""Offline checks for the generation layer and the Chainlit wiring.

Run with:  python tests/test_image_gen.py

No API key and no browser needed. The Gemini client is faked, so these cover the
real logic: prompt construction from the settings, parsing an image out of a
response, retrying a rate limit, and the errors a user would actually see. The
app module is imported to confirm every decorator is registered.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from image_gen import ImageGenerator, ImageGenError, _build_prompt  # noqa: E402

failures: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        failures.append(label)


def image_response(data: bytes = b"PNGDATA", text: str = ""):
    parts = [SimpleNamespace(inline_data=SimpleNamespace(data=data, mime_type="image/png"), text=None)]
    if text:
        parts.append(SimpleNamespace(inline_data=None, text=text))
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))])


def text_only_response(text: str):
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(inline_data=None, text=text)]))]
    )


class FakeModels:
    def __init__(self, response=None, fail_times: int = 0, code: int = 429):
        self.calls = 0
        self.last_prompt = ""
        self.last_model = ""
        self._response = response if response is not None else image_response()
        self._fail_times = fail_times
        self._code = code

    def generate_content(self, model, contents):
        self.calls += 1
        self.last_model = model
        self.last_prompt = contents
        if self.calls <= self._fail_times:
            exc = RuntimeError(f"{self._code} error")
            exc.code = self._code
            raise exc
        return self._response


def gen(models) -> ImageGenerator:
    return ImageGenerator(client=SimpleNamespace(models=models))


# ---- prompt construction --------------------------------------------------


def test_prompt_building():
    print("\nSettings are folded into the prompt")
    plain = _build_prompt("a cat", "1:1", "None")
    check(plain == "a cat", "no extras when settings are default")
    styled = _build_prompt("a cat", "16:9", "Watercolour")
    check("Watercolour" in styled, "style is included")
    check("16:9" in styled, "aspect ratio is included")


# ---- generation -----------------------------------------------------------


def test_generate_returns_image():
    print("\nA successful generation returns image bytes and metadata")
    models = FakeModels(image_response(b"IMG", text="Here you go."))
    result = gen(models).generate("a red bicycle", model="gemini-2.5-flash-image")
    check(result.image == b"IMG", "image bytes are extracted")
    check(result.mime_type == "image/png", "mime type is captured")
    check(result.text == "Here you go.", "accompanying text is captured")
    check(result.prompt == "a red bicycle", "original prompt is preserved")
    check(models.last_model == "gemini-2.5-flash-image", "the chosen model is used")
    check(result.seconds >= 0, "timing is recorded")


def test_empty_prompt_rejected():
    print("\nAn empty prompt is refused before any API call")
    models = FakeModels()
    try:
        gen(models).generate("   ")
        check(False, "should raise")
    except ImageGenError:
        check(models.calls == 0, "no API call is made")


def test_text_only_response_explains_itself():
    print("\nA reply with no image gives a useful message")
    models = FakeModels(text_only_response("I can't draw that."))
    try:
        gen(models).generate("something")
        check(False, "should raise")
    except ImageGenError as exc:
        check("without an image" in str(exc), "says no image came back")
        check("can't draw that" in str(exc), "quotes what the model said")


def test_rate_limit_is_retried():
    print("\nA 429 is retried, then succeeds")
    import time as _t

    original = _t.sleep
    _t.sleep = lambda *_: None
    try:
        models = FakeModels(fail_times=2, code=429)
        result = gen(models).generate("a fox")
        check(models.calls == 3, "retried twice before succeeding")
        check(result.image == b"PNGDATA", "returns the image after recovery")

        persistent = FakeModels(fail_times=99, code=429)
        try:
            gen(persistent).generate("a fox")
            check(False, "should give up eventually")
        except ImageGenError as exc:
            check("rate limited" in str(exc).lower(), "explains the rate limit plainly")
    finally:
        _t.sleep = original


def test_non_retryable_error_fails_fast():
    print("\nA non-retryable error is not retried")
    models = FakeModels(fail_times=99, code=400)
    try:
        gen(models).generate("a fox")
        check(False, "should raise")
    except ImageGenError:
        check(models.calls == 1, "only one attempt for a 400")


# ---- chainlit wiring ------------------------------------------------------


def test_decorators_are_registered():
    print("\nEvery Chainlit decorator in app.py is registered")
    import chainlit as cl

    import app  # noqa: F401  importing runs the decorators

    cfg = cl.config.config.code
    for hook in ("on_chat_start", "on_message", "on_settings_update", "on_chat_end", "set_starters"):
        check(getattr(cfg, hook, None) is not None, f"@cl.{hook} is registered")
    check(len(cl.config.config.code.action_callbacks) >= 2, "action callbacks are registered")


if __name__ == "__main__":
    for test in (
        test_prompt_building,
        test_generate_returns_image,
        test_empty_prompt_rejected,
        test_text_only_response_explains_itself,
        test_rate_limit_is_retried,
        test_non_retryable_error_fails_fast,
        test_decorators_are_registered,
    ):
        test()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All checks passed.")
