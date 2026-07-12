# Configuration

Open Creative Agent reads local settings from `.env`. Create it from the
template before starting the app:

```bash
cp .env.template .env
```

## Model Keys

`GOOGLE_API_KEY` is the only required key. The default configuration runs
planning, writing, HTML generation, and Nano-Banana image generation on Gemini:

```env
GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY"
```

Optional keys unlock additional tools. Everything degrades gracefully — agents
that need a missing key simply are not used:

| Key | Unlocks | Provider console |
| --- | --- | --- |
| `GOOGLE_API_KEY` | Gemini LLMs, Nano-Banana image generation/editing, Veo video | [Google AI Studio](https://aistudio.google.com/apikey) |
| `ARK_API_KEY` | Seedream image generation/editing, Seedance video | [Volcano Ark](https://console.volcengine.com/ark) |
| `TAVILY_API_KEY` | Web search used by the search agent | [Tavily](https://tavily.com) |
| `OPENAI_API_KEY` | GPT models (default writer for illustrated articles and posters) | [OpenAI](https://platform.openai.com) |
| `DASHSCOPE_API_KEY` | Qwen-based image understanding helpers | [DashScope](https://dashscope.aliyun.com) |
| `SEGMIND_API_KEY` | Selected image tools (e.g. background processing) | [Segmind](https://segmind.com) |
| `IMGBB_API_KEY` | Temporary image hosting used by some editing flows | [imgbb](https://api.imgbb.com) |

## Model Selection

Per-role model choices live in `conf/jsons/system.json`. Each entry accepts a
LiteLLM-style `provider/model` string:

```json
"llm_model": "gemini/gemini-3.5-flash",
"orchestrator_llm_model": "gemini/gemini-3.5-flash",
"html_gen_llm_model": "gemini/gemini-3.5-flash",
"article_llm_model": "openai/gpt-5.5",
"science_llm_model": "gemini/gemini-3.5-flash"
```

Notes:

- `article_llm_model` defaults to `openai/gpt-5.5`, so illustrated-article and
  poster writing use `OPENAI_API_KEY` out of the box. Point it at a Gemini
  model (for example `gemini/gemini-3.5-flash`) to run article writing on your
  Google key only.
- `conf/jsons/system_debug.json` is loaded instead of `system.json` when the
  server runs with `ACA_ENV=debug`.

Expert agents are registered in `conf/jsons/agent.json`. Setting an entry's
`enable` flag to `false` removes it from the orchestrator's planning list
without code changes.

## Local Server

The local server defaults to `127.0.0.1:9502`:

```env
OCA_HOST="127.0.0.1"
OCA_PORT="9502"
OCA_LOCAL_USER_ID="local_user"
VITE_TLDRAW_LICENSE_KEY=""
```

Use `OCA_PORT` when the default port is already occupied.
`VITE_TLDRAW_LICENSE_KEY` optionally passes a tldraw production license to the
browser build.

## Startup Flags

Skip dependency installation on repeated starts:

```bash
OCA_SKIP_INSTALL=1 ./scripts/start_local.sh
```

Skip rebuilding the browser UI when `server/static` is already current:

```bash
OCA_SKIP_FRONTEND_BUILD=1 ./scripts/start_local.sh
```

Both flags combined give the fastest restart:

```bash
OCA_SKIP_INSTALL=1 OCA_SKIP_FRONTEND_BUILD=1 ./scripts/start_local.sh
```

## Local Runtime Files

The app creates local runtime files that are ignored by git:

```text
.venv/
database/
logs/
outputs/
uploads/
__pycache__/
```
