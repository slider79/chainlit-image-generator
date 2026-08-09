---
title: Mirage
emoji: 🪄
colorFrom: purple
colorTo: pink
sdk: static
app_file: index.html
pinned: false
---

# Mirage (static build)

A single-page version of Mirage that calls [Pollinations AI](https://pollinations.ai)
directly from the browser. No backend, no API key, no build step.

This exists because Chainlit needs a persistent server with WebSockets, which
static hosting cannot provide. The full Chainlit app lives in the parent
repository and is the real project; this is a deployable demo of the same idea
and the same design.

## Deploying

The YAML block at the top of this file is Hugging Face Space configuration, so
the folder can be pushed to a **Static** Space as is.

**Hugging Face Spaces:** create a Space with SDK **Static**, then upload the
contents of this folder (`index.html` and this `README.md`) through the Files
tab, or push them to the Space's git remote.

**Anywhere else:** it is one HTML file with no dependencies, so Vercel, Netlify,
GitHub Pages and Cloudflare Pages all serve it by pointing them at this folder.

## Running it locally

Open `index.html` in a browser, or serve the folder:

```bash
python -m http.server 8090
```
