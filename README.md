# RAG 知识库管理系统

基于 RAG（Retrieval-Augmented Generation）架构的企业级智能知识库管理与问答平台。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + Uvicorn |
| 数据库 | MySQL（关系型）+ SQLite（备选） |
| 向量数据库 | ChromaDB（持久化，按 metadata.kb_id 隔离） |
| ORM | SQLAlchemy 2.0 |
| 认证 | PyJWT + Werkzeug（密码哈希） |
| LLM | OpenAI 兼容接口（支持 DashScope / Ollama / OpenAI / 自定义） |
| Embedding | OpenAI 兼容接口（同上） |
| Reranker | qwen3-vl-rerank（DashScope）/ 兼容 API |
| OCR | PaddleOCR（PP-StructureV3 版面检测 + 文字识别 + 表格识别） |
| 中文分词 | jieba（BM25 关键词检索） |
| 前端 | HTML + CSS + JavaScript（模块化 SPA + Hash 路由） |

## 快速开始

### 1. 安装依赖

```bash
cd knowledge-base
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

`.env` 文件内容：
```bash
JWT_SECRET=your-random-hex-string    # openssl rand -hex 32
DB_TYPE=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASS=your-password
DB_NAME=knowledge_base
APP_ENV=development
CORS_ORIGINS=http://localhost:8000
```

### 3. 初始化数据库

```bash
python scripts/init_db.py        # 首次初始化
python scripts/migrate_db.py     # 增量迁移
```

### 4. 配置模型

编辑 `config/models.json`，或在 **系统配置 → 模型配置** 界面修改。

支持三个模型配置：
- **LLM**：问答生成（qwen3.6-plus / llama3 / gpt-4o 等）
- **Embedding**：文本向量化（text-embedding-v3 / bge-m3 等）
- **Reranker**：结果重排（qwen3-vl-rerank）

### 5. 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问 `http://localhost:8000`，默认管理员：`admin` / `admin123`

### 6. OCR 配置（可选）

PDF 文档解析使用 PaddleOCR，需安装依赖：

```bash
pip install paddlepaddle paddleocr
```

模型会在首次使用时自动下载到 `~/.paddlex/official_models/`。支持的功能：
- **版面检测**：自动识别文字、表格、图片、公式等区域
- **文字识别**：PP-OCRv5_server 模型
- **表格识别**：HTML 格式输出，自动转 Markdown
- **阅读顺序**：双栏/多栏文档自适应排序

## 智能问答流程

```
用户提问 → JWT认证 → 权限校验 → 查询改写(多轮时) → 查缓存
  → Embedding向量化 → 向量检索(ChromaDB) + BM25检索(jieba)
  → RRF融合 → qwen3-vl-rerank重排 → LLM生成回答 → 写缓存 → 返回
```

### 检索链路详解

| 步骤 | 说明 | 代码位置 |
|------|------|----------|
| 查询改写 | 有对话历史时，LLM 将指代问题改写为独立查询 | `core/llm.py` → `rewrite_query()` |
| 向量检索 | ChromaDB 语义相似度匹配 | `core/vectorstore.py` → `query()` |
| BM25 检索 | jieba 中文分词 + BM25 关键词匹配 | `core/hybrid_search.py` → `BM25Index` |
| RRF 融合 | Reciprocal Rank Fusion 合并两路结果 | `core/hybrid_search.py` → `rrf_fusion()` |
| 重排序 | qwen3-vl-rerank 对结果二次排序 | `core/reranker.py` → `rerank()` |
| 回答生成 | LLM 基于检索上下文生成回答 | `core/llm.py` → `generate_answer()` |

### 多轮对话

- 自动创建对话，历史消息存入 `conversation` / `conversation_turn` 表
- 传递最近 3 轮上下文给 LLM 用于查询改写和回答生成
- 左侧对话列表支持切换历史会话

### 查询缓存

- 内存 TTL 缓存，正常结果 1 小时，拒答 5 分钟
- `GET /api/cache/stats` / `POST /api/cache/clear`

## 功能概览

| 页面 | 功能 | 权限 |
|---|---|---|
| 登录页 | 用户名密码登录，JWT 认证 | 全员 |
| 仪表盘 | 统计卡片、7天问答趋势、热门知识库、待处理事项 | 全员 |
| 知识库列表 | 创建/查看/删除知识库 | 全员（删除需 admin） |
| 知识库详情 | 文档管理、分块查看、部门授权设置 | 查看全员，编辑需 admin |
| 文档上传 | 三步向导，三种分块策略，同名文件替换确认，PDF OCR 异步处理+按页进度 | admin/kb_admin |
| 分块查看 | 搜索/排序/折叠/编辑/删除 | 查看全员，编辑需 admin |
| 智能问答 | 多轮对话、混合检索、预设问题、Markdown 渲染、引用标注、点赞/点踩 | 全员 |
| 用户管理 | CRUD、筛选、分页 | super_admin |
| 部门管理 | 树形结构 | super_admin |
| 审计日志 | 操作记录筛选 | super_admin |
| 质量监控 | 差评率/无结果率/延迟统计、反馈列表 | super_admin |
| **效果评测** | **评测集自动生成、LLM-as-Judge 多维度评分、评测记录** | **super_admin** |
| 系统配置 | LLM/Embedding/Reranker/Prompt/检索策略/缓存配置 | super_admin |

### 效果评测系统

从知识库文档自动生成评测数据，通过 LLM-as-Judge 进行多维度系统化评估。

**评测集生成**：选择知识库 → LLM 自动生成 5 类测试问题：
- 事实型（40%）：答案直接在文档中
- 超范围（20%）：文档中完全不涉及的主题（测拒答能力）
- 多文档（15%）：需综合多个文档片段才能回答（测综合能力）
- 歧义（15%）：用户提问模糊，系统应要求澄清（测澄清能力）
- 错误前提（10%）：问题中的假设与文档矛盾（测纠错能力）

**9 维度自动评分**：

| 维度 | 说明 |
|------|------|
| 检索精确率 | 检索到的内容与问题的相关程度 |
| 检索召回率 | 关键信息是否被检索到 |
| 排序质量 | 最相关的内容是否排在前面 |
| 忠实度 | 回答是否基于检索内容，有无编造 |
| 相关性 | 回答是否针对问题 |
| 完整性 | 回答是否覆盖关键信息 |
| 拒答准确性 | 超出范围的问题是否正确拒答 |
| 时效性 | 对过期信息的处理是否恰当 |
| 多跳推理 | 跨文档推理的准确性 |

**评测 Prompt 管理**：独立于系统 Prompt，可在「效果评测 → Prompt 管理」Tab 中自定义生成和打分的 Prompt。

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
| POST | `/api/upload` | 上传文档（50MB限制，PDF/DOCX/MD/TXT，PDF 走 OCR 异步处理） |
| GET | `/api/upload/progress/{task_id}` | 查询 PDF 上传处理进度（按页更新） |
| GET | `/api/documents?kb_id=xxx` | 文档列表 |
| DELETE | `/api/documents/{filename}` | 删除文档 |
| GET | `/api/documents/{filename}/chunks` | 查看分块 |
| PUT/DELETE | `/api/chunks/{chunk_id}` | 编辑/删除分块（需 admin） |

### 问答 & 对话
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/query` | 语义问答（question, top_k, kb_id, use_hybrid, use_reranker, history, conv_id） |
| POST | `/api/reindex` | 重建向量索引 |
| GET/POST | `/api/conversations` | 对话列表/创建 |
| GET/POST | `/api/conversations/{id}/turns` | 对话轮次 |
| POST/GET | `/api/feedback` | 提交/查看反馈 |

### 用户 & 部门
| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/users` | 用户列表/创建 |
| PUT/DELETE | `/api/users/{id}` | 更新/禁用用户 |
| GET/POST/DELETE | `/api/departments` | 部门 CRUD |

### 授权 & 配置 & 统计
| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST/DELETE | `/api/kb-access` | 知识库部门授权 |
| GET/POST | `/api/config/models` | 模型配置（LLM/Embedding/Reranker） |
| GET/POST | `/api/config/prompts` | Prompt 模板 |
| GET/POST | `/api/config/eval-prompts` | 评测 Prompt 模板 |
| GET | `/api/audit-logs` | 审计日志（仅 super_admin） |
| GET | `/api/stats/dashboard` | 仪表盘统计 |
| GET | `/api/stats/quality` | 质量监控统计 |
| GET | `/api/cache/stats` | 缓存统计 |

### 效果评测
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/eval/datasets` | 评测集列表 |
| POST | `/api/eval/generate` | 生成评测集（kb_ids, count） |
| DELETE | `/api/eval/datasets/{id}` | 删除评测集 |
| GET | `/api/eval/datasets/{id}/questions` | 获取评测问题列表 |
| POST/DELETE | `/api/eval/datasets/{id}/questions/{qid}` | 编辑/删除单个问题 |
| POST | `/api/eval/run/{dataset_id}` | 启动评测运行 |
| GET | `/api/eval/runs` | 评测运行记录 |
| GET | `/api/eval/runs/{id}/results` | 评测结果详情（含多维度分数） |

## 项目结构

```
knowledge-base/
├── .env / .env.example         # 环境变量
├── app/
│   ├── main.py                 # FastAPI 入口 + 中间件
│   ├── api/
│   │   ├── routes.py           # 路由聚合（13个子路由）
│   │   ├── deps.py             # 认证 + 权限检查
│   │   ├── auth_routes.py      # 登录
│   │   ├── user_routes.py      # 用户 CRUD
│   │   ├── dept_routes.py      # 部门 CRUD
│   │   ├── kb_routes.py        # 知识库 CRUD
│   │   ├── doc_routes.py       # 文档/分块管理
│   │   ├── query_routes.py     # 问答/改写/缓存
│   │   ├── config_routes.py    # 模型/Prompt 配置
│   │   ├── audit_routes.py     # 审计日志
│   │   ├── access_routes.py    # 授权管理
│   │   ├── conversation_routes.py  # 对话/反馈
│   │   ├── stats_routes.py     # 统计数据
│   │   └── eval_routes.py      # 评测管理 + 评测 Prompt
│   ├── core/
│   │   ├── auth.py             # JWT 认证
│   │   ├── database.py         # 数据库连接
│   │   ├── embedding.py        # 向量化（重试+缓存）
│   │   ├── llm.py              # LLM 调用 + 查询改写
│   │   ├── loader.py           # 文档加载（PDF 统一走 OCR）
│   │   ├── splitter.py         # 文本分块（三种策略）
│   │   ├── vectorstore.py      # 向量存储 + 混合检索
│   │   ├── hybrid_search.py    # BM25 + RRF 融合
│   │   ├── reranker.py         # qwen3-vl-rerank 重排
│   │   ├── cache.py            # 查询缓存
│   │   ├── progress.py         # 上传任务进度追踪
│   │   ├── eval_generator.py   # 评测集生成（LLM）
│   │   ├── eval_runner.py      # 评测执行（检索+生成+Judge评分）
│   │   └── ocr/                # OCR 模块
│   │       ├── __init__.py
│   │       ├── engine.py       # OCREngine 核心引擎
│   │       ├── postprocess.py  # 后处理（JSON + Markdown）
│   │       └── utils.py        # 工具函数
│   ├── models/
│   │   ├── models.py           # ORM（14 张表，外键级联）
│   │   └── schema.py           # Pydantic 模型
│   └── static/
│       ├── index.html          # 页面模板（13个页面 + 弹窗）
│       ├── style.css           # 样式
│       └── js/
│           ├── api.js          # API 封装（Token 注入、错误处理）
│           ├── router.js       # Hash 路由
│           ├── components/
│           │   └── ui.js       # 分页、模态框、Tab、Markdown
│           └── pages/          # 13 个页面模块
│               ├── auth.js     # 登录
│               ├── dashboard.js
│               ├── kb.js       # 知识库管理
│               ├── upload.js   # 文档上传
│               ├── chunks.js   # 分块查看
│               ├── qa.js       # 智能问答
│               ├── users.js
│               ├── depts.js
│               ├── audit.js
│               ├── config.js   # 系统配置
│               ├── quality.js  # 质量监控
│               └── eval.js     # 效果评测
├── config/
│   ├── models.json             # 模型配置（gitignore）
│   ├── models.json.example     # 模型配置示例
│   ├── prompts.json            # 问答/Prompt 模板
│   └── eval_prompts.json       # 评测专用 Prompt 模板
├── scripts/
│   ├── init_db.py              # 数据库初始化
│   ├── migrate_db.py           # 增量迁移
│   └── ocr_cli.py              # OCR 命令行工具
├── data/
│   └── chroma_db/              # ChromaDB 持久化数据
├── HIGHLIGHTS.md               # 产品亮点
├── TODO.md                     # 功能路线图
├── prototype.html              # UI 原型
├── requirements.txt
└── README.md
```

## 数据库表（14 张）

| 表 | 用途 | 级联 |
|---|---|---|
| `user` | 用户 | — |
| `department` | 部门树 | — |
| `knowledge_base` | 知识库 | — |
| `document` | 文档元数据（SHA-256 去重） | — |
| `kb_department_access` | 知识库×部门授权 | KB/部门删除时级联 |
| `kb_user_access` | 知识库×用户授权 | KB/用户删除时级联 |
| `conversation` | 会话 | 用户删除时级联 |
| `conversation_turn` | 对话轮次 | 对话删除时级联 |
| `qa_feedback` | 用户反馈 | 轮次/用户删除时级联 |
| `audit_log` | 审计日志 | — |
| `eval_dataset` | 评测集 | — |
| `eval_question` | 评测问题 | 评测集删除时级联 |
| `eval_run` | 评测运行记录 | 评测集删除时级联 |
| `eval_result` | 评测结果（含多维度分数） | 评测运行删除时级联 |

## 权限体系

| 角色 | 可见菜单 | 知识库 | 文档 | 分块 | 审计/评测 |
|---|---|---|---|---|---|
| super_admin | 全部（含效果评测） | 全权 | 上传/删除 | 编辑/删除 | 查看 |
| kb_admin | 业务 | 管理设置 | 上传/删除 | 编辑/删除 | ✗ |
| user | 业务 | 只读查看 | 只读 | 只读 | ✗ |

## 分块策略

| 策略 | 说明 | 适用场景 |
|---|---|---|
| 语义分块（默认） | 按句子边界拆分 | 通用 |
| 固定长度 | 按字符数硬切+重叠 | 简单文本 |
| 结构分析 | 按 Markdown 标题层级 | 技术文档 |

## 安全说明

- JWT Secret / 数据库密码通过 `.env` 配置，**切勿使用默认值**
- 生产环境 `APP_ENV=production` 启用 CORS 域名限制
- 文件上传限制 50MB，仅允许 PDF/DOCX/MD/TXT
- `.env` 已加入 `.gitignore`

## 项目实施历程

### Phase 1 — MVP 基础搭建
| 提交 | 内容 |
|------|------|
| `52feb9f` | RAG 知识库问答系统 MVP（FastAPI + ChromaDB + 前端 SPA） |
| `493346b` | 前端 12 个页面（登录、仪表盘、知识库、上传、问答、用户、部门、审计、配置等） |
| `7d3b127` | 产品原型文件 + PRD + 设计方案文档 |
| `1667a2f` | 数据库层搭建（SQLite + SQLAlchemy，10 张核心表） |
| `fcc96ee` | 模型配置持久化 + Ollama 支持 + 索引重建 + 知识库文档隔离 |

### Phase 2 — 文档管理完善
| 提交 | 内容 |
|------|------|
| `c9afc53` | 文档分块查看/编辑（搜索、排序、折叠、编辑、删除） |
| `10d4e97` | 上传流程重写（三步向导：选文件→配策略→上传结果） |
| `cc71c91` | Prompt 管理系统（问答/改写/拒答多类型可配置） |
| `490ebce` | 语义分块 + 结构分析分块策略 + Embedding 重试机制 |
| `c93fe64` | 问答预设问题按钮 |
| `96a8a2b` | 问答回答 Markdown 渲染 |
| `7086c15` | 上下文长度限制 + LLM 切换 qwen-turbo（40s→2s） |

### Phase 3 — 安全与架构
| 提交 | 内容 |
|------|------|
| `6891195` | JWT 认证 + 知识库权限体系 + 审计日志 + 用户管理 |
| `67c1f44` | 权限体系简化 + 前端模块化拆分 + 分页 |
| `acb1d30` | 架构重构：安全加固 + 前后端模块化 + CORS |
| `ecb0eb7` | 混合检索（向量+BM25+RRF）+ 多轮对话 + 反馈 + 缓存 + 文档版本管理 |
| `f503c58` | 同名文件上传弹窗确认替换 |

### Phase 4 — 质量监控与统计
| 提交 | 内容 |
|------|------|
| `91d64e7` | 质量监控页展示用户反馈记录 |
| `2915f0a` | 统计 API — 仪表盘和质量监控数据接入 |
| `d15bdb4` | 仪表盘待处理事项接真实数据 |
| `fcd89d7` | 全面 Bug 修复 + 架构优化 + 代码清理 |

### Phase 5 — 检索增强
| 提交 | 内容 |
|------|------|
| `232b49b` | 查询改写 + qwen3-vl-rerank 重排 |
| `9fb59c7` | 问答页知识库选择器 + 对话删除 + 级联删除反馈 |
| `9997373` | 产品核心亮点文档 HIGHLIGHTS.md |

### Phase 6 — 效果评测系统
| 提交 | 内容 |
|------|------|
| `9c38ae2` | 评测集自动生成 + LLM-as-Judge 9 维度评分 |
| `745a7fd` | MySQL 迁移脚本兼容修复 |
| `f1306ee`~`b1e48bf` | 评测系统 4 轮 Bug 修复（API 调用、弹窗布局、Judge 判定） |
| `ed8965a` | 文档归档（PRD v3.0 + 设计方案 v3.0） |

### Phase 7 — OCR 与异步处理
| 提交 | 内容 |
|------|------|
| `1a378ee` | PaddleOCR PDF 解析（版面检测+文字识别+表格识别） + 异步上传按页进度 + 级联删除修复 |

---

## 分期规划

### ✅ P0 — 核心链路
文档上传/分块/向量化/检索/问答，用户/部门/知识库 CRUD，权限体系，审计日志

### ✅ P1 — 架构 + 功能
前后端模块化、安全加固、混合检索（向量+BM25+RRF）、多轮对话、查询改写、qwen3-vl-rerank 重排、查询缓存、用户反馈、文档版本管理、效果评测系统（LLM-as-Judge 多维度评分）、PaddleOCR PDF 解析（版面检测+文字识别+表格识别+按页进度）

### 🔲 P2 — 增强
- Redis 分布式缓存
- 审计日志导出

### 🔲 P3 — 规模化
- SSO 单点登录
- 向量数据库迁移（Milvus / Qdrant）
- 异步任务队列（Celery）
