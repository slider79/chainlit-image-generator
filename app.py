"""Prism: a Chainlit image generator powered by Gemini.

The point of this file is the decorators. Chainlit builds the entire UI from
them: you never write a widget, a layout, or a rerun. Each decorator registers a
callback for one moment in the conversation's life, and Chainlit calls it.

    @cl.set_starters      the suggestion cards on the empty screen
    @cl.on_chat_start     runs once when a session begins
    @cl.on_settings_update runs when the user changes the settings panel
    @cl.on_message        runs on every message the user sends
    @cl.action_callback   runs when the user clicks a button attached to a message
    @cl.on_chat_end       runs when the session closes

Compare this to Streamlit, where the whole script re-executes top to bottom on
every interaction and state has to be carried by hand in st.session_state. Here
state is just a dict on the session, and nothing re-runs.
"""

from __future__ import annotations

import os

import chainlit as cl

from image_gen import (
    ASPECT_RATIOS,
    DEFAULT_ASPECT,
    DEFAULT_MODEL,
    MODELS,
    Generated,
    ImageGenerator,
    ImageGenError,
)

try:  # optional convenience: load a local .env if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv(encoding="utf-8-sig")
except ImportError:
    pass

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
            message="A close-up studio portrait of an elderly blacksmith, soft rim lighting, shallow depth of field",
        ),
    ]


def _settings_panel() -> cl.ChatSettings:
    """The gear-icon panel. Chainlit renders these inputs from a list."""
    return cl.ChatSettings(
        [
            cl.input_widget.Select(
                id="model",
                label="Model",
                values=list(MODELS.keys()),
                items=MODELS,
                initial_value=DEFAULT_MODEL,
            ),
            cl.input_widget.Select(
                id="aspect",
                label="Aspect ratio",
                values=ASPECT_RATIOS,
                initial_value=DEFAULT_ASPECT,
            ),
            cl.input_widget.Select(
                id="style", label="Style", values=STYLES, initial_value="None"
            ),
        ]
    )


# ---------------------------------------------------------------------------
# @cl.on_chat_start: once per session. Set up state and greet.
# ---------------------------------------------------------------------------
@cl.on_chat_start
async def on_chat_start() -> None:
    # cl.user_session is per-connection state. No reruns, so it simply persists.
    cl.user_session.set("settings", {"model": DEFAULT_MODEL, "aspect": DEFAULT_ASPECT, "style": "None"})
    cl.user_session.set("count", 0)

    await _settings_panel().send()

    if not os.environ.get("GEMINI_API_KEY"):
        await cl.Message(
            content=(
                "**No `GEMINI_API_KEY` found.**\n\n"
                "Create a `.env` file next to `app.py` containing:\n\n"
                "```\nGEMINI_API_KEY=your_key_here\n```\n\n"
                "Get a free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey), "
                "then restart the app."
            )
        ).send()
        return

    await cl.Message(
        content=(
            "**Prism** turns a description into an image with Gemini.\n\n"
            "Describe anything and I will draw it. Use the gear icon to change the "
            "model, aspect ratio, or style."
        )
    ).send()


# ---------------------------------------------------------------------------
# @cl.on_settings_update: fires when the settings panel changes.
# ---------------------------------------------------------------------------
@cl.on_settings_update
async def on_settings_update(settings: dict) -> None:
    cl.user_session.set("settings", settings)
    await cl.Message(
        content=(
            f"Settings updated: **{MODELS.get(settings['model'], settings['model'])}**, "
            f"{settings['aspect']}, style {settings['style'].lower()}."
        )
    ).send()


async def _render(result: Generated) -> None:
    """Send an image plus its caption and action buttons."""
    count = cl.user_session.get("count") or 0
    cl.user_session.set("count", count + 1)

    image = cl.Image(
        content=result.image,
        name=f"prism-{count + 1}.png",
        display="inline",
        size="large",
    )

    caption = (
        f"**{result.prompt}**\n\n"
        f"`{result.model}` · {result.seconds}s"
        + (f"\n\n{result.text.strip()}" if result.text.strip() else "")
    )

    # Actions are buttons attached to a message; clicks route to @cl.action_callback.
    actions = [
        cl.Action(name="regenerate", label="Generate again", payload={"prompt": result.prompt}),
        cl.Action(name="variation", label="Make a variation", payload={"prompt": result.prompt}),
    ]

    await cl.Message(content=caption, elements=[image], actions=actions).send()


async def _generate_and_send(prompt: str, variation_hint: str = "") -> None:
    settings = cl.user_session.get("settings") or {}
    model = settings.get("model", DEFAULT_MODEL)

    # cl.Step shows a collapsible progress entry while the work runs.
    async with cl.Step(name=f"Generating with {MODELS.get(model, model)}", type="tool") as step:
        step.input = prompt
        try:
            generator = ImageGenerator()
            result = await cl.make_async(generator.generate)(
                prompt=prompt + variation_hint,
                model=model,
                aspect=settings.get("aspect", DEFAULT_ASPECT),
                style=settings.get("style", "None"),
            )
            result.prompt = prompt  # keep the user's wording for the caption
            step.output = f"Done in {result.seconds}s"
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
    await _generate_and_send(action.payload["prompt"])


@cl.action_callback("variation")
async def on_variation(action: cl.Action) -> None:
    await _generate_and_send(
        action.payload["prompt"],
        variation_hint=" Reinterpret this with a different composition and mood.",
    )


# ---------------------------------------------------------------------------
# @cl.on_chat_end: cleanup hook when the session closes.
# ---------------------------------------------------------------------------
@cl.on_chat_end
async def on_chat_end() -> None:
    made = cl.user_session.get("count") or 0
    print(f"Session ended after {made} image(s).")
