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
assets/examples/  example outputs used by the README
conf/             local runtime configuration
docs/             user and developer documentation
scripts/          local startup scripts
server/           FastAPI app, routers, services, and built web UI
src/              agent implementations and expert tools
unit_test/        lightweight tests for local mode
web/              React/tldraw browser UI source
```

## Local Architecture

The open-source local version runs as one FastAPI process:

1. `scripts/start_local.sh` prepares the Python and web environments.
2. The React/tldraw UI is built from `web/` into `server/static/`.
3. `server.main:app` serves the API, static UI, uploads, and generated outputs.
4. Chat requests are routed to the local agent graph and provider-backed tools.

The local version does not require Docker, Redis, a login system, a billing
layer, or a hosted worker queue.
