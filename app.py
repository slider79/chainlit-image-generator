"""Prism: a Chainlit image generator powered by Pollinations AI.

The point of this file is the decorators. Chainlit builds the entire UI from
them: you never write a widget, a layout, or a rerun. Each decorator registers a
callback for one moment in the conversation's life, and Chainlit calls it.

    @cl.set_starters       the suggestion cards on the empty screen
    @cl.on_chat_start      runs once when a session begins
    @cl.on_settings_update runs when the user changes the settings panel
    @cl.on_message         runs on every message the user sends
    @cl.action_callback    runs when a button on a message is clicked
    @cl.on_chat_end        runs when the session closes

Compare this to Streamlit, where the whole script re-executes top to bottom on
every interaction and state has to be carried by hand in st.session_state. Here
state is just a dict on the session, and nothing re-runs.
"""

from __future__ import annotations

import random

import chainlit as cl

from image_gen import (
    DEFAULT_SIZE,
    SIZES,
    STYLES,
    Generated,
    ImageGenerator,
    ImageGenError,
)


# ---------------------------------------------------------------------------
# @cl.set_starters: the cards shown on an empty chat, before any message.
# ---------------------------------------------------------------------------
@cl.set_starters
async def starters() -> list[cl.Starter]:
    return [
        cl.Starter(
            label="Neon jellyfish",
            message="A bioluminescent jellyfish drifting above a rain-slick cyberpunk city at night",
        ),
        cl.Starter(
            label="Mountain cabin",
            message="A tiny wooden cabin on a snowy mountain ridge at sunrise, warm light in the windows",
        ),
        cl.Starter(
            label="Retro poster",
            message="A 1970s travel poster for Jupiter's moon Europa, bold flat colours and grainy print",
        ),
        cl.Starter(
            label="Studio portrait",
            message="A close-up studio portrait of an elderly blacksmith, soft rim lighting",
        ),
    ]


def _settings_panel() -> cl.ChatSettings:
    """The settings panel. Chainlit renders these inputs from a list.

    There is deliberately no model selector: Pollinations currently returns the
    same image whatever model is requested, so offering a choice would be
    inventing a control that does nothing.
    """
    return cl.ChatSettings(
        [
            cl.input_widget.Select(
                id="size",
                label="Image size",
                values=list(SIZES.keys()),
                initial_value=DEFAULT_SIZE,
            ),
            cl.input_widget.Select(
                id="style",
                label="Style",
                values=STYLES,
                initial_value="None",
            ),
        ]
    )


# ---------------------------------------------------------------------------
# @cl.on_chat_start: once per session. Set up state and greet.
# ---------------------------------------------------------------------------
@cl.on_chat_start
async def on_chat_start() -> None:
    # cl.user_session is per-connection state. No reruns, so it simply persists.
    cl.user_session.set("settings", {"size": DEFAULT_SIZE, "style": "None"})
    cl.user_session.set("count", 0)

    await _settings_panel().send()
    await cl.Message(
        content=(
            "**Prism** turns a description into an image using "
            "[Pollinations AI](https://pollinations.ai), which is free and needs no API key.\n\n"
            "Describe anything and I will draw it. Use the settings panel to change "
            "the size or style. Larger images can take up to a minute."
        )
    ).send()


# ---------------------------------------------------------------------------
# @cl.on_settings_update: fires when the settings panel changes.
# ---------------------------------------------------------------------------
@cl.on_settings_update
async def on_settings_update(settings: dict) -> None:
    cl.user_session.set("settings", settings)
    style = settings.get("style", "None")
    await cl.Message(
        content=(
            f"Settings updated: **{settings.get('size', DEFAULT_SIZE)}**"
            + (f", {style.lower()} style." if style != "None" else ", no set style.")
        )
    ).send()


async def _render(result: Generated) -> None:
    """Send the image with its caption and action buttons."""
    count = (cl.user_session.get("count") or 0) + 1
    cl.user_session.set("count", count)

    image = cl.Image(
        content=result.image,
        name=f"prism-{count}.jpg",
        display="inline",
        size="large",
    )

    style_note = "" if result.style == "None" else f" · {result.style.lower()}"
    caption = (
        f"**{result.prompt}**\n\n"
        f"`{result.size_label}{style_note}` · seed `{result.seed}` · {result.seconds}s"
    )

    # Actions are buttons on a message; clicks route to @cl.action_callback.
    payload = {"prompt": result.prompt, "seed": result.seed}
    actions = [
        cl.Action(name="regenerate", label="Generate again", payload=payload),
        cl.Action(name="variation", label="Make a variation", payload=payload),
    ]

    await cl.Message(content=caption, elements=[image], actions=actions).send()


async def _generate_and_send(prompt: str, seed: int | None = None, hint: str = "") -> None:
    settings = cl.user_session.get("settings") or {}

    # cl.Step shows a collapsible progress entry while the work runs.
    async with cl.Step(name="Generating with Pollinations", type="tool") as step:
        step.input = prompt
        try:
            generator = ImageGenerator()
            # make_async moves blocking work off the event loop so the UI stays live.
            result = await cl.make_async(generator.generate)(
                prompt=prompt + hint,
                size_label=settings.get("size", DEFAULT_SIZE),
                style=settings.get("style", "None"),
                seed=seed,
            )
            result.prompt = prompt  # keep the user's wording for the caption
            step.output = f"Done in {result.seconds}s (seed {result.seed})"
        except ImageGenError as exc:
            step.output = str(exc)
            await cl.Message(content=f"**Could not generate that.** {exc}").send()
            return

    await _render(result)


# ---------------------------------------------------------------------------
# @cl.on_message: the main entry point, one call per user message.
# ---------------------------------------------------------------------------
@cl.on_message
async def on_message(message: cl.Message) -> None:
    await _generate_and_send(message.content)


# ---------------------------------------------------------------------------
# @cl.action_callback: one per button name, fired when that button is clicked.
# ---------------------------------------------------------------------------
@cl.action_callback("regenerate")
async def on_regenerate(action: cl.Action) -> None:
    # A fresh seed gives a genuinely different image from the same prompt.
    await _generate_and_send(action.payload["prompt"], seed=random.randint(1, 1_000_000))


@cl.action_callback("variation")
async def on_variation(action: cl.Action) -> None:
    await _generate_and_send(
        action.payload["prompt"],
        seed=random.randint(1, 1_000_000),
        hint=", different composition and mood",
    )


# ---------------------------------------------------------------------------
# @cl.on_chat_end: cleanup hook when the session closes.
# ---------------------------------------------------------------------------
@cl.on_chat_end
async def on_chat_end() -> None:
    made = cl.user_session.get("count") or 0
    print(f"Session ended after {made} image(s).")
