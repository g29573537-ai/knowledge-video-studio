# 让当前助手直接制作

这条路径适合在 Codex 等支持本机工具的助手中打开仓库，直接完成写稿、审查和课件。内容由当前会话编写，声音与时间轴仍使用项目的真实媒体 CLI。不要把它称为网页自动供应商模式，也不要手工伪造成功的网页任务。

可以给助手这样的任务：

> 阅读 AGENTS.md 和工作流文档。用我的授权声音样例和指定 HTML 模板制作主题视频。由当前会话写稿并审查，不再调用其他内容模型。所有文件放进独立 .studio 任务目录。先做自然口播，再让字幕和翻页跟随声音；保留源音轨，播放速度1.2。检查真实视频画面与转写，交付讲稿、课件、视频、字幕、来源、章节、封面和简介。

## 准备媒体项目

先按 README 安装并启动服务。在网页上传参考声音并完成一次声音准备，或在自己的 OmniVoice Studio 中创建声音档案。使用该服务中的实际 `profile_id`，不能复制他人的 ID。准备模型权重并确认语音服务能够加载。

复制公共示例：

```sh
mkdir -p .studio/manual
cp -R examples/assistant .studio/manual/my-lesson
```

修改 `.studio/manual/my-lesson/project.json` 的 `voice.profile_id`。修改 `narration.md` 和 `slides.html` 来适配主题。Chrome 找不到时，在项目 JSON 中填写 `chrome` 路径。

`narration.md` 中 `## opening` 定义一个自然段，`[[opening]]` 标记下一发声字符对应的页面切换。项目的 `cues.opening.slide` 必须与 HTML 页 ID 一致。同一自然段可放置多个切页标记；不要为了每个动画碎片拆成语音请求。示例未携带任何真实录音。

## 运行与审查

在安装产生的环境中执行（以下是 macOS/Linux 路径）：

```sh
.runtime/omnivoice/.venv/bin/python -m knowledge_video.media produce .studio/manual/my-lesson/project.json --repairs 2
.runtime/omnivoice/.venv/bin/python -m knowledge_video.media transcribe .studio/manual/my-lesson/project.json
```

`produce` 会检查真实声音身份、生成或复用语音、执行有限对齐修复，并输出 `build/video.mp4`、`subtitles.srt`、源音轨、时间轴和报告。它不调用内容 LLM，也不会自动审查讲稿事实或生成封面简介。

`transcribe` 输出 `build/speech_asr.json`。助手需要逐段比较预期文本与转写，区分识别错字和实际漏读。有疑问时检查音频片段，不凭相似度一个数字宣告通过。修改口播后重跑 `produce`，未变化的段落会复用缓存；完成后再运行 `transcribe`，确认审查对应的是最终音频。

讲稿与事实审查还应保存来源、假设和数字推导。发布素材可用 `knowledge_video.publishing.PublishingCopy`、`cover_html` 和 `description_text` 由当前助手填入已审定文案后生成；封面仍须渲染和检查。章节时间取自 `build/timeline.json`，不能手写估算时间。

完成前检查声音档案与参考音频哈希、字幕全文、视频尺寸与时长、实际成片截图和播放。独立媒体目录不会自动注册到网页任务列表。需要网页管理时，请使用网页正常创建任务并选择其支持的模型入口。

## 与网页 Codex 模式的区别

网页使用 `Provider.generate` 调用独立的 `codex exec` 进程，通过 stdin 传入材料，并要求结构化输出。当前助手方式由会话自行操作媒体项目。两条路径都复用媒体引擎，但内容审查和交付责任不同。Codex 的非交互输出约定参见[官方文档](https://learn.chatgpt.com/docs/non-interactive-mode)。
