# Open Creative Agent

<div align="center">
  <p><strong>Turn a rough creative brief into finished visual work.</strong></p>
  <p>
    Open Creative Agent is a local-first creative agent workspace for posters,
    product visuals, UI mockups, knowledge cards, marketing articles, and
    long-form visual assets.
  </p>
  <p>
    <img src="https://img.shields.io/badge/runtime-local--first-2f855a" alt="Local-first runtime">
    <img src="https://img.shields.io/badge/UI-React%20%2B%20tldraw-2563eb" alt="React and tldraw UI">
    <img src="https://img.shields.io/badge/Python-3.14-3776ab" alt="Python 3.14">
  </p>
</div>

Open Creative Agent (OCA) gives you a chat-driven creative workflow with a
movable canvas. Describe the outcome, provide constraints, iterate in natural
language, and keep the generated images or web artifacts in one local browser
workspace.

This repository is the open-source local version. It runs as a single FastAPI
server and serves the React/tldraw web UI from the same local process.

## Start Here

| You want to... | Start with |
| --- | --- |
| Try the app locally | [Download And Run](#download-and-run) |
| See what it can produce | [Examples](#examples) |
| Understand the main value | [Why Open Creative Agent](#why-open-creative-agent) |
| Configure model keys and ports | [Configuration](docs/configuration.md) |
| Customize or contribute | [Development](docs/development.md) |

## Why Open Creative Agent

- **Brief-first creation**: write the real goal, audience, copy, source
  material, and style constraints instead of only a narrow image prompt.
- **Canvas plus chat**: generated media appears on the left canvas while the
  conversation stays on the right, so results are easy to inspect, move, and
  refine.
- **Multi-step creative work**: the orchestrator can plan, research, write,
  generate, and edit across multiple specialist agents.
- **Local deployment**: no Docker, Redis, login system, billing layer, or hosted
  worker queue is required for the local open-source version.
- **Useful output formats**: create product listing visuals, campaign posters,
  illustrated articles, UI mockups, knowledge cards, long images, and browser
  pages.

## Examples

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

## Download And Run

Requirements:

- Python 3.14
- Node.js and npm
- macOS or Linux shell environment
- At least one model provider API key

Clone the repository:

```bash
git clone https://github.com/GML-FMGroup/open-creative-agent.git
cd open-creative-agent
```

Create your local environment file:

```bash
cp .env.template .env
```

Edit `.env` and set at least one model key. The default setup uses Gemini, so
`GOOGLE_API_KEY` is the first key to configure:

```env
GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY"
```

Start OCA:

```bash
./scripts/start_local.sh
```

Open the local web app:

```text
http://127.0.0.1:9502
```

The first startup may take a few minutes because the script creates `.venv`,
installs Python packages, installs web dependencies, builds the React UI, and
starts the local server.

## What The App Feels Like

The main screen is intentionally simple:

- a tldraw canvas on the left for generated images, web pages, and other media;
- a chat panel on the right for instructions, planning, progress, and final
  answers;
- follow-up editing through the same conversation;
- local output files served from the running app.

## Documentation

- [Configuration](docs/configuration.md): API keys, local server settings, and
  startup flags.
- [Development](docs/development.md): manual startup, project layout, tests, and
  contribution notes.

## Project Status

OCA is an early open-source local version of a larger creative-agent system. The
focus of this repository is a runnable local workflow, clean UI, and practical
creative output. Some provider-specific tools require their own API keys.
