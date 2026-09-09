# Knowledge Video Studio

输入主题，选择参考声音，确认 HTML 课件或参考模板，制作带配音、字幕和章节的知识视频。

参考网址和资料摘要均可留空。系统会尝试获取参考资料；没有可用资料时，依据稳定的通用知识、透明的推导和标为假设的教学算例继续。不会伪造引用或实测结果，内容仍经过审稿。质量报告和视频说明会注明通用知识模式。

这是一个本地网页工作台。内容步骤可以使用本机登录的 Codex，也可以使用 OpenAI 兼容的外部大模型接口。视频节奏由真实口播音轨决定。修改播放速度时，音高保持不变，字幕和翻页使用同一时间变换。

## 先看清它能做什么

- **主题到成片**：学习目标、参考资料、讲稿、内容审查、课件生成、版式检查、克隆配音、逐字对齐、转写复核、字幕、1080p MP4。
- **两种课件输入**：参考模板生成新 HTML；或读取已有 HTML 的页面顺序，为现有课件生成口播。已有文件不被覆盖。
- **两种模型入口**：本机 `codex exec`；外部 `/chat/completions`（按填写的 Base URL 追加）。模型名可配置，Codex 留空时沿用用户配置。
- **保留进度**：任务、资料快照、模型输出、声音缓存、源音轨和检查结果保存在 `.studio/`。重启后的中断任务可以继续。
- **有限自动修复**：结构错误重试、课件版式修复、逐段配音重做、整句遗漏和数字转写复核。不会调低声学门槛来制造成功。
- **清楚的交付**：视频、SRT、口播稿、资料来源、章节和质量报告。建议发布前完整试听。

它不保证任意主题都能无人审核发布。核心内容包含无法核实的具体事实、录音无法识别、课件不兼容或重复修复失败时，任务会停止并保留结果。目前提供中文、英语、日语、韩语、法语、德语、西班牙语、意大利语、葡萄牙语和俄语的完整语言配置，支持 macOS 和 Linux。本地 GPU 能明显改善语音生成速度。Windows 建议先在 WSL 中部署，尚未做原生验收。

## 安装与启动

### 一键安装（推荐）

克隆仓库后，在仓库根目录执行：

```sh
./scripts/install
./scripts/start
```

第一条命令自动准备 uv / Python 3.11，把指定版本的 OmniVoice Studio 拉取到 `.runtime/omnivoice`，按上游锁文件安装依赖，再安装视频工作台。Node.js 低于 22 时下载校验过的官方运行时。不会改动其他目录的 OmniVoice。第二条命令启动语音服务与工作台，打开 **http://127.0.0.1:8770/**。停止启动命令会关闭它自己启动的子进程，已有语音服务保持运行。

macOS 缺少系统工具时使用已有 Homebrew 安装 Git、FFmpeg 和 Chrome；没有 Homebrew 时需先安装它。Debian/Ubuntu 使用 apt，可能要求 sudo。Linux 需要可工作的 Chrome/Chromium 和中文字体，其他发行版自行准备系统依赖。也可用 `./scripts/install --skip-system-deps` 跳过系统工具安装。仅查看计划可运行 `python3 scripts/install.py --dry-run`。WSL 仍需按 Linux 环境准备，Windows 原生安装未验收。

安装程序固定 OmniVoice 源码提交，使用 `uv sync --frozen` 复用其已知依赖锁文件。上游该提交的项目版本号与锁文件元数据存在差异，使用 `--locked` 会拒绝安装。这里不重算上游依赖，实际验收确认了新环境的导入、服务启动、模型加载和英文媒体导出。

模型权重不包含在 Git 中。首次启动后展开“模型与服务设置”，选择视频语言和识别模型，点击“下载所选语言模型”，完成后点击“载入模型”。下载失败保留缓存，可重新点击继续。默认端口已占用时启动器不会终止已有服务；可用 `./scripts/start --port 8771 --voice-port 3901` 另行启动。


### 1. 系统依赖

需要 Python 3.11、Node.js 22+、FFmpeg / FFprobe、Chrome 或 Chromium，以及中文字幕字体。

macOS：

```sh
brew install python@3.11 node ffmpeg
# 安装 Google Chrome；系统通常已经有 PingFang 中文字体。
```

Ubuntu / Debian：

```sh
sudo apt-get update
sudo apt-get install ffmpeg fonts-noto-cjk chromium
# 另外安装 Node.js 22+ 和 Python 3.11。
```

Chrome 自动发现失败时设置 `CHROME_BIN`，或在网页中填写路径。中文字幕字体可在网页中填写。

### 2. Python 项目

在克隆的仓库根目录执行：

```sh
python3.11 -m venv .venv
. .venv/bin/activate
pip install -e '.[media,dev]'
knowledge-video doctor
knowledge-video serve
```

打开 **http://127.0.0.1:8770**。前端是随包提供的静态文件，不需要前端构建或云托管。

如果已经有安装 WhisperX 的独立语音环境，可以用该环境安装本项目，或临时执行：

```sh
STUDIO_PYTHON=/path/to/python ./scripts/dev
```

不要把个人录音、登录状态或 API Key 加入仓库。`.studio/`、`.env`、媒体和构建目录默认排除。

### 3. 克隆声音服务

本项目通过 REST 连接 [OmniVoice Studio](https://github.com/Galest/OmniVoice-Studio)。可以使用上面的一键安装，也可以按上游说明独立安装，默认地址 `http://127.0.0.1:3900`。语音模型和 tokenizer 权重首次使用时需要下载，**模型状态必须为 loaded=true**。

工作台运行时不会修改上游项目源码或依赖；一键安装仅操作自己的 `.runtime/` 环境。服务空闲卸载模型后，工作台会调用 `/setup/warmup` 自动唤醒，并等待实际 `loaded=true` 后才进入配音。若加载失败或超时，保留任务进度并显示具体错误。不要使用会清空数据的上游 smoke-test 脚本作日常检查。

网页可上传参考录音、指定本机路径，或填写已有声音档案 ID。推荐 6 至 20 秒、发音清楚且音量稳定的本人或授权录音。录音逐字稿可手动填写；留空则用本地 faster-whisper 识别。识别模型首次使用也会下载。

## 多语言模型

[OmniVoice 官方模型](https://huggingface.co/k2-fsa/OmniVoice) 本身支持多语言克隆。前端的语言选项共用 `k2-fsa/OmniVoice` 和音频 tokenizer，分别准备 WhisperX 对齐模型。模型面板提供 Whisper Small、Medium、Large v3 三档多语言识别权重，可以选择下载并加载。准备进度按四个实际步骤显示，不把步骤进度当作下载字节百分比。语音服务的当前 loaded/loading 状态单独显示。

视频语言控制口播稿、课件文字、TTS、ASR 复核和字幕对齐。参考录音语言可以独立选择或自动识别，因此可以用中文样例生成英文口播。跨语言的口音和音色相似度仍建议试听。英文字幕保留空格和单词边界。

目前前端开放有对应强制对齐模型的十种语言。中文生产链与英文媒体链已经实测，其他八种语言具备配置入口，尚未逐种完成听感与成片验收；不把上游的语言覆盖数量当作本项目已验证的数量。模型下载和加载期间暂不同时启动视频任务，避免争抢内存。

## 使用自己的 Codex

先安装兼容当前模型的 Codex CLI，然后登录：

```sh
codex login
codex login status
```

网页选择 **Codex CLI**，模型名可以留空。程序使用 `codex exec --ephemeral --sandbox read-only --output-schema ...`，通过 stdin 提交内容并获取结构化结果。沿用本机登录状态，正常使用账户额度。不会复制、读取或打包 `auth.json`。

如果系统 CLI 较旧，程序会比较已安装 CLI 与 macOS 应用附带程序的版本。也可以显式指定：

```sh
CODEX_BIN=/path/to/codex knowledge-video serve
```

如果在 Codex 中打开此仓库，可以直接说：

> 检查环境并启动网页。我会在网页中选择录音和模板，然后制作一条知识视频。

也可以让 Codex 生成请求 JSON 后使用 CLI：

```sh
knowledge-video run examples/request.json --output .studio/manual/my-lesson
```

有关认证与结构化输出，见 [Codex 非交互调用官方文档](https://learn.chatgpt.com/docs/non-interactive-mode)。这里面向用户自己的本地登录；不要把个人登录状态分发给别人或放进公共 CI。

## 外部大模型

展开网页右上角“模型与服务设置”，选择外部模型，填写：

- Base URL，例如 `https://your-provider.example/v1`，程序追加 `/chat/completions`。
- 模型名。
- API Key，或给服务进程设置 `KNOWLEDGE_VIDEO_API_KEY`。
- JSON Object、JSON Schema 或纯提示词模式。
- 是否支持图片输入。支持时会发送课件截图参与版式检查；不支持时只做结构报告与文本检查。

DeepSeek V4 Flash 已完成真实供应商调用。设置 Base URL 为 `https://api.deepseek.com`、模型为 `deepseek-v4-flash`、JSON Object，关闭图片输入。课件代码生成默认使用该模型的 `low` 推理强度；请求 JSON 的 `provider.reasoning_effort` 可显式覆盖。内容审查沿用供应商默认强度。调用记录只保存模型名和用量，不保存密钥或思考内容。完整生产验收见下方验收记录。

外部模型会接收主题、资料正文、讲稿和模板；启用视觉检查后会接收课件截图。参考录音只发给指定的语音服务。网页输入的 Key 只保留在服务内存，重启后需重新输入或使用环境变量。浏览器不保存 Key。

## 课件约定

生成新课件时，可以点击本机品牌模板、通用教学模板，或选择“自定义模板”填写 HTML 的完整路径。品牌模板点击后自动检查并预览，自定义路径需要点击“检查并预览课件”。预览按 1920×1080 等比缩放。

本机模板库位于 `.studio/templates/<名称>/`，其中 `template.json` 使用 `{"name":"品牌名","description":"样式说明","file":"slides.html"}`，HTML 与离线资源放在同一模板目录。接口只列出目录内存在的文件。此目录不进入源码分发，可用它配置自己的 Zero2Quant 或其他品牌模板。

自动生成的课件使用 HTML/CSS/SVG，默认黑底教学模板可替换。不调用图片生成服务。

已有课件优先支持：

1. 实现 `window.setPresentationState({slide, visible, highlight})` 的 HTML。
2. 常规横向 Reveal.js 课件。
3. 顶层 `section` 分页的静态 HTML，程序会在私有副本中注入切页适配。

每页应有唯一 `id`。不支持直接读取 PPTX、复杂嵌套 Reveal 纵向页序、连续视频、Canvas 动画录制或任意网页自动猜测分页。资源打包按 HTML/CSS 中显式引用的资源逐项复制，不会把用户父目录整个复制进任务。JavaScript 动态拼接的资源地址需要自行整理为相对静态地址。需要联网加载的已有课件仍依赖其网络资源，建议使用离线版本。

截图会等待字体、图片、有限动效和布局稳定，再检查文字是否被视口或父容器裁切。无限动画、持续变化的数据页面不属于静态课件支持范围。

前端选择“使用已有 HTML”后填写完整路径，点击“检查并预览课件”，确认页数和预览，再开始制作。

## 开发与测试

```sh
pip install -e '.[dev]'
pytest -q
node --check knowledge_video/static/app.js
node --check narration_video/render_deck.mjs
python -m build
```

测试包含真实 FFmpeg 导出、保持音高的变速、字幕时钟、漏句检测、缓存、已有 HTML 资源打包、外部接口 HTTP 契约、本机 API 边界、任务恢复和子进程取消。外部接口测试使用本地协议服务，不等于所有供应商都已实际验证。

- [完整工作流与 LLM 角色](WORKFLOW.md)
- [架构和扩展入口](ARCHITECTURE.md)
- [验收记录](ACCEPTANCE.md)
- [数据与部署边界](SECURITY.md)
- [第三方组件](../THIRD_PARTY.md)

MIT License。模型权重、语音服务、字体、用户模板与内容各自遵循其原有许可。

### 自动封面与发布简介

视频完成后，系统使用同一模型入口，根据已审查的讲稿生成封面标题、副标题、发布简介和主题标签。封面在本地排成 1920×1080 PNG，包含课件预览，并沿用模板的背景与品牌。章节时间来自实际音轨，资料链接来自任务资料，不由模型编造。

结果页提供封面预览、PNG 下载、简介复制和 TXT 下载。历史视频可以点击“生成封面与简介”，再次点击则生成新版本，无需重做配音和视频。生成失败时保留已完成成片和上一版素材，可以单独重试。外部模型的密钥仍只在内存中使用。所有素材只保存到本地，不自动发布到平台。
