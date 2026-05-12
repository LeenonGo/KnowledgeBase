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
| 🧠 Agent 模式 | LLM 自主决策工具调用，Plan-and-Execute 多步推理 |
| 📊 Self-RAG | 自适应检索：自动判断是否需要检索、评估结果相关度 |
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
| 仪表盘 | 统计卡片、7 天趋势、热门知识库 | 全员 |
| 知识库列表 | 创建/查看/删除，部门选择 | 全员（删除需 admin） |
| 知识库详情 | 文档管理、分块查看、部门授权 | 查看全员，编辑需 admin |
| 文档上传 | 三步向导、分块策略选择、PDF OCR 异步处理+按页进度 | admin/kb_admin |
| 分块查看 | 搜索/排序/折叠/编辑/删除 | 查看全员，编辑需 admin |
| 💬 智能问答 | RAG 模式：多轮对话、混合检索、Query 润色、引用标注 [C1][C2] | 全员 |
| 🧠 Agent 工作台 | Agent 模式：推理链可视化、Plan-and-Execute、图表生成、Self-RAG | 全员 |
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
  → Query润色(纠错+扩展+关键词) → Embedding向量化
  → 向量检索(ChromaDB) + BM25检索(jieba) → RRF融合
  → qwen3-rerank重排 → 引用标注[C1][C2] → LLM生成回答 → 返回
```

### Agent 模式（Agent 工作台）

```
用户提问 → Planning（判断复杂度，拆解子任务）
  → 每个子任务执行 ReAct 循环：Thought → Tool-Call → Observe（最多7轮）
  → Self-RAG：评估检索相关度，低相关自动重试或拒答
  → Synthesize：综合所有子任务结果生成最终回答
  → 图表渲染（chart_generator → ECharts）
```

**Agent 工具列表（11 个）：**

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
│   │   ├── conversation_routes.py  # 对话管理
│   │   ├── doc_routes.py           # 文档上传/删除（含 OCR 异步处理）
│   │   ├── kb_routes.py            # 知识库 CRUD
│   │   ├── eval_routes.py          # 效果评测
│   │   └── ...
│   ├── core/
│   │   ├── llm.py                  # LLM 调用 + Agent + Plan-and-Execute + Self-RAG
│   │   ├── tools.py                # 11 个 Agent 工具 + 工具注册表
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
│           └── pages/              # 14 个页面模块
│               ├── qa.js           # 智能问答（RAG 模式）
│               ├── agent.js        # Agent 工作台（Agent 模式）
│               └── ...
├── config/
│   ├── models.json                 # LLM/Embedding/Reranker 配置
│   └── prompts.json                # Prompt 模板（qa/agent/planner/synthesizer/...）
├── scripts/
│   ├── init_db.py                  # 数据库初始化
│   ├── migrate_db.py               # 增量迁移
│   └── ocr_cli.py                  # OCR 命令行工具
├── data/chroma_db/                 # 向量库持久化
├── docs/                           # PRD / 设计方案 / 运维手册
└── README.md
```

---

## 数据库（15 张表）

| 表 | 用途 |
|---|---|
| `user` / `department` | 用户与部门 |
| `knowledge_base` | 知识库 |
| `document` | 文档元数据（SHA-256 去重） |
| `kb_department_access` / `kb_user_access` | 知识库授权 |
| `conversation` / `conversation_turn` | 多轮对话（conv_type 区分 RAG/Agent） |
| `qa_feedback` | 用户反馈 |
| `audit_log` | 审计日志 |
| `eval_dataset` / `eval_question` / `eval_run` / `eval_result` | 效果评测 |
| `trace` / `trace_span` | 全链路 Trace |

---

## 权限体系

| 角色 | 知识库 | 文档 | 分块 | 审计/评测 |
|---|---|---|---|---|
| super_admin | 全权 | 上传/删除 | 编辑/删除 | 查看 |
| kb_admin | 管理设置 | 上传/删除 | 编辑/删除 | ✗ |
| user | 只读查看 | 只读 | 只读 | ✗ |

---

## 项目实施历程

**Phase 1 — MVP 基础搭建**
- RAG 知识库问答系统 MVP（FastAPI + ChromaDB + 前端 SPA）
- 数据库层搭建（10 张核心表）

**Phase 2 — 文档管理完善**
- 文档分块查看/编辑、上传三步向导、Prompt 管理系统
- 语义分块 + 结构分析分块策略

**Phase 3 — 安全与架构**
- JWT 认证 + 知识库权限体系 + 审计日志
- 混合检索（向量+BM25+RRF）+ 多轮对话 + 反馈 + 缓存

**Phase 4 — 质量监控与统计**
- 质量监控页、统计 API、仪表盘数据接入

**Phase 5 — 检索增强**
- 查询改写 + qwen3-rerank 重排

**Phase 6 — 效果评测系统**
- 评测集自动生成 + LLM-as-Judge 9 维度评分

**Phase 7 — OCR 与异步处理**
- PaddleOCR PDF 解析 + 异步上传按页进度

**Phase 8 — Query 润色与多格式支持**
- Query 润色 + Excel/CSV/PPT 解析 + BM25 索引隔离

**Phase 9 — Agent 智能化 v4.0**
- Agent / Function Calling + 5 个工具 + 工具层权限代理

**Phase 10 — 流式问答修复**
- SSE 接口修复 + 前端认证修复

**Phase 11 — v5.0 Agent 全面升级**
- Citation 引用标注 + 推理链可视化 + 联网搜索 + 全链路 Trace
- RAG / Agent 模式分离（独立页面 + 对话隔离）
- Plan-and-Execute 规划分解（复杂问题自动拆子任务）
- Self-RAG 自适应检索（Retrieve/Relevance/Grounding 三重反思）
- 11 个 Agent 工具（含 chart_generator、calculator、doc_stats 等）
- 前端 UI 优化（侧边栏收起、Markdown 渲染、ECharts 图表）

---

## 待办功能

### ⭐ P1 — 深度智能化

- [ ] **工具插件化注册**：支持用户自定义工具，Tool Registry 热加载
- [ ] **长期记忆层**：会话记忆（用户偏好）+ 知识记忆（高频问答沉淀 FAQ）

### ⭐ P2 — 产品体验

- [ ] **Prompt 调试工作台**：可视化编辑 system prompt，实时预览 + A/B 测试 + 版本管理
- [ ] **知识库健康度看板**：文档覆盖率、热点分析、孤岛检测、质量趋势
- [ ] **对话管理增强**：对话置顶/标签/导出 Markdown/PDF/分享只读链接
- [ ] **反馈闭环增强**：差评自动触发重新检索分析，好评沉淀 FAQ

### 💡 P3 — 架构演进

- [ ] **多 Agent 协作**：路由 Agent + 检索 Agent + 分析 Agent + 写作 Agent
- [ ] **知识图谱增强**：实体抽取 + 关系图谱 + GraphRAG 多跳推理
- [ ] **数据源同步**：飞书 / Confluence / Git 自动导入
- [ ] **API 开放 + Bot 发布**：API Key / Widget / Webhook 对外提供问答能力

### 🛡️ 系统优化 & 安全加固

- [ ] JWT 过期时间 + 刷新机制（access_token + refresh_token 双 token）
- [ ] 告警：OOM、磁盘满、LLM API 不可用时要有告警
- [ ] 缓存层：查询缓存接 Redis，支持多实例部署
- [ ] MySQL 定时备份脚本 + cron 配置
