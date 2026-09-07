# Knowledge Video Studio

输入主题，选择参考声音，确认 HTML 课件或参考模板，制作带配音、字幕和章节的知识视频。

这是一个本地网页工作台。内容步骤可以使用本机登录的 Codex，也可以使用 OpenAI 兼容的外部大模型接口。视频节奏由真实口播音轨决定。修改播放速度时，音高保持不变，字幕和翻页使用同一时间变换。

## 先看清它能做什么

- **主题到成片**：学习目标、参考资料、讲稿、内容审查、课件生成、版式检查、克隆配音、逐字对齐、转写复核、字幕、1080p MP4。
- **两种课件输入**：参考模板生成新 HTML；或读取已有 HTML 的页面顺序，为现有课件生成口播。已有文件不被覆盖。
- **两种模型入口**：本机 `codex exec`；外部 `/chat/completions`（按填写的 Base URL 追加）。模型名可配置，Codex 留空时沿用用户配置。
- **保留进度**：任务、资料快照、模型输出、声音缓存、源音轨和检查结果保存在 `.studio/`。重启后的中断任务可以继续。
- **有限自动修复**：结构错误重试、课件版式修复、逐段配音重做、整句遗漏和数字转写复核。不会调低声学门槛来制造成功。
- **清楚的交付**：视频、SRT、口播稿、资料来源、章节和质量报告。建议发布前完整试听。

它不保证任意主题都能无人审核发布。资料不可访问、核心论点缺证据、录音无法识别、课件不兼容或重复修复失败时，任务会停止并保留结果。目前重点支持中文、macOS 和 Linux。本地 GPU 能明显改善语音生成速度。Windows 建议先在 WSL 中部署，尚未做原生验收。

## 安装与启动

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

本项目通过 REST 连接 [OmniVoice Studio](https://github.com/Galest/OmniVoice-Studio)。请按照上游项目说明安装并启动服务，默认地址 `http://127.0.0.1:3900`。语音模型和 tokenizer 权重首次使用时需要下载，**模型状态必须为 loaded=true**。

工作台不会修改上游项目源码或依赖。服务空闲卸载模型后，需要在 OmniVoice 中重新加载或重启你自己的服务。不要使用会清空数据的上游 smoke-test 脚本作日常检查。

网页可上传参考录音、指定本机路径，或填写已有声音档案 ID。推荐 6 至 20 秒、发音清楚且音量稳定的本人或授权录音。录音逐字稿可手动填写；留空则用本地 faster-whisper 识别。识别模型首次使用也会下载。

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

- [完整工作流与 LLM 角色](docs/WORKFLOW.md)
- [架构和扩展入口](docs/ARCHITECTURE.md)
- [验收记录](docs/ACCEPTANCE.md)
- [数据与部署边界](docs/SECURITY.md)
- [第三方组件](THIRD_PARTY.md)

MIT License。模型权重、语音服务、字体、用户模板与内容各自遵循其原有许可。
