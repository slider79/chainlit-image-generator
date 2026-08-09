# Prism

**A Chainlit image generator powered by Gemini · By Shuja Jamal**

Describe an image, get an image. Prism is a small conversational app built with [Chainlit](https://docs.chainlit.io) to learn how its decorator-driven model works, and how that compares to building the same thing in Streamlit.

![Chainlit](https://img.shields.io/badge/ui-Chainlit-2f6fed)
![Gemini](https://img.shields.io/badge/images-Gemini-1b7a43)
![Python](https://img.shields.io/badge/python-3.11%2B-1f4e79)

---

## What it does

- Type a description, Gemini draws it, the image appears inline in the chat.
- **Starter cards** on the empty screen give one-click example prompts.
- A **settings panel** switches model, aspect ratio, and style mid-conversation.
- Every image comes with **Generate again** and **Make a variation** buttons.
- A collapsible **step** shows the generation running, with timing.

---

## The decorators, which are the whole point

Chainlit has no layout code. You do not place widgets or manage reruns. You register callbacks for moments in a conversation and Chainlit builds the UI around them. Every decorator below is used in [`app.py`](app.py):

| Decorator | When it runs | What it does here |
| :--- | :--- | :--- |
| `@cl.set_starters` | Rendering an empty chat | Returns the four suggestion cards |
| `@cl.on_chat_start` | Once, when a session opens | Seeds session state, sends the settings panel, greets the user |
| `@cl.on_settings_update` | User changes a setting | Stores the new model / ratio / style |
| `@cl.on_message` | Every user message | Generates an image from the message |
| `@cl.action_callback("regenerate")` | That button is clicked | Re-runs the same prompt |
| `@cl.action_callback("variation")` | That button is clicked | Re-runs with a "reinterpret this" hint |
| `@cl.on_chat_end` | Session closes | Cleanup hook, logs how many images were made |

A decorator is just a function that takes a function and registers or wraps it. `@cl.on_message` hands your function to Chainlit's router, so when a message arrives, Chainlit calls it with a `cl.Message`. Nothing else in the file has to know that happened, which is why the app reads as a list of event handlers rather than a script.

The UI elements used: `cl.Message` (text), `cl.Image` (inline images), `cl.Action` (buttons), `cl.ChatSettings` with `Select` inputs (the settings panel), `cl.Step` (progress), and `cl.Starter` (suggestion cards).

---

## Chainlit vs Streamlit

I built the previous eight projects in this internship with Streamlit, so this is a direct comparison rather than a summary of the docs.

### The core difference: rerun vs callback

**Streamlit re-executes the entire script on every interaction.** That single fact shapes everything else. Any value that must survive a click has to be parked in `st.session_state`, expensive work has to be wrapped in `@st.cache_resource` or it repeats, and you learn to reason about "what runs again when this button is pressed."

**Chainlit runs your callbacks and nothing else.** `@cl.on_message` fires once per message. A local variable stays a local variable. `cl.user_session` is a plain dict that persists because nothing re-executes. Building a chat UI, this removed a whole category of bug I had been managing by hand.

Two concrete examples from my own work:

- In the Streamlit voice agent I had to hash the recorded audio and compare it against the previous hash, because a rerun would otherwise reprocess the same recording endlessly. In Chainlit that problem does not exist; the handler fires once.
- In the Streamlit chatbots I stored API keys under a non-widget session key, because Streamlit clears widget state when a widget stops rendering. That bug class is specific to the rerun model.

### Where each one wins

| | Chainlit | Streamlit |
| :--- | :--- | :--- |
| **Best at** | Conversational apps: chat, agents, assistants | Dashboards, forms, data apps, anything tabular or charted |
| **Chat UI** | Built in, including streaming, message history, threads, and file attachments | You assemble it from `st.chat_message` and manage the transcript yourself |
| **State** | Persists naturally; callbacks only | `st.session_state` plus rerun-aware thinking |
| **Layout control** | Deliberately limited; you get the chat shell | Full control: columns, tabs, sidebars, arbitrary pages |
| **Charts and tables** | Not its purpose | Excellent, one line each |
| **Agent visibility** | `cl.Step` renders nested tool calls and reasoning for free | You build your own progress and trace display |
| **Learning curve** | Very small if you know decorators | Very small, full stop |
| **Ecosystem** | Younger, smaller | Large, mature, huge deployment story |

### How I would choose

- **Chat with an LLM or an agent, and I want it to look right by default:** Chainlit. The step display alone is worth it for anything with tool calls, and I did not write a single line of layout code for this project.
- **Anything with controls, charts, tables, or a dashboard around the model:** Streamlit. The RAG project in this internship has a performance dashboard with metrics and charts next to the chat; that is Streamlit's home ground and would have been awkward in Chainlit.
- **A mixed app:** Streamlit, because Chainlit is opinionated about being a chat and fighting that is not worth it.

The honest summary: Chainlit is faster and cleaner for the narrow case it targets, Streamlit is more flexible for everything else. Having built both, I would not pick one as "better", they solve different shapes of problem.

---

## Setup

**1. Get a free Gemini key** at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).

**2. Install and run:**

```bash
git clone https://github.com/slider79/chainlit-image-generator.git
cd chainlit-image-generator

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS or Linux

pip install -r requirements.txt

copy .env.example .env          # cp on macOS/Linux, then add your key
chainlit run app.py
```

It opens at `http://localhost:8000`.

`.env` is gitignored; never put a real key in `.env.example`, which is tracked.

---

## Tests

```bash
python tests/test_image_gen.py
```

No API key and no browser needed. The Gemini client is faked, so the tests cover prompt construction from the settings, extracting an image from a response, retrying a rate limit, refusing an empty prompt, explaining a text-only reply, and confirming every Chainlit decorator in `app.py` is actually registered.

---

## Project structure

```
.
├── app.py                     the Chainlit app: every decorator lives here
├── image_gen.py               Gemini image generation, UI-free so it is testable
├── requirements.txt
├── .env.example               template for GEMINI_API_KEY
├── chainlit.md                the readme shown inside the app
├── .chainlit/config.toml      app name, dark theme, wide layout, sidebar settings
├── public/
│   ├── theme.json             dark palette, squared corners
│   └── style.css              small styling pass on top
├── tests/test_image_gen.py
└── README.md
```

---

## Notes

**Models.** The settings panel offers `gemini-2.5-flash-image` (fast and stable), `gemini-3.1-flash-image`, and `gemini-3-pro-image`. Aspect ratio and style are expressed as instructions inside the prompt, since these models take direction in plain language rather than as separate parameters.

**Rate limits.** The Gemini free tier is easy to exhaust. Generation retries `429` and `5xx` with backoff, and if the limit is genuinely reached the app says so in plain words rather than showing a stack trace. If you see that message, wait a minute or switch model.

**Keys.** The API key is read from the environment, never sent to the browser, and stripped from any error message before it is displayed.

---

*By Shuja Jamal, August 2026.*
