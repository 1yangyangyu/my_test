# 铁塔运维知识库：代码架构设计 V1

依据：《铁塔运维内部知识库技术架构设计方案.docx》。
范围：第一阶段后端代码架构、模块边界和核心接口设计；本文中的目录和 Python 代码是拟实现设计，不代表已经完成或运行验证的系统。

## 1. 总体决策

采用 Python + FastAPI 的模块化单体，同一代码仓库部署 API、摄入 Worker、定时同步进程。保持单 RAG 编排，不引入多 Agent；将检索与回答封装为应用服务，未来需要时可作为 Agent 工具调用。

两条独立链路：

- 入库：文件上传/工单增量 → 持久化任务 → 解析清洗 → 父子分块 → 向量化 → 双索引构建 → 校验发布。
- 问答：身份认证 → 权限范围 → 会话/告警解析 → 并行混合检索 → RRF → 重排 → 父块补全 → 证据检查 → 生成 → 引用校验 → 返回。

API 不同步执行 OCR、大文件解析或模型编码。Worker 通过持久化任务运行这些操作，避免请求超时和重复导入。

### 对原方案的细化

| 原方案 | 代码落地方式 |
|---|---|
| 召回后过滤元数据 | 权限、组织、区域授权、有效期在两路召回时强制过滤，返回后再以数据库复核；设备等推断条件可作为软条件 |
| Top3 | 初始建议两路各取 30、融合保留 40、重排选 3 个子块，再补父块；均可配置，需评测校准 |
| 增量更新 | 文档版本、内容哈希、来源事件版本、任务幂等、双索引发布、删除事件与补偿 |
| 根因推理链 | 输出“证据、可能原因、待验证事项”的简明诊断依据，区分假设与确认结论 |
| 规范与工单 | source_kind 区分规范和案例；案例经验不能覆盖有效规范，也不能自动成为操作标准 |
| 历史对话 | 存站址、设备、告警、已排查项；历史模型回答不视为权威知识证据 |

## 2. 技术组件与职责

| 组件 | 建议选择 | 责任与边界 |
|---|---|---|
| HTTP 服务 | FastAPI / Pydantic | 参数、响应、认证依赖、异常转换 |
| 业务数据库 | MySQL | 文档/版本/权限/任务/父子块/会话/反馈；作为事实来源 |
| 对象存储 | 企业现有 S3 兼容存储 | 原文件、解析结果、页面图片；受控访问 |
| 缓存与队列 | Redis + Celery | 任务投递与短期缓存；任务最终状态保存在 MySQL |
| 文档解析 | MinerU 适配器 + DOCX 解析器 | 返回统一文本块、表格及来源定位，不让业务依赖解析器私有结构 |
| 向量化 | BGE-M3 服务 | 专门推理服务；编码版本与索引绑定 |
| 向量检索 | Milvus | 子块向量与过滤字段 |
| 关键词检索 | Elasticsearch BM25 | 子块文本与同样的过滤字段；明确中文分词方案 |
| 重排 | BGE-Reranker 服务 | 对候选 query/text 对排序 |
| 生成 | Qwen 服务适配器 | 有界超时、结构化输出、受约束回答 |
| 评测 | 离线数据集 + RAGAS 适配器 | 召回、回答、拒答、越权、规范时效独立评估 |

以上是架构建议，不是已确认的基础设施清单。具体模型大小、GPU、客户端版本和依赖锁文件在实现阶段按内网环境确定。第一版不必引入 LangGraph；普通 Python 应用服务即可表达固定 RAG 流程。若团队已统一 LangChain，可在适配层复用组件。

## 3. 代码目录

以下每个目录均有对应职责，Python 包目录实现时补齐 __init__.py。

```text
tower-knowledge-base/
  README.md
  pyproject.toml
  .env.example
  src/tower_kb/
    main.py                       # FastAPI 初始化、生命周期与路由注册
    bootstrap.py                  # 依赖装配：接口绑定到具体实现
    config.py                     # 配置及环境变量校验
    api/
      dependencies.py             # 当前用户、权限上下文、请求 ID
      errors.py                   # 统一错误响应
      v1/
        chat.py                   # 问答、SSE
        documents.py              # 上传、版本、撤销、发布
        jobs.py                   # 查询异步任务状态
        sessions.py               # 会话读取与关闭
        feedback.py               # BadCase 提交
        health.py                 # 存活和就绪检查
    schemas/
      chat.py                     # HTTP 请求/响应 DTO
      document.py
      job.py
      feedback.py
    domain/
      entities.py                 # Document、Chunk、Citation、Evidence
      policy.py                   # 访问范围、有效期规则
      enums.py                    # 状态与来源类别
      errors.py                   # 领域错误，不依赖 HTTP
    ports/
      repositories.py             # 元数据、块、会话、任务存储接口
      search.py                   # 词法与向量检索接口
      models.py                   # Embedder、Reranker、Generator
      parser.py                   # 文档解析接口
      queue.py                    # 任务投递接口
      object_store.py             # 文件读写接口
    application/
      rag_service.py              # 在线问答总流程
      document_service.py         # 上传、版本管理和撤销
      session_service.py          # 所有权检查、上下文与版本控制
      feedback_service.py         # 反馈落库和人工审核状态
      ingestion_service.py        # 离线入库总流程
    rag/
      query_parser.py             # 告警码、设备、专业提取
      query_rewriter.py           # 多轮问题补全，保留原始查询
      filter_builder.py           # 权限硬约束与业务软条件
      hybrid_retriever.py          # 两路并行召回、超时与降级
      fusion.py                   # RRF 排名融合
      reranking.py                # 重排与候选裁剪
      context_builder.py          # 父块补全、去重和 token 预算
      evidence_gate.py            # 证据充分性与无命中分支
      answer_generator.py         # 结构化生成
      citation_validator.py       # 引用 ID、版本、定位及支持性检查
      prompts/
        answer.md
        rewrite.md
    ingestion/
      pipeline.py                 # 可恢复的步骤编排
      cleaning.py                 # 页眉页脚、重复、工单脱敏和质量过滤
      chunking.py                 # 标题/流程边界优先的父子分块
      metadata.py                 # 标准化字段及缺失校验
      indexing.py                 # 双索引 upsert 与可见性确认
      publishing.py               # 发布门禁与当前版本切换
      reconciliation.py           # 缺失索引、孤儿块、任务补偿
    adapters/
      database/
        models.py                 # ORM 表定义
        session.py                # 连接与事务
        repositories.py           # ports 的 MySQL 实现
      search/
        milvus.py                 # 向量检索及过滤表达式编译
        elasticsearch.py          # BM25、中文分词、过滤 DSL
      models/
        embedding.py
        reranker.py
        qwen.py
      parsing/
        mineru.py
        docx.py
      storage/s3.py
      queue/celery.py
      auth/identity_provider.py    # 接入企业身份系统
      sources/
        documents.py              # 文档库事件/游标适配
        work_orders.py            # 工单 CDC 或增量轮询
    workers/
      app.py                      # Worker 入口
      tasks.py                    # 摄入、重试、重建任务
      scheduler.py                # 增量扫描、对账、到期检查
    observability/
      logging.py                  # 脱敏日志、trace_id
      metrics.py                  # 延迟、命中、失败率
  migrations/                     # 数据库版本迁移
  tests/
    unit/
    integration/
    security/
    fixtures/                     # 合成样例，禁止直接放敏感工单
  evaluation/
    datasets/
    run.py
    metrics.py
  deploy/
    Dockerfile.api
    Dockerfile.worker
    compose.dev.yml               # 开发环境；不等同生产部署方案
  scripts/
    seed_demo.py
    reindex.py
```

依赖方向：api → application → domain/ports；adapters 实现 ports；bootstrap 完成装配。domain 不导入 FastAPI、Milvus SDK 或 ORM。避免路由层直接写检索表达式、拼 Prompt 或发模型请求。

## 4. 核心模型

### Document / DocumentVersion

- Document：doc_id、org_id、source_system、source_id、current_version、deleted_at。
- DocumentVersion：doc_id、version、content_hash、source_revision、title、source_kind、doc_type、device_type、station_type、specialty、applicable_regions、allowed_roles、effect_start、effect_end、status、object_key、parser_version、embedding_version。
- 唯一约束：(source_system, source_id, org_id)、(doc_id, version)。
- 版本状态：STAGING、READY、PUBLISHED、REVOKED、FAILED。规范“现行”由发布指针和有效期共同判定，不由标题中的 V2 判断。
- applicable_regions 与访问授权区域分开理解：一个决定规范适用哪里，一个决定用户能看哪里；行政区层级统一编码。

### Chunk

chunk_id、doc_id、version、chunk_type、parent_id、ordinal、text、page_start、page_end、section_path、paragraph_id、source_span、content_hash。

chunk_id 以文档版本、分块配置版本和序号确定，重试保持稳定。子块负责召回，父块负责上下文；不跨文档或版本拼接。扫描页码保留物理页索引，DOCX 若无可靠分页使用章节/段落定位，不编造页码。

建议初始子块约 300～500 中文字符、重叠约 50；先尊重标题、完整步骤、表格边界，再按长度兜底。字符长度与模型 token 预算分开计算。这些仅是初始参数。

### RequestContext / RetrievalScope

RequestContext 来自可信认证：user_id、org_id、roles、authorized_regions、permission_version、trace_id。

RetrievalScope 由服务端生成：组织、授权角色、授权区域、有效时间、允许文档集合/版本及业务条件。客户端只能缩小检索范围，不能扩权。普通问答的有效时间由服务端确定；历史规范查询单独授权与显式标注。

### Evidence / Answer

Evidence：citation_id、chunk_id、doc_id、version、原文、文件名、页码或段落、source_kind。

Answer：answer、reason_chain、reference、has_knowledge、status、trace_id、degraded、warnings。reason_chain 为简明诊断依据：证据 → 可能原因 → 待核实项，不要求模型输出内部思维过程。

## 5. 在线问答编排

下面是接口级伪代码，展示依赖关系；尚未实现具体适配器和运行配置。

```python
class RagService:
    def __init__(self, sessions, policy, parser, retriever, reranker,
                 context_builder, gate, generator, validator):
        self.sessions = sessions
        self.policy = policy
        self.parser = parser
        self.retriever = retriever
        self.reranker = reranker
        self.context_builder = context_builder
        self.gate = gate
        self.generator = generator
        self.validator = validator

    async def answer(self, request, actor):
        # 会话所有权必须先验证；历史内容也需按当前权限处理。
        history = await self.sessions.load_authorized(request.session_id, actor)
        scope = await self.policy.build_scope(actor, request.filters)
        query = await self.parser.parse(request.query, history)
        # retriever 内部：两路带 scope 过滤，独立超时，按 chunk_id 做 RRF。
        hits = await self.retriever.search(query, scope)
        hits = await self.policy.recheck(hits, scope)
        ranked = await self.reranker.rank(query, hits)
        evidence = await self.context_builder.build(ranked, scope, top_k=3)
        decision = await self.gate.check(query, evidence)
        if not decision.sufficient:
            result = decision.to_response()
        else:
            draft = await self.generator.generate(query, evidence)
            result = await self.validator.validate_or_fallback(draft, evidence)
        # 保存前/响应前对权限撤销与版本变化按策略复核。
        await self.policy.verify_response(result, actor)
        await self.sessions.append_turn(request, result, actor)
        return result
```

关键规则：

1. BM25 与向量检索必须使用同一个权限范围。检索字符串由适配器根据结构化条件生成，不让用户传任意 SQL/DSL。
2. RRF 使用两路排名融合，不直接加原始 BM25 分数与向量相似度。
3. 两路各 30、融合 40、最终 3 是起始配置。对比多个型号时按子问题覆盖候选，避免三个结果都来自同一型号。
4. 父块补全重新检查权限、当前版本与有效期；按父块去重，控制上下文预算，保留引用片段的精确定位。
5. evidence_gate 结合重排相关性、问题覆盖和规范来源判定；不能把重排分数当作概率，也不能因为召回非空就认定可回答。
6. 无依据回复原方案固定文案：“当前知识库暂无对应处置规范，请联系后台支撑人员”。信息不足可返回 needs_clarification；依赖服务故障返回 dependency_error，不能伪装成知识未命中。
7. 引用由服务端为证据分配 ID，模型只选择 ID，文件名/页码由服务端回填。校验 ID 只能保证来源真实，还需检查回答是否受到证据支持；不能宣称彻底消除幻觉。
8. 文档作为不可信数据处理，文内“忽略系统提示”等文本不能改变权限或指令。故障案例输出必须明确案例属性。
9. SSE 第一版先发阶段事件，待生成与引用校验通过后发最终回答；不要在校验前流出未经验证的操作步骤。

## 6. 增量入库与双索引一致性

### 上传与任务

上传接口校验权限、文件类型、大小和必要元数据，写对象存储与版本记录，在 MySQL 同一事务写入 ingestion_jobs 和 outbox_events，返回 202 + job_id。独立投递器将 outbox 事件交给 Celery；任务投递允许重复，Worker 必须幂等。

幂等依据包含 org_id、source_system、source_id、source_revision；内容哈希用于跳过重复内容，但权限或有效期改变也必须触发元数据更新。不能仅按文件名去重。

### Worker 状态

RECEIVED → PARSING → CHUNKING → EMBEDDING → INDEXING → VERIFYING → READY → PUBLISHED。

各步骤记录输入/输出位置、尝试次数、错误类型、lease 到期时间。Worker 崩溃后可被重新领取；网络超时有限重试，文件损坏、元数据缺失进入人工处理，不无限重试。

### 发布与查询门禁

1. 为新版本生成独立 chunk_id，写 MySQL 块记录与两路索引；不覆盖旧版本的块。
2. 核验块数量、版本、内容哈希、索引可查询性和元数据完整性，成功后标记 READY。
3. 在 MySQL 事务中用版本条件更新 current_version 并记录发布事件；来源事件乱序时拒绝旧 revision 覆盖新版本。
4. 检索始终只允许 PUBLISHED/current 的版本参与回答。索引侧维护发布过滤字段，返回后以 MySQL 发布指针再校验，禁止未发布或过期版本进入模型。
5. 两个索引没有跨库原子事务；发布字段传播期间可能短暂少召回。采用过量召回与有界补查，并暴露 degraded 状态；不能承诺绝对无窗口切换。
6. 旧版本异步回收，禁止先删旧版本再建新版本。撤销/删除优先在 MySQL 写 tombstone，查询复核立即拒绝；后台删除两路索引、失效缓存。
7. 权限变更同样先更新权威权限，再更新索引与缓存；权限服务不可用时失败关闭，不能退回无过滤查询。

工单接入优先使用已有 CDC；若没有，按 (updated_at, id) 稳定复合游标轮询并留重叠窗口，用事件幂等去重。删除需要 tombstone 或对账机制。轮询属于准实时，延迟目标由业务确认。

## 7. 存储与 API 契约

### 核心表

| 表 | 用途 | 关键约束 |
|---|---|---|
| documents / document_versions | 文档标识、版本、发布指针 | 来源唯一键、文档版本唯一键 |
| chunks | 父子文本及定位 | chunk_id 主键；doc_id/version 索引 |
| ingestion_jobs / outbox_events | 可恢复任务与可靠投递 | event_key 唯一、状态和 lease 索引 |
| source_cursors | 增量同步位置 | 来源唯一键；游标更新采用并发控制 |
| role_permissions | 角色和资源范围 | 企业身份系统到内部策略映射 |
| sessions / messages | 用户会话及问答快照 | org_id/user_id 所有权；会话版本并发控制 |
| feedback / evaluation_runs | 坏例审核、评测结果 | 关联 request_id 和检索/模型版本 |
| audit_events | 上传、发布、撤销、查询审计 | 操作人、对象、时间；控制敏感原文留存 |

### API

| 方法与路径 | 行为 |
|---|---|
| POST /api/v1/documents | 上传新文档，返回 202 和 job_id |
| POST /api/v1/documents/{doc_id}/versions | 新版本上传；权限及并发版本检查 |
| POST /api/v1/documents/{doc_id}/versions/{version}/publish | 知识管理员发布 READY 版本 |
| DELETE /api/v1/documents/{doc_id} | 撤销检索可见性，异步清理索引 |
| GET /api/v1/jobs/{job_id} | 当前阶段、失败原因、重试状态；检查任务所有权 |
| POST /api/v1/chat | 返回最终结构化回答 |
| POST /api/v1/chat/stream | 阶段事件 + 最终通过校验的回答 |
| GET /api/v1/sessions/{session_id} | 当前用户可访问的会话 |
| POST /api/v1/feedback | 绑定真实问答 ID 提交反馈 |
| GET /health/live、/health/ready | 进程存活与必要依赖就绪情况 |

请求示例：

```json
{
  "query": "这个RRU告警需要怎么排查？",
  "session_id": "session-demo",
  "filters": {"device_type": "RRU", "specialty": "无线"}
}
```

请求体不携带可信 roles/user_id；身份来自验证后的认证凭据。

无命中响应示例：

```json
{
  "request_id": "request-demo",
  "status": "no_knowledge",
  "query": "这个RRU告警需要怎么排查？",
  "answer": "当前知识库暂无对应处置规范，请联系后台支撑人员",
  "reason_chain": "",
  "reference": [],
  "has_knowledge": false,
  "degraded": false,
  "warnings": []
}
```

命中时 reference 每项包括 citation_id、doc_id、version、chunk_id、file_name、pos、source_kind。响应中的自然语言 answer 与结构化引用来自同一次生成结果，避免两个接口各自生成而产生矛盾。

错误采用统一 envelope：request_id、error.code、error.message、error.retryable。区分 401、403、404、422、429、503；依赖失败与业务无命中分开。

## 8. 配置、部署与观测

配置按环境分离：MYSQL_DSN、REDIS_URL、OBJECT_STORAGE_ENDPOINT、MILVUS_URI、ELASTICSEARCH_URL、EMBEDDING_ENDPOINT、RERANKER_ENDPOINT、LLM_ENDPOINT、LLM_MODEL、各链路超时、候选数量、上下文预算。密钥使用环境注入或企业密钥管理，不提交仓库。

API、Worker、Scheduler、模型服务分开进程。解析与向量化队列分离，限制并发与最大文件大小；大文档分批，避免占满 GPU 与 API 内存。数据库连接池、HTTP 客户端在进程生命周期初始化，不每次请求重建。

日志串联 request_id / job_id / doc_id / version。指标包括两路召回延迟、重排延迟、生成延迟、检索命中率、无知识率、拒答率、引用失败、任务积压、版本发布耗时及索引不一致数。日志默认脱敏，不记录密钥和完整敏感工单。

缓存默认只做安全的短期会话/元数据缓存；如增加答案缓存，键至少包含组织、权限范围摘要、权限版本、知识发布版本、规范化问题和会话上下文摘要。跨用户共享答案前必须证明权限等价。

## 9. 开发顺序与验收

| 阶段 | 要完成的内容 | 验收标准 |
|---|---|---|
| P0 工程骨架 | FastAPI、配置、依赖注入、数据库迁移、认证接口 | 服务启动；身份缺失拒绝；测试替身与真实适配器明确区分 |
| P1 摄入闭环 | 小样本文档上传、解析、父子块、双索引、发布 | 同事件重复投递不重复入库；单路写失败不发布 |
| P2 检索闭环 | RBAC 预过滤、混合召回、RRF、重排、父块补全 | 返回有定位的证据；无越权、旧版、未发布内容 |
| P3 回答闭环 | Qwen 生成、引用校验、无依据分支 | 规范问答有引用；不存在的标准不编造；故障响应不是未命中 |
| P4 增量与多轮 | 来源游标、删除、会话归属和上下文继承 | 乱序事件不覆盖新版本；跨用户 session 不可读 |
| P5 评测与接入 | 评测集、BadCase 审核、下游适配 | 对关键场景人工复核；记录基线后再约定指标 |

必须覆盖的测试：越权角色与区域、伪造会话 ID、权限撤销、到期规范、删除事件、双索引部分成功、重复任务、Worker 中断恢复、乱序版本、无命中、引用伪造、文档提示注入、服务超时及案例与规范冲突。

建议先准备 50～100 条经业务审核的问题，覆盖告警、流程、设备对比、案例、安全规范及无答案问题；逐步扩充。检索看 Recall@K/MRR，生成看证据支持与业务正确性；RAGAS 分数作为辅助，不能代替安全规范人工审核。

## 10. 实现前需要确认但不阻塞本版设计的事项

- 内网是否已有 MySQL、Redis、Milvus、Elasticsearch、对象存储，是否允许新增组件。
- Qwen/BGE 模型服务地址、并发和 GPU 资源；数据是否必须完全内网处理。
- 工单来源是数据库、API 还是 CDC，以及删除事件如何获取。
- 区域、角色、规范发布审批的实际口径及知识管理员名单。
- 文档规模、日增量、允许同步延迟、问答并发和响应时间目标。

## 11. 技术参考

- Milvus 官方过滤检索说明：https://milvus.io/docs/filtered-search.md
- Elasticsearch 官方 BM25 similarity 说明：https://www.elastic.co/docs/reference/elasticsearch/index-settings/similarity

本设计只引用上述文档确认组件能力；候选数量、分块大小、部署组合和发布机制均为针对本项目提出的工程设计，需在实现与评测阶段验证。
