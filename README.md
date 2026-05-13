# RAG 知识库管理系统

基于 RAG 架构的企业级智能知识库管理与问答平台。15 分钟部署上线，支持多部门权限隔离、混合检索、多轮对话、效果评测。

## 核心能力

| 能力 | 说明 |
|------|------|
| 📄 多格式文档解析 | PDF / Word / Excel / CSV / PPT / TXT / Markdown，PDF 支持 OCR |
| ✂️ 三种分块策略 | 语义分块 / 结构分析 / 固定长度，用户可选 |
| 🔍 混合检索 | 向量语义 + BM25 关键词 + RRF 融合 + qwen3-rerank 重排 |
| 🔐 部门权限隔离 | 部门级授权 + 三级角色权限，检索时自动过滤 |
| 💬 多轮对话 | 上下文自动传递，Query 润色 + 查询改写 |
| 🧠 Agent 模式 | LLM 自主决策工具调用，Plan-and-Execute 多步推理，13 个工具 |
| 📊 Self-RAG | 自适应检索：自动判断是否需要检索、评估结果相关度 |
| 💾 长期记忆层 | 用户记忆（偏好/背景/纠正）+ FAQ 高频问答自动沉淀 |
| 📈 效果评测 | LLM-as-Judge 9 维度自动评分 |
| 🔄 反馈闭环 | 用户 👍👎 + 质量监控，持续优化 |

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + Uvicorn |
| 数据库 | MySQL + SQLAlchemy 2.0 |
| 向量数据库 | ChromaDB（按 kb_id 隔离） |
| LLM / Embedding | OpenAI 兼容接口（DashScope / Ollama / 自定义） |
| Reranker | qwen3-rerank |
| OCR | PaddleOCR（版面检测 + 文字识别 + 表格识别） |
| 文档解析 | PyMuPDF(PDF)、python-docx(Word)、openpyxl/xlrd(Excel)、python-pptx(PPT)、jieba(中文分词) |
| 前端 | HTML + CSS + JavaScript（SPA + Hash 路由）+ ECharts |

---

## 快速开始

```bash
# 1. 安装依赖
cd knowledge-base
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env：JWT_SECRET、数据库连接、APP_ENV 等

# 3. 初始化数据库
python scripts/init_db.py
python scripts/migrate_db.py

# 4. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问 `http://localhost:8000`，默认管理员：`admin` / `admin123`

**OCR（可选）**：`pip install paddlepaddle paddleocr`，模型首次使用自动下载。

---

## 功能页面

| 页面 | 功能 | 权限 |
|---|---|---|
| 登录页 | JWT 认证 | 全员 |
| 仪表盘 | 统计卡片、7 天趋势、热门知识库、健康度评分 | 全员 |
| 知识库列表 | 创建/查看/删除，部门选择 | 全员（删除需 admin） |
| 知识库详情 | 文档管理、分块查看、部门授权 | 查看全员，编辑需 admin |
| 文档上传 | 三步向导、分块策略选择、PDF OCR 异步处理+按页进度 | admin/kb_admin |
| 分块查看 | 搜索/排序/折叠/编辑/删除 | 查看全员，编辑需 admin |
| 💬 智能问答 | RAG 模式：多轮对话、混合检索、Query 润色、引用标注 [C1][C2]、FAQ 预匹配 | 全员 |
| 🧠 Agent 工作台 | Agent 模式：推理链可视化、Plan-and-Execute、图表生成、Self-RAG、记忆注入 | 全员 |
| 💾 我的记忆 | 用户记忆管理：查看/删除偏好/背景/纠正记录 | 全员 |
| 📝 FAQ 管理 | FAQ 审核：通过/拒绝/删除、筛选分页、统计面板 | admin/kb_admin |
| 用户管理 | CRUD、筛选、分页 | super_admin |
| 部门管理 | 树形结构 | super_admin |
| 审计日志 | 操作记录筛选 | super_admin |
| 质量监控 | 差评率/无结果率/延迟统计、反馈列表 | super_admin |
| 效果评测 | 评测集自动生成、LLM-as-Judge 9 维度评分 | super_admin |
| 系统配置 | LLM/Embedding/Reranker/Prompt/检索策略 | super_admin |

---

## 智能问答流程

### RAG 模式（智能问答）

```
用户提问 → JWT认证 → 权限校验 → 查询改写(多轮时) → 查缓存
  → FAQ预匹配（命中直接返回）
  → Query润色(纠错+扩展+关键词) → Embedding向量化
  → 向量检索(ChromaDB) + BM25检索(jieba) → RRF融合
  → qwen3-rerank重排 → 引用标注[C1][C2]
  → 注入用户记忆 → LLM生成回答 → 返回
```

### Agent 模式（Agent 工作台）

```
用户提问 → 注入用户记忆
  → Planning（判断复杂度，拆解子任务）
  → 每个子任务执行 ReAct 循环：Thought → Tool-Call → Observe（最多7轮）
  → Self-RAG：评估检索相关度，低相关自动重试或拒答
  → Synthesize：综合所有子任务结果生成最终回答
  → 图表渲染（chart_generator → ECharts）
  → 对话结束 → 异步提取用户记忆 + 记录 FAQ 候选
```

**Agent 工具列表（13 个）：**

| 工具 | 功能 |
|---|---|
| search_kb | 知识库语义检索（带相关度评分） |
| list_kb | 列出可访问知识库 |
| list_docs | 列出知识库文档 |
| get_doc_content | 获取文档全文 |
| summarize_doc | 文档摘要生成 |
| web_search | 联网搜索 |
| current_time | 获取当前时间 |
| calculator | 数学计算（安全沙箱） |
| doc_stats | 知识库统计（文档数/分块数/格式分布） |
| chart_generator | 数据可视化（ECharts 柱状图/饼图/折线图） |
| knowledge_compare | 知识库/文档对比分析 |
| recall_memory | 查询用户记忆（偏好/背景/纠正） |
| search_faq | 查询 FAQ 沉淀，命中直接返回答案 |

---

## 长期记忆层

### 用户记忆（UserMemory）

| 类型 | 示例 | 触发方式 |
|------|------|----------|
| preference | 用户在电力行业、偏好表格形式 | 对话中规则自动提取 |
| context | 用户负责变电站巡检项目 | 对话中用户主动提及 |
| correction | 不要用"负载"，应该用"负荷" | 用户纠正时捕获 |

- **注入 prompt**：问答时自动注入 system prompt
- **生命周期**：上限 50 条/用户，90 天后衰减，置信度 < 0.1 过期淘汰
- **管理页面**：「💾 我的记忆」查看/删除

### FAQ 沉淀

| 阶段 | 机制 |
|------|------|
| 候选捕获 | 每次问答记录为候选（question_hash 去重） |
| 自动沉淀 | 同一问题 ≥ 3 次 + 好评率 ≥ 80% → 自动生成 FAQ |
| 人工审核 | admin/kb_admin 在管理页通过/拒绝 |
| 预匹配 | RAG 问答前先查 FAQ，命中直接返回 |
| 衰减淘汰 | 30 天未命中 → 置信度降低 → < 0.3 自动归档 |

---

## Self-RAG 自适应检索

系统内置 Self-RAG 能力，通过 3 个反思节点提升回答质量：

1. **Retrieve Judge**：LLM 自主判断是否需要检索（简单事实问题直接回答）
2. **Relevance Judge**：检索结果带相关度评分（高/中/低），全部低相关时拒答并建议换关键词或联网搜索
3. **Grounding Judge**：回答必须标注引用来源 [C1][C2]，找不到证据标注「待确认」，禁止编造

---

## 效果评测

从知识库文档自动生成评测数据，通过 LLM-as-Judge 进行多维度评估。

**评测集生成**：LLM 自动生成 5 类测试问题：
- 事实型（40%）、超范围（20%）、多文档（15%）、歧义（15%）、错误前提（10%）

**9 维度评分**：检索精确率、检索召回率、排序质量、忠实度、相关性、完整性、拒答准确性、时效性、多跳推理

---

## API 接口

### 认证
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/login` | 登录 |
| GET | `/api/me` | 当前用户信息 |

### 知识库 & 文档
| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/knowledge-bases` | 知识库列表/创建 |
| PUT/DELETE | `/api/knowledge-bases/{id}` | 更新/删除知识库 |
| POST | `/api/upload` | 上传文档 |
| GET | `/api/upload/progress/{task_id}` | PDF 处理进度 |
| GET | `/api/documents?kb_id=xxx` | 文档列表 |
| DELETE | `/api/documents/{filename}` | 删除文档 |
| GET | `/api/documents/{filename}/chunks` | 查看分块 |
| PUT/DELETE | `/api/chunks/{chunk_id}` | 编辑/删除分块 |

### 问答 & 对话
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/query/stream` | RAG 流式问答（SSE） |
| POST | `/api/query/agent/stream` | Agent 流式问答（SSE） |
| GET/POST | `/api/conversations` | 对话列表/创建 |
| GET/POST | `/api/conversations/{id}/turns` | 对话轮次 |
| POST/GET | `/api/feedback` | 提交/查看反馈 |

### 用户记忆 & FAQ
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/memory` | 获取用户记忆列表 + 统计 |
| DELETE | `/api/memory/{id}` | 删除单条记忆 |
| GET | `/api/faq` | FAQ 列表（分页/筛选） |
| GET | `/api/faq/stats` | FAQ 统计 |
| POST | `/api/faq/{id}/approve` | 审核通过 FAQ |
| POST | `/api/faq/{id}/reject` | 拒绝 FAQ |
| DELETE | `/api/faq/{id}` | 删除 FAQ |

### 用户 & 部门 & 授权
| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/users` | 用户列表/创建 |
| PUT/DELETE | `/api/users/{id}` | 更新/禁用用户 |
| GET/POST/DELETE | `/api/departments` | 部门 CRUD |
| GET/POST/DELETE | `/api/kb-access` | 知识库部门授权 |

### 配置 & 统计 & 评测
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/cache/stats` | 查询缓存统计 |
| POST | `/api/cache/clear` | 清空查询缓存 |
| GET/POST | `/api/config/models` | 模型配置 |
| GET/POST | `/api/config/prompts` | Prompt 模板 |
| GET | `/api/stats/dashboard` | 仪表盘统计 |
| GET | `/api/stats/quality` | 质量监控统计 |
| POST | `/api/eval/generate` | 生成评测集 |
| POST | `/api/eval/run/{dataset_id}` | 启动评测 |

---

## 项目结构

```
knowledge-base/
├── app/
│   ├── main.py                     # FastAPI 入口
│   ├── api/                        # 路由模块
│   │   ├── query_routes.py         # 问答（RAG + Agent + Plan-and-Execute）
│   │   ├── conversation_routes.py  # 对话管理 + 记忆/FAQ hook
│   │   ├── memory_routes.py        # 用户记忆 & FAQ 管理 API
│   │   ├── doc_routes.py           # 文档上传/删除（含 OCR 异步处理）
│   │   ├── kb_routes.py            # 知识库 CRUD
│   │   └── ...
│   ├── core/
│   │   ├── llm.py                  # LLM 调用 + Agent + Plan-and-Execute + Self-RAG
│   │   ├── tools.py                # 13 个 Agent 工具 + 工具注册表
│   │   ├── memory_service.py       # 记忆提取/检索/衰减 + FAQ 沉淀/匹配/生命周期
│   │   ├── vectorstore.py          # ChromaDB 向量存储 + 混合检索
│   │   ├── splitter.py             # 文本分块（语义/固定/结构）
│   │   ├── reranker.py             # 重排序
│   │   ├── loader.py               # 文档加载
│   │   ├── ocr/                    # OCR 模块（PaddleOCR）
│   │   └── ...
│   ├── models/                     # ORM + Pydantic
│   └── static/                     # 前端 SPA
│       ├── index.html              # 主页面 + 路由
│       ├── style.css               # 全局样式 + Markdown 渲染
│       └── js/
│           ├── router.js           # Hash 路由
│           ├── api.js              # API 封装
│           ├── components/ui.js    # 通用组件（分页/模态/Markdown渲染/图表）
│           └── pages/              # 16 个页面模块
│               ├── qa.js           # 智能问答（RAG 模式）
│               ├── agent.js        # Agent 工作台（Agent 模式）
│               ├── memory.js       # 用户记忆管理
│               ├── faq.js          # FAQ 管理
│               └── ...
├── config/
│   ├── models.json                 # LLM/Embedding/Reranker 配置
│   └── prompts.json                # Prompt 模板
├── scripts/
│   ├── init_db.py                  # 数据库初始化
│   ├── migrate_db.py               # 增量迁移
│   └── ocr_cli.py                  # OCR 命令行工具
├── data/chroma_db/                 # 向量库持久化
├── docs/                           # PRD / 设计方案 / 运维手册
└── README.md
```

---

## 数据库（19 张表）

| 表 | 用途 |
|---|---|
| `user` / `department` | 用户与部门 |
| `knowledge_base` | 知识库 |
| `document` | 文档元数据（SHA-256 去重） |
| `kb_department_access` / `kb_user_access` | 知识库授权 |
| `conversation` / `conversation_turn` | 多轮对话（conv_type 区分 RAG/Agent） |
| `user_memory` | 用户长期记忆（偏好/背景/纠正） |
| `faq` / `faq_tag` / `faq_candidate` | FAQ 沉淀 + 候选统计 |
| `qa_feedback` | 用户反馈 |
| `audit_log` | 审计日志 |
| `eval_dataset` / `eval_question` / `eval_run` / `eval_result` | 效果评测 |
| `trace` / `trace_span` | 全链路 Trace |

---

## 权限体系

| 角色 | 知识库 | 文档 | 分块 | 审计/评测 | FAQ |
|---|---|---|---|---|---|
| super_admin | 全权 | 上传/删除 | 编辑/删除 | 查看 | 审核/删除 |
| kb_admin | 管理设置 | 上传/删除 | 编辑/删除 | ✗ | 审核/删除 |
| user | 只读查看 | 只读 | 只读 | ✗ | 只读 |

---

## 项目实施历程

**Phase 1 — MVP 基础搭建**
- RAG 知识库问答系统 MVP（FastAPI + ChromaDB + 前端 SPA）

**Phase 2 — 文档管理完善**
- 文档分块查看/编辑、上传三步向导、Prompt 管理系统

**Phase 3 — 安全与架构**
- JWT 认证 + 知识库权限体系 + 审计日志 + 混合检索 + 多轮对话

**Phase 4 — 质量监控与统计**

**Phase 5 — 检索增强**
- 查询改写 + qwen3-rerank 重排

**Phase 6 — 效果评测系统**
- 评测集自动生成 + LLM-as-Judge 9 维度评分

**Phase 7 — OCR 与异步处理**
- PaddleOCR PDF 解析 + 异步上传按页进度

**Phase 8 — Query 润色与多格式支持**

**Phase 9 — Agent 智能化 v4.0**
- Agent / Function Calling + 5 个工具

**Phase 10 — 流式问答修复**

**Phase 11 — v5.0 Agent 全面升级**
- RAG/Agent 模式分离、Plan-and-Execute、Self-RAG、13 个工具
- 推理链可视化、引用标注、联网搜索、全链路 Trace
- 对话管理增强（置顶/标签/导出）
- 知识库健康度看板

**Phase 12 — v5.1 长期记忆层**
- 用户记忆（偏好/背景/纠正）+ FAQ 高频问答自动沉淀
- Agent 工具新增 recall_memory + search_faq

---

## 竞品对比分析

对比 Dify、Coze、FastGPT 等主流 AI Agent 平台，当前系统与竞品的核心差距：

### 已有优势（优于竞品）
| 能力 | 说明 |
|------|------|
| Self-RAG 三重反思 | 多数竞品没有自适应检索能力 |
| 长期记忆层 | 用户记忆 + FAQ 沉淀，多数 RAG 产品不具备 |
| 部门权限隔离 | 企业级多租户能力，Dify/Coze 云端版需付费 |
| 效果评测系统 | 9 维度自动评分，多数竞品没有 |

### 核心差距（需补齐）

#### 🔴 P0 — 直接影响 Agent 智能化程度

| 功能 | 竞品现状 | 本项目现状 | 收益 |
|------|---------|-----------|------|
| **代码执行沙箱** | Dify/Coze 都有 Code Interpreter，Agent 可写 Python 处理数据 | 只有 calculator 做简单数学 | Agent 能做数据分析、表格处理，智能化质变 |
| **人机协作确认** | Dify Workflow 支持人工审批节点，Agent 暂停等用户确认 | Agent 全自动，用户无法干预中间过程 | 用户能控制 Agent 行为，信任度提升 |
| **HTTP 请求工具** | Dify/Coze 支持 HTTP 节点调任意 API | Agent 只能调内置工具 | Agent 能连接外部系统（飞书/钉钉/数据库），扩展性打开 |

#### 🟡 P1 — 体验差距，中期补齐

| 功能 | 竞品现状 | 本项目现状 |
|------|---------|-----------|
| **Prompt 调试工作台** | Dify/Coze 可视化编辑 + 实时预览 + 版本管理 | Prompt 写在 JSON 文件里 |
| **结构化输出** | Dify 支持 JSON Schema 输出，前端直接渲染表单 | Agent 输出全是自由文本 |
| **工具插件化** | Dify 支持工具市场 + 自定义 API 工具 | 工具硬编码，无法扩展 |

#### 🟢 P2 — 锦上添花

| 功能 | 说明 |
|------|------|
| 对话级语义记忆 | 当前规则提取，升级为向量化语义检索 |
| 多 Agent 协作 | 路由 Agent + 专业 Agent 分工 |
| 知识图谱增强 | 实体抽取 + 关系图谱 + GraphRAG |
| Guardrails | 敏感内容检测、幻觉检测 |
| 数据源同步 | 飞书/Confluence/Git 自动导入 |

---

## 待办功能 & 执行计划

### 🔥 v5.2 — Agent 智能化增强（下一步）

| 优先级 | 功能 | 预估工期 | 说明 |
|--------|------|---------|------|
| **P0** | 代码执行沙箱（code_executor 工具） | 2 天 | Python 沙箱执行，返回 stdout + 生成文件，Agent 能做数据分析 |
| **P0** | 人机协作确认节点 | 1 天 | Plan-and-Execute 中加确认点，子任务执行完暂停等用户批准 |
| **P0** | HTTP 请求工具（http_request） | 1 天 | Agent 能调 REST API，连接飞书/钉钉/企业微信/外部数据库 |

### 📋 v5.3 — 产品体验补齐

| 优先级 | 功能 | 说明 |
|--------|------|------|
| P1 | Prompt 调试工作台 | 可视化编辑 + 实时预览 + 版本对比 |
| P1 | 结构化输出 | 支持 JSON Schema / 表格 / Markdown 报告输出格式 |
| P1 | 工具插件化注册 | Tool Registry 热加载，支持用户自定义工具 |
| P2 | 反馈闭环增强 | 差评自动触发重新检索分析，好评沉淀 FAQ |

### 💡 v6.0 — 架构演进

| 功能 | 说明 |
|------|------|
| 多 Agent 协作 | 路由 Agent + 检索 Agent + 分析 Agent + 写作 Agent |
| 知识图谱增强 | 实体抽取 + 关系图谱 + GraphRAG 多跳推理 |
| 数据源同步 | 飞书 / Confluence / Git 自动导入 |
| API 开放 + Bot 发布 | API Key / Widget / Webhook 对外提供问答能力 |

### 🛡️ 系统优化 & 安全加固

| 功能 | 说明 |
|------|------|
| JWT 双 token | access_token + refresh_token 刷新机制 |
| 告警机制 | OOM、磁盘满、LLM API 不可用 |
| Redis 缓存 | 查询缓存接 Redis，支持多实例部署 |
| MySQL 定时备份 | 备份脚本 + cron 配置 |
