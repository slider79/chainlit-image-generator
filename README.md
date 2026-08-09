# Prism

**A Chainlit image generator · By Shuja Jamal**

Describe an image, get an image. Prism is a small conversational app built with [Chainlit](https://docs.chainlit.io) to learn how its decorator-driven model works, and how that compares to building the same thing in Streamlit.

Images come from [Pollinations AI](https://pollinations.ai), which is free, open source, and needs **no API key**, so the whole app deploys with no secrets at all.

![Chainlit](https://img.shields.io/badge/ui-Chainlit-2f6fed)
![Pollinations](https://img.shields.io/badge/images-Pollinations-8b5cf6)
![No API key](https://img.shields.io/badge/api_key-none_required-1b7a43)
![Python](https://img.shields.io/badge/python-3.11%2B-1f4e79)

**Live app:** _add your Hugging Face Space URL here after deploying_

---

## What it does

- Type a description, Pollinations draws it, the image appears inline in the chat.
- **Starter cards** on the empty screen give one-click example prompts.
- A **settings panel** switches image size and style mid-conversation.
- Every image comes with **Generate again** and **Make a variation** buttons, which re-roll the seed.
- A collapsible **step** shows the generation running, with timing and the seed used.

---

## The decorators, which are the whole point

Chainlit has no layout code. You do not place widgets or manage reruns. You register callbacks for moments in a conversation and Chainlit builds the UI around them. Every decorator below is used in [`app.py`](app.py):

| Decorator | When it runs | What it does here |
| :--- | :--- | :--- |
| `@cl.set_starters` | Rendering an empty chat | Returns the four suggestion cards |
| `@cl.on_chat_start` | Once, when a session opens | Seeds session state, sends the settings panel, greets the user |
| `@cl.on_settings_update` | User changes a setting | Stores the new size and style |
| `@cl.on_message` | Every user message | Generates an image from the message |
| `@cl.action_callback("regenerate")` | That button is clicked | Same prompt, new seed |
| `@cl.action_callback("variation")` | That button is clicked | New seed plus a "different composition" hint |
| `@cl.on_chat_end` | Session closes | Cleanup hook, logs how many images were made |

A decorator is a function that takes a function and registers or wraps it. `@cl.on_message` hands your function to Chainlit's router, so when a message arrives, Chainlit calls it with a `cl.Message`. Nothing else in the file has to know that happened, which is why the app reads as a list of event handlers rather than a script.

UI elements used: `cl.Message` (text), `cl.Image` (inline images), `cl.Action` (buttons), `cl.ChatSettings` with `Select` inputs, `cl.Step` (progress), `cl.Starter` (suggestion cards).

---

## Chainlit vs Streamlit

I built the previous eight projects in this internship with Streamlit, so this is a direct comparison rather than a summary of the docs.

### The core difference: rerun vs callback

**Streamlit re-executes the entire script on every interaction.** That single fact shapes everything else. Any value that must survive a click has to be parked in `st.session_state`, expensive work has to be wrapped in `@st.cache_resource` or it repeats, and you learn to reason about "what runs again when this button is pressed."

**Chainlit runs your callbacks and nothing else.** `@cl.on_message` fires once per message. A local variable stays a local variable. `cl.user_session` is a plain dict that persists because nothing re-executes. Building a chat UI, this removed a whole category of bug I had been managing by hand.

Two concrete examples from my own work:

- In the Streamlit voice agent I had to hash the recorded audio and compare it against the previous hash, because a rerun would otherwise reprocess the same recording endlessly. In Chainlit that problem does not exist; the handler fires once.
- In the Streamlit chatbots I had to store API keys under a non-widget session key, because Streamlit clears widget state when a widget stops rendering. That bug class is specific to the rerun model.

### Where each one wins

| | Chainlit | Streamlit |
| :--- | :--- | :--- |
| **Best at** | Conversational apps: chat, agents, assistants | Dashboards, forms, data apps, anything tabular or charted |
| **Chat UI** | Built in, including streaming, history, threads, attachments | You assemble it from `st.chat_message` and manage the transcript yourself |
| **State** | Persists naturally; callbacks only | `st.session_state` plus rerun-aware thinking |
| **Layout control** | Deliberately limited; you get the chat shell | Full control: columns, tabs, sidebars, pages |
| **Charts and tables** | Not its purpose | Excellent, one line each |
| **Agent visibility** | `cl.Step` renders nested tool calls and reasoning for free | You build your own progress and trace display |
| **Deployment** | Needs a real server with WebSockets, so a container | Streamlit Cloud is one click and free |
| **Ecosystem** | Younger, smaller | Large, mature |

### How I would choose

- **Chat with an LLM or an agent, and I want it to look right by default:** Chainlit. The step display alone is worth it for anything with tool calls, and I wrote no layout code for this project.
- **Anything with controls, charts, tables, or a dashboard around the model:** Streamlit. The RAG project in this internship has a performance dashboard with metrics and charts beside the chat; that is Streamlit's home ground and would fight Chainlit.
- **A mixed app:** Streamlit, because Chainlit is opinionated about being a chat and arguing with that is not worth it.

The honest summary: Chainlit is faster and cleaner for the narrow case it targets; Streamlit is more flexible for everything else. Having built both, I would not call either one better. They solve different shapes of problem.

---

## Running it locally

No API key, no `.env`, nothing to sign up for.

```bash
git clone https://github.com/slider79/chainlit-image-generator.git
cd chainlit-image-generator

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS or Linux

pip install -r requirements.txt
chainlit run app.py
```

It opens at `http://localhost:8000`.

---

## Deploying

Chainlit keeps an open WebSocket to the browser, so it needs a long-lived server. That rules out serverless hosts such as Vercel, and is why this repo ships a [`Dockerfile`](Dockerfile) instead.

### Hugging Face Spaces (free, no card)

The easiest option, and the one this Dockerfile targets.

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space).
2. Name it, for example `prism`, and choose **Docker** as the Space SDK (blank template), visibility **Public**, hardware **CPU basic (free)**.
3. Create the Space, then push this repo to it:
   ```bash
   git remote add space https://huggingface.co/spaces/<your-username>/prism
   git push space main
   ```
   Alternatively, use the Space's **Files** tab to upload the repository contents directly in the browser.
4. Add this block to the very top of `README.md` in the Space (Hugging Face reads it as configuration):
   ```
   ---
   title: Prism
   emoji: 🎨
   colorFrom: gray
   colorTo: purple
   sdk: docker
   app_port: 7860
   ---
   ```
5. The Space builds automatically and goes live at `https://huggingface.co/spaces/<your-username>/prism`.

No secrets to configure, because Pollinations needs no key.

### Any other container host

The same image runs anywhere that takes a Dockerfile. **Railway** ([railway.app](https://railway.app)): New Project, Deploy from GitHub repo, it detects the Dockerfile, and you expose the port it prints. **Fly.io**: `fly launch` then `fly deploy`. **Google Cloud Run**: deploy from source and set the port to `7860`. In each case the container listens on `$PORT`, which the Dockerfile already respects.

### Why not Vercel

Vercel functions are serverless and short-lived, and they do not hold the WebSocket connection Chainlit relies on for streaming and events. The RAG voice backend in this internship suits Vercel precisely because it is request/response; this app is not.

---

## Tests

```bash
python tests/test_image_gen.py
```

No network and no browser needed. The HTTP client is faked, so the tests cover URL and prompt construction from the settings, handling a successful image, retrying transient failures, seed behaviour, refusing an empty prompt, explaining a non-image response and a timeout, and confirming every Chainlit decorator in `app.py` is actually registered.

---

## Project structure

```
.
├── app.py                     the Chainlit app: every decorator lives here
├── image_gen.py               Pollinations calls, UI-free so it is testable
├── Dockerfile                 container for Hugging Face Spaces or any host
├── requirements.txt           chainlit, httpx
├── chainlit.md                the readme shown inside the app
├── .chainlit/config.toml      app name, dark theme, wide layout, sidebar settings
├── public/
│   ├── theme.json             dark palette, squared corners
│   └── style.css              small styling pass on top
├── tests/test_image_gen.py
└── README.md
```

---

## Notes on the API, checked rather than assumed

**Why Pollinations.** Gemini's image generation is no longer free, so this project moved to Pollinations: free, open source, and keyless. An image is a plain GET request whose URL contains the prompt.

**There is deliberately no model selector.** Pollinations advertises a `model` parameter, but testing it against the live service returned byte-identical images for `sana`, `flux`, `turbo` and even a nonsense model name, and the models endpoint lists only one model. A dropdown would therefore be a control that does nothing, so the settings panel offers size and style instead, both of which measurably change the result.

**Size and seed are real.** Different dimensions produce genuinely different images, and the same seed reproduces the same image, which is why *Generate again* and *Make a variation* re-roll the seed.

**Timing.** Small images come back in a couple of seconds; 1024px and larger can take the best part of a minute. The client allows 180 seconds, retries transient failures with backoff, and explains a timeout in plain words rather than hanging.

---

*By Shuja Jamal, August 2026.*
