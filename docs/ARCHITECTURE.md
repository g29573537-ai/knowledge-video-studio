# 架构与扩展

## 目录

- `knowledge_video/static/`：网页前端，无构建依赖。
- `knowledge_video/server.py`：本机 API、上传、课件预览、任务和产物访问。
- `knowledge_video/jobs.py`：持久任务状态、单任务工作队列、取消和重启续跑。
- `knowledge_video/workflow.py`：显式工作流与阶段产物。
- `knowledge_video/providers.py`：Codex CLI 与外部 Chat Completions 的统一结构化接口。
- `knowledge_video/prompts.py`：研究、写稿、编辑、课件、视觉与转写复核指令。
- `knowledge_video/models.py`：请求和阶段输出模型。
- `knowledge_video/materials.py`：资料抓取、HTML 分页识别、资源打包。
- `knowledge_video/media.py`：重型音频子进程与失败段落重做。
- `narration_video/`：独立的配音、对齐、变速、字幕和渲染引擎。

## 任务与缓存

每次启动生成一个独立任务 ID。输入保存在 `request.json`，API Key 从持久副本删除。任务输出默认位于 `.studio/jobs/<id>/`。模型输出按阶段文件缓存；声音缓存包含输入、模型、语速、真实参考音频哈希和参考稿。内容阶段由模型 schema 校验，媒体阶段保留声学证据。

取消会终止当前任务拥有的子进程组；一次正在等待返回的外部 HTTP 请求可能需要等待其配置超时。服务重启后会把未完成任务标记为 interrupted。继续任务会复用已经完成的阶段和缓存。修改主题、模板或声音等输入时应新建任务，避免把旧的模型结果当成新任务的结果。

队列一次运行一个视频任务，避免多个模型竞争显存。HTTP 服务仍可以响应状态和取消操作。当前是单机单服务进程设计，不应启动多个服务进程共享同一数据目录。

## 模型接口

所有内容阶段调用 `Provider.generate(instruction, payload, result_model, images)`。新增供应商时在此实现即可，不需要改时间轴引擎。

- Codex：stdin 输入，结构化 schema，临时输出文件，本机认证。优先使用用户显式 `CODEX_BIN`；否则比较 PATH 与 macOS 应用自带的可执行文件。
- 外部接口：用户提供 base URL 与模型，支持 schema、object、prompt 三种 JSON 输出模式。可选图片输入。当前不宣称支持所有供应商特有工具调用。

资料搜索采用模型提出候选权威 URL、程序实际抓取并返回正文的方式。用户可追加参考网址和资料笔记。候选 URL 没有成功抓取时不会被当成已验证来源。它不是一个完整搜索引擎；需要检索召回、PDF 或企业知识库时应扩展 `materials.py`，并继续保留来源 ID 与正文快照。

## API

- `GET /api/system`：依赖与默认语音服务状态。
- `POST /api/upload`：参考录音上传。
- `POST /api/slides/inspect`：读取本机 HTML 页序并返回预览。
- `POST /api/jobs`：创建任务，请求结构见 `JobRequest`。
- `GET /api/jobs`、`GET /api/jobs/{id}`：列表与状态。
- `POST /api/jobs/{id}/cancel`、`POST /api/jobs/{id}/resume`。
- `GET /artifacts/{id}/...`：只提供成片、字幕、讲稿、资料文案、章节、报告和页面资源。

POST 请求必须携带 `X-Studio-Client: 1`。浏览器界面自动提供。服务仅绑定 loopback，不是面向多租户公网部署的服务。
