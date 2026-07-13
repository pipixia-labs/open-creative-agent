<div align="center">

<h1>🎨 Open Creative Agent</h1>

<p><strong>把一句粗略的想法，变成可交付的视觉作品 —— 海报、商品图、图文文章、UI 设计稿、短视频，全部在一个本地"聊天 + 画布"工作台里完成。</strong></p>

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

**Open Creative Agent（OCA）** 是一个开源、本地优先的**多智能体创意工作室**。你用自然语言描述目标 —— 需求、受众、文案、素材、约束条件 —— 编排器（orchestrator）会把任务规划并分发给 **20 个专家智能体**：搜索调研、设计知识、图像生成与编辑、视频、图文文章、海报、网页与 UI 页面。生成结果直接落在聊天旁边的 [tldraw](https://tldraw.dev) 无限画布上，可以随时查看、追问修改、下载。

一次 `git clone`，一个脚本，一个浏览器标签页。不需要 Docker、不需要注册账号、没有云端依赖。

<table align="center">
  <tr>
    <td align="center"><a href="assets/examples/poster-edit-final.png"><img src="assets/examples/poster-edit-final.png" height="210" alt="多轮对话打磨的海报"></a></td>
    <td align="center"><a href="assets/examples/amazon-product-output.png"><img src="assets/examples/amazon-product-output.png" height="210" alt="亚马逊商品图组"></a></td>
    <td align="center"><a href="assets/examples/ui-design-output.png"><img src="assets/examples/ui-design-output.png" height="210" alt="银行 App 首页 UI"></a></td>
    <td align="center"><a href="assets/examples/knowledge-card-output.jpg"><img src="assets/examples/knowledge-card-output.jpg" height="210" alt="单词学习卡片"></a></td>
  </tr>
</table>

## 从这里开始

| 你想…… | 看这里 |
| --- | --- |
| 5 分钟在本机跑起来 | [快速开始](#-快速开始) |
| 看看它能做出什么 | [作品展示](#%EF%B8%8F-作品展示) |
| 了解它和别的工具有什么不同 | [为什么选 OCA](#-为什么选-open-creative-agent) |
| 配置 API key、模型、端口 | [配置文档](docs/configuration.md) |
| 阅读代码、跑测试、参与贡献 | [开发文档](docs/development.md) |

## 📢 动态

- **2026-07** 🎉 首个开源版本发布：本地"聊天 + 画布"工作台，编排器调度 20 个专家智能体，端到端生成海报、商品视觉、图文文章、UI 页面和视频。

## 💡 为什么选 Open Creative Agent

- **写需求，而不是拼 prompt。** 直接把真实的需求写出来 —— 受众、文案、商品图、风格约束 —— 编排器会拆解任务，并把每个环节路由给对应的专家智能体。
- **完整的创作流水线。** 搜索 → 设计推理 → 素材生成 → 编辑 → 排版 → 渲染。营销图组、图文文章、详情页拿到手就是组装好的成品，而不是零散的片段。
- **文字真的不会错。** 海报、长图、知识卡片、UI 页面这类版式敏感的输出，先组装成网页再渲染成像素，标题、日期、正文清晰准确 —— 避开了纯文生图"文字乱码"的经典翻车点。
- **用对话来改稿。** "标题居中、放大 1.5 倍、去掉二维码" —— 追加一句话就能在上一版基础上继续改，而不是从头重新生成。
- **聊天 + 画布并排。** 生成的媒体落在可拖拽、可缩放的 tldraw 无限画布上，方便排列和对比版本；规划和进度实时显示在右侧聊天栏。
- **本地优先，方便魔改。** 一个 FastAPI 进程托管全部 API 和 React UI。基于 [google-adk](https://github.com/google/adk-python) 的可读 Python 代码，模型供应商可插拔，无任何托管依赖。

## 🖼️ 作品展示

以下作品全部由 OCA 根据一条需求生成（标注处含多轮修改）。点击图片看大图。

<table>
  <tr>
    <td align="center" width="33%">
      <a href="assets/examples/poster-edit-final.png"><img src="assets/examples/poster-edit-final.png" width="230" alt="对话式海报修改"></a>
      <br><b>海报（4 轮对话打磨）</b>
      <br><sub>"针对27届高交会做一个海报，相关信息可以搜索一下" → "标题居中、颜色醒目、字体放大1.5倍" → "标题换个好看的颜色，其他文字下移改黑色" → "去掉二维码"。</sub>
    </td>
    <td align="center" width="33%">
      <a href="assets/examples/amazon-product-output.png"><img src="assets/examples/amazon-product-output.png" width="230" alt="亚马逊商品图组"></a>
      <br><b>亚马逊商品图组</b>
      <br><sub>根据一张商品图生成主图、多视角图、场景图、细节图和英文文案，商品保持与输入完全一致。</sub>
    </td>
    <td align="center" width="33%">
      <a href="assets/examples/reasoning-image-output.png"><img src="assets/examples/reasoning-image-output.png" width="230" alt="推理式图像生成"></a>
      <br><b>需要推理的图像生成</b>
      <br><sub>画 3 款流行女装，分别以亚洲、欧洲、美洲知名建筑为背景，天气为当地实时天气，并在顶部、中部、下部写上数学、物理、化学知名公式。</sub>
    </td>
  </tr>
  <tr>
    <td align="center">
      <a href="assets/examples/art-illustration-set.png"><img src="assets/examples/art-illustration-set.png" width="230" alt="艺术插画系列"></a>
      <br><b>插画系列</b>
      <br><sub>四幅拼贴风格插画，把美丽风景拼贴进可爱动物剪影，色彩明亮、有视觉冲击力。</sub>
    </td>
    <td align="center">
      <a href="assets/examples/ui-design-output.png"><img src="assets/examples/ui-design-output.png" width="230" alt="UI 设计"></a>
      <br><b>移动端 App UI</b>
      <br><sub>银行 App 首页：账户总余额、多卡切换、最近交易、转账/充值/理财入口，风格专业可信、信息层级清晰。</sub>
    </td>
    <td align="center">
      <a href="assets/examples/knowledge-card-output.jpg"><img src="assets/examples/knowledge-card-output.jpg" width="230" alt="知识卡片"></a>
      <br><b>知识卡片</b>
      <br><sub>1080×1920 英语单词卡网页：上半部治愈卡通插图，下半部音标、释义、例句，目标单词标红。</sub>
    </td>
  </tr>
  <tr>
    <td align="center">
      <a href="assets/examples/long-form-visual.png"><img src="assets/examples/long-form-visual.png" width="230" alt="竖版长图"></a>
      <br><b>竖版长图</b>
      <br><sub>介绍中国历代王朝的竖版长图，每个朝代配一段简介。</sub>
    </td>
    <td align="center">
      <a href="assets/examples/marketing-article-output.jpg"><img src="assets/examples/marketing-article-output.jpg" width="230" alt="营销文章"></a>
      <br><b>图文营销文章</b>
      <br><sub>针对给定商品生成小红书风格营销文章，配图由内部智能体一并生成，端到端完成。</sub>
    </td>
    <td align="center">
      <a href="assets/examples/event-text-poster.png"><img src="assets/examples/event-text-poster.png" width="230" alt="活动文字海报"></a>
      <br><b>文字精准的活动海报</b>
      <br><sub>展会海报：地点、时间、主办方等文字与输入完全一致，标题醒目、零错别字。</sub>
    </td>
  </tr>
</table>

## 🚀 快速开始

环境要求：**Python 3.14+**、**Node.js + npm**、macOS 或 Linux，以及一个 [Google AI Studio API key](https://aistudio.google.com/apikey)（免费额度即可跑通）。

```bash
git clone https://github.com/GML-FMGroup/open-creative-agent.git
cd open-creative-agent
cp .env.template .env      # 在 .env 里填入 GOOGLE_API_KEY
./scripts/start_local.sh
```

然后打开 **http://127.0.0.1:9502**，描述你想做的东西。

首次启动需要几分钟：创建 `.venv`、安装 Python 与前端依赖、构建 React UI、启动服务。之后的启动会快很多 —— 见[启动参数](docs/configuration.md#startup-flags)。

只配 Gemini 一个 key 就能覆盖规划、写作、网页生成和 Nano-Banana 图像生成。其他可选 key 解锁更多工具 —— Seedream/Seedance 图像与视频（火山方舟）、联网搜索（Tavily）、GPT 文章写手。详见[供应商对照表](docs/configuration.md#model-keys)。

## 🖥️ 工作台

<p align="center">
  <a href="assets/workspace.png"><img src="assets/workspace.png" width="860" alt="Open Creative Agent 工作台：左侧 tldraw 画布，右侧聊天"></a>
</p>

- **左侧画布。** 生成的图像、渲染的页面、视频都是真实的 tldraw 对象：可拖动、排列、缩放、对比版本。
- **右侧聊天。** 需求、执行计划、可展开的思考步骤和进度都在这里；可直接上传商品图或参考图。
- **原地迭代。** 每条追加消息都在当前上下文里继续改稿。
- **随时下载。** 成品文件由本地应用直接提供下载。

## 🏗️ 工作原理

一个 FastAPI 进程同时提供 API 和构建好的 React UI。每条聊天请求先经过**编排器**做任务规划，再由**执行器**把步骤分发给 **20 个专家智能体** —— 联网搜索、设计知识、营销文案、文生图与图像编辑（Nano Banana / Seedream）、推理式生成、视频（Veo / Seedance）、图像理解与 OCR、背景去除、图文文章、海报、参考图复刻、UI 生成、HTML 页面生成、HTML 渲染成图。会话状态存在本地 SQLite，生成的文件都留在你自己的磁盘上。

架构细节、项目结构与验证命令：[docs/development.md](docs/development.md)。

## 📚 文档

- [配置](docs/configuration.md) —— 各 API key 及其解锁的能力、模型选择、端口、启动参数。
- [开发](docs/development.md) —— 手动启动、架构、项目结构、测试、贡献说明。

## 🤝 贡献与路线图

代码库刻意保持小而可读 —— 一个服务、一个 UI、一个 agent 包。欢迎 PR 和 issue。

欢迎一起做的方向：

- **PPT / 幻灯片导出** —— 为本地版带回幻灯片生成能力
- **深度调研智能体** —— 长程调研报告，反哺创意生产
- **更多模型供应商** —— 接入更多图像、视频与 LLM 后端
- **Windows 支持** —— 在 shell 脚本之外提供原生启动路径
- **UI 打磨与国际化** —— 工作台还年轻，迭代很快

## ⭐ Star 历史

<div align="center">
  <a href="https://star-history.com/#GML-FMGroup/open-creative-agent&Date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=GML-FMGroup/open-creative-agent&type=Date&theme=dark" />
      <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=GML-FMGroup/open-creative-agent&type=Date" />
      <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=GML-FMGroup/open-creative-agent&type=Date" />
    </picture>
  </a>
</div>

<p align="center"><em>如果 OCA 帮你做出了满意的作品，点个 ⭐ 能让更多人发现它。</em></p>
