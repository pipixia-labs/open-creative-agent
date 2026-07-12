# Configuration

Open Creative Agent reads local settings from `.env`. Create it from the
template before starting the app:

```bash
cp .env.template .env
```

## Model Keys

The default configuration uses Gemini models, so `GOOGLE_API_KEY` is the first
key to configure:

```env
GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY"
```

Optional provider keys are only needed by selected tools:

```env
OPENAI_API_KEY=""
DASHSCOPE_API_KEY=""
SEGMIND_API_KEY=""
IMGBB_API_KEY=""
ARK_API_KEY=""
TAVILY_API_KEY=""
```

## Local Server

The local server defaults to `127.0.0.1:9502`:

```env
OCA_HOST="127.0.0.1"
OCA_PORT="9502"
OCA_LOCAL_USER_ID="local_user"
VITE_TLDRAW_LICENSE_KEY=""
```

Use `OCA_PORT` when the default port is already occupied.

## Startup Flags

Skip dependency installation on repeated starts:

```bash
OCA_SKIP_INSTALL=1 ./scripts/start_local.sh
```

Skip rebuilding the browser UI when `server/static` is already current:

```bash
OCA_SKIP_FRONTEND_BUILD=1 ./scripts/start_local.sh
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
