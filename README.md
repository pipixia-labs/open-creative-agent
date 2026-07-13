<div align="center">

<h1>🎨 Open Creative Agent</h1>

<p><strong>Turn a rough idea into finished visual work — posters, product shots, illustrated articles, UI mockups, and short videos — in one local chat-and-canvas workspace.</strong></p>

<p>
  <a href="./README.md">English</a> |
  <a href="./README.zh-CN.md">简体中文</a>
</p>

<p>
  <img src="https://img.shields.io/badge/python-3.14-3776ab" alt="Python 3.14">
  <img src="https://img.shields.io/badge/runtime-local--first-2f855a" alt="Local-first">
  <img src="https://img.shields.io/badge/UI-React%20%2B%20tldraw-2563eb" alt="React + tldraw">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="License: Apache-2.0"></a>
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen" alt="PRs welcome">
</p>

</div>

**Open Creative Agent (OCA)** is an open-source, local-first **multi-agent creative studio**. You describe the outcome in plain language — goal, audience, copy, source material, constraints — and an orchestrator plans the work across **20 specialist agents** for research, design knowledge, image generation and editing, video, articles, posters, and web/UI pages. Results land on a movable [tldraw](https://tldraw.dev) canvas next to the chat, ready to inspect, refine in follow-up messages, and download.

One `git clone`, one script, one browser tab. No Docker, no account, no cloud backend.

<p align="center">
  <a href="assets/demo.gif"><img src="assets/demo.gif" width="860" alt="Open Creative Agent demo: a brief becomes a finished poster, then gets refined by one follow-up message"></a>
  <br><sub>A real session at ~14× speed: search → design → generate → render → refine by conversation.</sub>
</p>

<table align="center">
  <tr>
    <td align="center"><a href="assets/examples/poster-edit-final.png"><img src="assets/examples/poster-edit-final.png" height="210" alt="Poster refined over four chat turns"></a></td>
    <td align="center"><a href="assets/examples/amazon-product-output.png"><img src="assets/examples/amazon-product-output.png" height="210" alt="Amazon listing image set"></a></td>
    <td align="center"><a href="assets/examples/ui-design-output.png"><img src="assets/examples/ui-design-output.png" height="210" alt="Mobile banking app UI"></a></td>
    <td align="center"><a href="assets/examples/knowledge-card-output.jpg"><img src="assets/examples/knowledge-card-output.jpg" height="210" alt="Vocabulary knowledge card"></a></td>
  </tr>
</table>

## Start Here

| You want to... | Go to |
| --- | --- |
| Run it on your machine in ~5 minutes | [Quick Start](#-quick-start) |
| See what it can produce | [Showcase](#%EF%B8%8F-showcase) |
| Understand what makes it different | [Why Open Creative Agent](#-why-open-creative-agent) |
| Configure API keys, models, ports | [Configuration](docs/configuration.md) |
| Read the code, run tests, contribute | [Development](docs/development.md) |

## 📢 News

- **2026-07** 🎉 Initial open-source release: local chat + canvas workspace, an orchestrator coordinating 20 specialist agents, and end-to-end generation of posters, product visuals, illustrated articles, UI pages, and videos.

## 💡 Why Open Creative Agent

- **Brief-first, not prompt-first.** Write the actual brief — audience, copy, product photos, style constraints — instead of compressing everything into one image prompt. The orchestrator decomposes it and routes each part to the right specialist.
- **A real creative pipeline.** Search → design reasoning → asset generation → editing → layout → rendering. Marketing sets, illustrated articles, and detail pages come out assembled, not as loose fragments.
- **Text that is actually correct.** Layout-heavy formats (posters, long images, knowledge cards, UI pages) are composed as web pages and rendered to pixels, so titles, dates, and body copy stay sharp and typo-free — the classic failure mode of pure text-to-image.
- **Edit by conversation.** "Center the title, make it 1.5× larger, drop the QR code" — follow-up messages refine the previous result instead of regenerating from scratch.
- **Chat + canvas, side by side.** Generated media appears on an infinite tldraw canvas you can arrange and compare, while planning and progress stream in the chat rail.
- **Local-first and hackable.** One FastAPI process serving a React UI. Readable Python on [google-adk](https://github.com/google/adk-python), pluggable model providers, no hosted dependencies.

## 🖼️ Showcase

Everything below was produced by OCA from a single brief (plus follow-up edits where noted). Click any image for full size.

<table>
  <tr>
    <td align="center" width="33%">
      <a href="assets/examples/poster-edit-final.png"><img src="assets/examples/poster-edit-final.png" width="230" alt="Conversational poster editing"></a>
      <br><b>Poster, refined over 4 turns</b>
      <br><sub>"Make a poster for the 27th China Hi-Tech Fair — search for the details" → "center the title, brighter color, 1.5× larger" → "recolor the title, move body text down" → "remove the QR code".</sub>
    </td>
    <td align="center" width="33%">
      <a href="assets/examples/amazon-product-output.png"><img src="assets/examples/amazon-product-output.png" width="230" alt="Amazon product listing images"></a>
      <br><b>Amazon listing image set</b>
      <br><sub>Main, multi-angle, lifestyle, and detail shots plus English copy — generated from one product photo, keeping the product identical.</sub>
    </td>
    <td align="center" width="33%">
      <a href="assets/examples/reasoning-image-output.png"><img src="assets/examples/reasoning-image-output.png" width="230" alt="Reasoning-based image generation"></a>
      <br><b>Reasoning-heavy generation</b>
      <br><sub>Three trending outfits, each in front of a famous building from a different continent, under that city's real-time weather, annotated with a math, physics, and chemistry formula.</sub>
    </td>
  </tr>
  <tr>
    <td align="center">
      <a href="assets/examples/art-illustration-set.png"><img src="assets/examples/art-illustration-set.png" width="230" alt="Art illustration set"></a>
      <br><b>Illustration series</b>
      <br><sub>Four collage-style illustrations blending scenic landscapes into animal silhouettes, in bright high-impact colors.</sub>
    </td>
    <td align="center">
      <a href="assets/examples/ui-design-output.png"><img src="assets/examples/ui-design-output.png" width="230" alt="UI design"></a>
      <br><b>Mobile app UI</b>
      <br><sub>A banking-app home screen: balance, card switcher, recent transactions, transfer / top-up / invest actions — professional and trust-first.</sub>
    </td>
    <td align="center">
      <a href="assets/examples/knowledge-card-output.jpg"><img src="assets/examples/knowledge-card-output.jpg" width="230" alt="Knowledge card"></a>
      <br><b>Knowledge card</b>
      <br><sub>1080×1920 vocabulary card as a ready-to-open web page: cartoon illustration on top, phonetics, meaning, and example sentence below.</sub>
    </td>
  </tr>
  <tr>
    <td align="center">
      <a href="assets/examples/long-form-visual.png"><img src="assets/examples/long-form-visual.png" width="230" alt="Long-form visual"></a>
      <br><b>Long-form vertical graphic</b>
      <br><sub>A scrolling infographic of China's dynasties, each with a short introduction.</sub>
    </td>
    <td align="center">
      <a href="assets/examples/marketing-article-output.jpg"><img src="assets/examples/marketing-article-output.jpg" width="230" alt="Marketing article"></a>
      <br><b>Illustrated marketing article</b>
      <br><sub>A Xiaohongshu-style product article with matching generated illustrations, written and composed end to end.</sub>
    </td>
    <td align="center">
      <a href="assets/examples/event-text-poster.png"><img src="assets/examples/event-text-poster.png" width="230" alt="Event text poster"></a>
      <br><b>Text-accurate event poster</b>
      <br><sub>Exhibition poster with venue, dates, and organizer rendered exactly as provided — headline prominent, zero garbled text.</sub>
    </td>
  </tr>
</table>

## 🚀 Quick Start

Prerequisites: **Python 3.14+**, **Node.js + npm**, macOS or Linux, and a [Google AI Studio API key](https://aistudio.google.com/apikey) (free tier works).

```bash
git clone https://github.com/GML-FMGroup/open-creative-agent.git
cd open-creative-agent
cp .env.template .env      # put your GOOGLE_API_KEY inside
./scripts/start_local.sh
```

Then open **http://127.0.0.1:9502** and describe what you want to make.

The first start takes a few minutes: it creates `.venv`, installs Python and web dependencies, builds the React UI, and launches the server. Later starts are much faster — see [startup flags](docs/configuration.md#startup-flags).

Gemini alone covers planning, writing, page generation, and Nano-Banana image generation. Optional keys unlock more tools — Seedream/Seedance images and video (Volcano Ark), web search (Tavily), and the GPT-backed article writer. See the [provider table](docs/configuration.md#model-keys).

## 🖥️ The Workspace

<p align="center">
  <a href="assets/workspace.png"><img src="assets/workspace.png" width="860" alt="Open Creative Agent workspace: tldraw canvas on the left, chat on the right"></a>
</p>

- **Left — canvas.** Generated images, rendered pages, and videos arrive as real tldraw objects: drag, arrange, zoom, compare versions.
- **Right — chat.** The brief, the agent's plan, expandable thinking steps, and progress live here. Attach product photos or reference images directly.
- **Iterate in place.** Every follow-up message edits the work in context.
- **Download anything.** Finished artifacts are served straight from the local app.

## 🏗️ How It Works

A single FastAPI process serves the API and the built React UI. Each chat request goes to an **orchestrator** that plans the task, then an **executor** dispatches steps to **20 specialist agents** — web search, design knowledge, ad copy, text-to-image and image editing (Nano Banana / Seedream), reasoning-driven generation, video (Veo / Seedance), image understanding and OCR, background removal, illustrated articles, posters, reference-based page recreation, UI generation, HTML page generation, and HTML-to-image rendering. Session state lives in local SQLite; generated files stay on your disk.

Details, project layout, and validation commands: [docs/development.md](docs/development.md).

## 📚 Documentation

- [Configuration](docs/configuration.md) — API keys and what each unlocks, model selection, ports, startup flags.
- [Development](docs/development.md) — manual startup, architecture, project layout, tests, contribution notes.

## 🤝 Contributing & Roadmap

The codebase is intentionally small and readable — one server, one UI, one agent package. PRs and issues are welcome.

Directions we would love help with:

- **Slides / PPT export** — bring deck generation to the local version
- **Deep research agent** — long-horizon research reports feeding creative work
- **More model providers** — additional image, video, and LLM backends
- **Windows support** — a native startup path alongside the shell script
- **UI polish and i18n** — the workspace is young and moving fast

## ⭐ Star History

<div align="center">
  <a href="https://star-history.com/#GML-FMGroup/open-creative-agent&Date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=GML-FMGroup/open-creative-agent&type=Date&theme=dark" />
      <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=GML-FMGroup/open-creative-agent&type=Date" />
      <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=GML-FMGroup/open-creative-agent&type=Date" />
    </picture>
  </a>
</div>

<p align="center"><em>If OCA made something you like, a ⭐ helps more people find it.</em></p>
