# Development

This document covers local development details for Open Creative Agent.

## Manual Startup

The recommended startup path is still:

```bash
./scripts/start_local.sh
```

For manual startup, run the backend and build the frontend yourself:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd web
npm install
npm run build
cd ..
cp .env.template .env
.venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 9502
```

## Validation

Run these checks before committing code changes:

```bash
.venv/bin/python -m compileall -q server src conf unit_test
.venv/bin/python -m pytest unit_test
cd web
npm run build
```

## Project Layout

```text
assets/           README media (examples, workspace screenshot)
conf/             local runtime configuration and agent registry
docs/             user and developer documentation
scripts/          local startup scripts
server/           FastAPI app, routers, services, and built web UI
src/              agent implementations and expert tools
unit_test/        lightweight tests for local mode
web/              React/tldraw browser UI source
```

## Local Architecture

The source-available local version runs as one FastAPI process:

1. `scripts/start_local.sh` prepares the Python and web environments.
2. The React/tldraw UI is built from `web/` into `server/static/`.
3. `server.main:app` serves the API, static UI, uploads, and generated outputs.
4. Chat requests are routed to the local agent graph and provider-backed tools.

The local version does not require Docker, Redis, a login system, a billing
layer, or a hosted worker queue.

## Agent Architecture

A chat request flows through three layers under `src/agents/`:

1. **Orchestrator** (`src/agents/orchestrator/`) reads the brief plus session
   state and produces a step-by-step plan.
2. **Executor** (`src/agents/executor/`) runs the plan, dispatching each step
   to one expert agent and folding results back into session state.
3. **Experts** (`src/agents/experts/`) are 20 single-purpose agents built on
   google-adk.

The expert roster, grouped by what they do:

| Group | Agents |
| --- | --- |
| Image generation | `ImageGenerationAgent` (Nano Banana / Seedream), `ReasoningImageGenerationAgent`, `ImageGenerationAndEditingAgent` |
| Image analysis | `ImageUnderstandingAgent`, `ImageToPromptAgent`, `ImageProcessingAgent` (background removal) |
| Video | `VideoGenerationAgent` (Veo / Seedance) |
| Research | `SearchAgent`, `SearchQueryAgent`, `ExtractorAgent`, `ReadArtifactAgent` |
| Design and copy | `ArtKnowledgeAgent`, `AdTextElementGenerationAgent`, `ScienceAgent` |
| Composed deliverables | `ArticleGenerationAgentv2`, `PosterGenerationAgent`, `PageGenerationByReferenceAgent`, `UIGenerationAgent` |
| Web rendering | `HTMLGenerationAgent`, `HTMLToImageAgent` (Playwright) |

Two registration points must stay in sync when adding or removing an expert:

- `conf/jsons/agent.json` — the description and parameters shown to the
  orchestrator (set `enable: false` to hide an agent without deleting code);
- `server/agents_manager.py` — instantiation and the `expert_agents` mapping.

## Frontend

The browser UI is a small Vite + React + TypeScript app in `web/` using the
tldraw SDK for the canvas. `npm run build` outputs into `server/static/`, which
FastAPI serves at `/`. During UI work, rebuild and restart with:

```bash
OCA_SKIP_INSTALL=1 ./scripts/start_local.sh
```

## Contribution Notes

- Keep changes runnable: the app should start and `pytest unit_test` should
  pass after every commit.
- Describe the purpose, approach, and verification steps in pull requests.
- Prefer small, reviewable iterations over large rewrites.
