# 铁塔运维知识库 RAG 框架

按 [代码架构设计 V1](docs/architecture-v1.md) 实现的第一版本地后端。Python 3.11+，建议 3.12。使用 FastAPI + SQLite + 文件对象存储，无需 GPU、外部模型、Redis 或数据库服务。

**这是可运行的本地开发基线，不是完整生产实现。** 本地哈希向量不等于 BGE 语义向量，词项匹配不等于 Elasticsearch BM25，原文摘录不等于 Qwen 生成。所有问答返回 `degraded=true` 并标明基线限制。禁止直接用于指导现场危险操作。

## 快速开始

在仓库已有 checkout 中操作，无需创建 worktree：

```bash
cd /workspace/my_test/RAG
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
# 生成当前开发会话使用的随机口令，不要提交口令或 .env
export TOWER_DEV_TOKEN="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export TOWER_DATA_DIR="$PWD/.runtime"
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/smoke.py
.venv/bin/uvicorn tower_kb.main:app --host 127.0.0.1 --port 8000
```

另一个终端启动 Worker，须设置**相同**的 `TOWER_DEV_TOKEN` 和绝对路径 `TOWER_DATA_DIR`：

```bash
cd /workspace/my_test/RAG
.venv/bin/python -m tower_kb.workers.tasks
# 或单次处理：.venv/bin/python -m tower_kb.workers.tasks --once
```

API 与 Worker 是独立进程；快照/容器重启后必须重新启动。无需后台调度器即可运行本地闭环。`.env.example` 只提供变量说明，不会自动加载。开发 Token 映射到服务端固定的 `demo-user/demo-org`、`admin/engineer` 角色和 `demo-region` 区域；不能用客户端 Header 或请求字段伪造身份。本地模式不能模拟企业多用户登录，测试通过领域服务注入不同身份验证隔离。生产模式启动会失败关闭。

## 外部服务环境变量模板

`.env.example` 还提供后续接入所需的配置占位：

- 大模型：`API_KEY`、`BASE_URL`、`LLM_MODEL`，用于 DeepSeek/OpenAI 兼容服务。
- Milvus：`MILVUS_HOST`、`MILVUS_PORT`、`MILVUS_USERNAME`、`MILVUS_PASSWORD`，以及 TLS、数据库和集合配置。
- BGE-M3：`BGE_M3_MODE`、本地模型路径/设备，或在线服务地址、模型名和可选密钥。
- Langfuse：启用开关、Public/Secret Key 和实例地址。

将模板复制为 `.env` 后自行填写密钥和密码；`.env` 已被 Git 忽略。上述外部配置尚未被当前本地实现读取，填入配置不会自动切换检索或模型，也不会自动启用链路日志。后续需实现相应适配器和配置校验。请勿把真实密钥填写到会提交的 `.env.example` 中。

## 导入、发布、提问

先准备经过脱敏的 UTF-8 `.txt` 或 `.md` 文件：

```bash
.venv/bin/python scripts/import_document.py ./example.md --source-id demo-guide --revision 1
```

导入返回 `doc_id/version/job_id`。Worker 将任务处理到 `READY` 后，由管理员显式发布；不会自动把未审核内容加入问答。以下命令中的 ID 需替换为实际返回值：

```bash
curl -H "Authorization: Bearer $TOWER_DEV_TOKEN" http://127.0.0.1:8000/api/v1/jobs/JOB_ID
curl -X POST -H "Authorization: Bearer $TOWER_DEV_TOKEN" http://127.0.0.1:8000/api/v1/documents/DOC_ID/versions/1/publish
curl -H "Authorization: Bearer $TOWER_DEV_TOKEN" -H 'Content-Type: application/json' \
  -d '{"query":"RRU 告警如何排查？"}' http://127.0.0.1:8000/api/v1/chat
```

本地 API 也接受 `POST /api/v1/documents` JSON：`title/source_id/source_revision/content` 必填；可选 `source_kind=standard|case`、`roles`、`regions` 和带时区的 `effect_start/effect_end`。暂不接受 multipart/PDF/OCR/DOCX。每次内容、授权元数据或有效期变更都要增加 `source_revision`；同 revision 重复提交幂等，不同内容会返回 409。文件内容限制 100 万字符，请求体限制 4 MB。

| API | 行为 |
|---|---|
| `POST /api/v1/documents` | 持久化版本和任务，返回 202 |
| `POST /api/v1/documents/{id}/versions` | 上传新版本，同 source_id |
| `GET /api/v1/jobs/{id}` | 查看摄入状态、尝试次数和安全错误类别 |
| `POST /api/v1/documents/{id}/versions/{version}/publish` | 发布 READY 且最新来源版本 |
| `DELETE /api/v1/documents/{id}` | 立即撤销可见性，保留本地审计数据 |
| `POST /api/v1/chat` | 最终回答、引用、会话 ID |
| `POST /api/v1/chat/stream` | 校验后发送 `validated` 与最终 `answer` SSE 事件 |
| `GET /api/v1/sessions/{id}` | 验证归属，旧引用撤销后隐藏历史证据 |
| `POST /api/v1/feedback` | `request_id/comment`，必须关联自己的真实问答 |
| `GET /health/live`、`GET /health/ready` | 进程与本地数据库状态，不代表 Worker 存活 |

传 `session_id` 可继续保存到同一会话；目前**不进行历史问题补全**。允许的客户端检索过滤仅 `filters.source_kind`，未知字段拒绝；设备、专业提取和业务区域适用性尚未实现。无依据固定返回“当前知识库暂无对应处置规范，请联系后台支撑人员”；异常返回错误，不能混作未命中。

## 模块与数据流

```text
src/tower_kb/
  main.py / api/           HTTP、认证、DTO、错误、SSE
  bootstrap.py            依赖装配
  config.py               环境校验，禁用未实现的生产模式
  domain/                 身份、权限、有效期、领域异常
  ports/                  SearchIndex / Generator 接口
  application/            文档管理与 RAG 编排
  ingestion/              父子分块、持久化任务、索引校验
  rag/                    RRF 和引用校验
  adapters/               SQLite、词项/哈希向量检索、原文摘录
  workers/                独立 Worker 入口
```

摄入：对象内容哈希存储 → 版本与 SQLite 任务同事务写入 → Worker 领取 lease → 解析文本 → 父子分块 → 双索引 → 核对块数量 → READY → 管理员发布。SQLite 任务表本身就是本地持久队列，因此本版不需要 outbox 或 Celery。索引共用 SQLite 事务，不能将此实现的原子性推断到两个外部索引。

问答：认证 → 会话归属 → 权限/组织/区域/有效期/当前发布版本预过滤 → 两路并行召回各 30 → RRF 40 → 词项重排与阈值门禁 → 最多 3 个父块与 4000 字符预算 → 原文摘录 → 引用 ID/逐字支持校验 → 当前权限版本复核 → 持久化与返回。

子块目标 400 字符、重叠 50；父块最多 1600 字符，保留真实段落/偏移，不编造页码。当前优先规范，再显示有明确标签的案例；尚未实现规范冲突语义判断。文档内容只作为被引用的数据，不会执行指令、工具调用或网络请求；原文可能包含恶意文字，输出端仍需作为不可信文本显示。

## 持久化、恢复与边界

- `.runtime/knowledge.db` 自动执行幂等 schema-v1 初始化；不是完整迁移框架。版本、任务、父子块、索引、会话、反馈、审计保存在 SQLite。
- `.runtime/objects/` 按 SHA256 保存原文。对象先写、数据库失败可能留下孤儿对象；暂无垃圾回收任务。
- 任务 lease 为 120 秒，过期可重新领取，最多 3 次；lease token 阻止旧 Worker 覆盖。仅适合小文本本地任务，不含长任务心跳。不可恢复异常直接 FAILED，不无限重试；失败重建需新的 revision。
- 索引写入失败会回滚且禁止发布。撤销优先修改权威记录，立即阻止查询；异步物理清理、删除事件和补偿扫描未实现。
- 新版本不覆盖旧块，旧版本不进入新回答。审计日志只保存对象与动作，不记密钥或完整工单。
- 默认无答案缓存；没有企业鉴权、速率限制、TLS 网关和生产数据保留策略。开发服务绑定 loopback。
- SSE 目前在完整校验后输出两个事件，不提供实时阶段进度或未校验的 token 流。

## 生产接入路线

| 组件 | 当前状态 | 后续工作 |
|---|---|---|
| MySQL / migrations | SQLite 开发实现 | 事务仓储接口、MySQL 实现与迁移、并发/故障测试 |
| S3 | 本地内容寻址文件 | 受控对象存储适配器、原子上传与回收 |
| Redis / Celery / outbox | SQLite 持久任务 | outbox、Celery、心跳、重试/补偿/调度 |
| Milvus / Elasticsearch BM25 | 本地词项和哈希向量 | 双索引过滤编译、版本可见性校验、降级策略 |
| BGE-M3 / Reranker | 无模型调用 | 服务客户端、有界超时、模型版本与质量评测 |
| Qwen | 逐字原文摘录 | Generator 适配、结构化输出、支持性校验与评测 |
| MinerU / DOCX | UTF-8 文本 | 原文件异步解析、OCR/表格及定位映射 |
| 企业身份系统 | 固定开发身份 | JWT/JWKS/SSO 验证、服务端授权与权限版本 |
| 工单同步 / 评测 | 未实现 | 脱敏、稳定游标、删除事件、业务审核问题集与指标 |

未提供任何虚假的生产适配器或模型服务可用性声明。接入真实设施时应先明确区域/角色/规范审批口径、数据内网限制和模型地址，再扩展 ports 与 bootstrap；不要把示例 Token 用于生产。

## 验证与部署

`tests/test_workflow.py` 覆盖权限范围、伪造会话、撤销、有效期、版本切换、幂等与乱序、索引失败、Worker 崩溃恢复、无命中、恶意文档不执行、引用伪造、依赖错误、反馈、SSE。`scripts/smoke.py` 在临时目录验证完整闭环，不污染开发数据。`scripts/live_smoke.py` 真实启动 Uvicorn 与独立 Worker，验证 HTTP 入库、发布和引用回答后自动关闭。

`deploy/compose.dev.yml` 提供共享持久卷的 API/Worker 开发部署示例。Docker 构建尚未在此云环境验证；生产部署方案不在首版本地范围内。`requirements.lock` 固定本次验证的直接与传递依赖版本，不包含可移植的制品哈希；安装保留 HTTPS 校验。
