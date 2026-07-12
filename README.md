# Open Creative Agent

Open Creative Agent is a local-first creative multi-agent application built on
FastAPI and Google ADK. The current open-source layout runs as one local Python
process and serves both the API and browser UI from the same server.

## Requirements

- Python 3.14
- Node.js and npm
- macOS or Linux shell environment
- At least one LLM provider API key

The default configuration uses Gemini models, so `GOOGLE_API_KEY` is the first
key to configure. Other providers are optional and only needed by selected tools.

## Quick Start

```bash
cp .env.template .env
```

Edit `.env` and set at least:

```env
GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY"
```

Then run:

```bash
./scripts/start_local.sh
```

Open the local UI:

```text
http://127.0.0.1:9502
```

The first startup can take a little while because the agent graph and expert
tools are imported before the server accepts requests.

## One-Command Startup

`scripts/start_local.sh` does the local setup work for you:

1. Creates `.venv` with Python 3.14 if it does not exist.
2. Installs `requirements.txt` into `.venv`.
3. Installs and builds the React/tldraw browser UI from `web/`.
4. Creates `.env` from `.env.template` if `.env` does not exist.
5. Starts `uvicorn` with `server.main:app`.

You can override the host and port in `.env`:

```env
OCA_HOST="127.0.0.1"
OCA_PORT="9502"
OCA_LOCAL_USER_ID="local_user"
VITE_TLDRAW_LICENSE_KEY=""
```

To skip dependency installation on repeated starts:

```bash
OCA_SKIP_INSTALL=1 ./scripts/start_local.sh
```

To skip rebuilding the browser UI when `server/static` is already current:

```bash
OCA_SKIP_FRONTEND_BUILD=1 ./scripts/start_local.sh
```

## Manual Startup

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd web && npm install && npm run build && cd ..
cp .env.template .env
.venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 9502
```

## Example Prompts and Outputs

Add example media under `assets/examples/` and reference it with relative paths.
Click a thumbnail to open the full-size result.

| Type | Prompt | Result |
| --- | --- | --- |
| Art illustration set | 请设计四幅拼贴风格的插画，需要将美丽的风景拼贴进一些可爱的动物中，色彩明亮、具有视觉冲击力。 | <a href="assets/examples/art-illustration-set.png"><img src="assets/examples/art-illustration-set.png" width="220" alt="Art illustration set"></a> |
| Amazon product listing images | 为这个产品生成亚马逊的主图、多视角图、场景图和细节图，并补充相应的文案，针对英语用户。注意生产图需要和输入的图像中的商品保持一致。使用 Nano Banana 来编辑图像。 | <a href="assets/examples/amazon-product-output.png"><img src="assets/examples/amazon-product-output.png" width="260" alt="Amazon product listing images"></a> |
| Conversational poster editing | 初始：针对27届高交会做一个海报，相关信息可以搜索一下。确保文字清晰正确，标题清晰醒目。<br>编辑1：标题居中，颜色换一下，需要醒目一点。其他相关的文字可以放在海报的中部和下部。字体可以变大1.5倍。<br>编辑2：标题文字颜色不好看，换一个好看、醒目、与整体效果匹配的颜色。其他文字再往下一点，并换成黑色。<br>编辑3：去掉二维码的展示。其他部分不变。 | <a href="assets/examples/poster-edit-final.png"><img src="assets/examples/poster-edit-final.png" width="220" alt="Conversational poster editing"></a> |
| Event text poster | 帮我根据以下标题做个活动海报：2025中国（深圳）全球烟斗艺术展。举办地点为：深圳国际会展中心。时间为：2025年11月20日-24日。主办方：深圳烟斗协会。海报上的其他相关文字可以帮我填充。注意标题醒目、文字不要错。 | <a href="assets/examples/event-text-poster.png"><img src="assets/examples/event-text-poster.png" width="220" alt="Event text poster"></a> |
| Long-form visual | 制作一个竖版的长图，介绍中国的各个历史朝代。每个朝代配一段简单的介绍。 | <a href="assets/examples/long-form-visual.png"><img src="assets/examples/long-form-visual.png" width="180" alt="Long-form visual"></a> |
| Marketing article | 针对给定的这个产品，生成一个小红书风格的营销文章。 | <a href="assets/examples/marketing-article-output.jpg"><img src="assets/examples/marketing-article-output.jpg" width="180" alt="Marketing article"></a> |
| UI design | 设计一个移动端银行 App 的首页 UI。包含账户总余额、多张银行卡切换、最近 5 条交易记录，以及“转账 / 充值 / 理财”三个主要操作入口。整体风格需要专业、安全、可信，信息层级清晰，适合高频查看。 | <a href="assets/examples/ui-design-output.png"><img src="assets/examples/ui-design-output.png" width="220" alt="UI design"></a> |
| Reasoning-based image generation | 画一下当前比较流行的3款女装，输出3个图像，要求分别以3个分别来自亚洲、欧洲和美洲的知名建筑为背景，天气分别为这3个知名建筑所在地的实时天气，分别在顶部、中部和下部写上数学、物理、化学的知名公式。 | <a href="assets/examples/reasoning-image-output.png"><img src="assets/examples/reasoning-image-output.png" width="260" alt="Reasoning-based image generation"></a> |
| Knowledge card | 请创建一个 1080×1920 像素的英语单词学习卡片网页，输出一个可直接在浏览器打开的完整 HTML。风格为治愈卡通描边，色彩柔和但稍微明快，画面简洁不拥挤。上半部分为满幅贴边的治愈卡通插图，不允许圆角、外框、白边、卡片边或 UI 面板；下半部分居中展示音标、中文释义、英文例句和中文翻译，并将目标单词标红。示例单词：apple。 | <a href="assets/examples/knowledge-card-output.jpg"><img src="assets/examples/knowledge-card-output.jpg" width="180" alt="Knowledge card"></a> |

## Test

```bash
.venv/bin/python -m unittest discover -s unit_test -v
.venv/bin/python -m pip check
```

## Project Layout

```text
apps/          CLI entry points
conf/          local runtime configuration
server/        FastAPI app, routers, services, local web UI
src/           agent implementations and expert tools
unit_test/     lightweight tests for local mode
web/           React/tldraw browser UI source
```

Runtime files are generated locally and ignored by git:

```text
.venv/
database/
logs/
outputs/
uploads/
__pycache__/
```

## Notes

- This local version does not require Docker, Redis, login, billing, or a worker
  queue.
- The browser UI is built from `web/` into `server/static/`.
- Chat requests need valid provider keys in `.env`; the home page and session
  APIs can start without them.
