# RAG 知识库管理系统

基于 RAG（Retrieval-Augmented Generation）架构的企业级智能知识库管理与问答平台。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + Uvicorn |
| 数据库 | MySQL（关系型）+ SQLite（备选） |
| 向量数据库 | ChromaDB（持久化，按 metadata.kb_id 隔离） |
| ORM | SQLAlchemy |
| 认证 | PyJWT + Werkzeug（密码哈希） |
| LLM | OpenAI 兼容接口（支持 DashScope / Ollama / OpenAI / 自定义） |
| Embedding | OpenAI 兼容接口（同上） |
| Reranker | qwen3-vl-rerank（DashScope）/ 兼容 API |
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
| 文档上传 | 三步向导，三种分块策略，同名文件替换确认 | admin/kb_admin |
| 分块查看 | 搜索/排序/折叠/编辑/删除 | 查看全员，编辑需 admin |
| 智能问答 | 多轮对话、混合检索、预设问题、Markdown 渲染、引用标注、点赞/点踩 | 全员 |
| 用户管理 | CRUD、筛选、分页 | super_admin |
| 部门管理 | 树形结构 | super_admin |
| 审计日志 | 操作记录筛选 | super_admin |
| 质量监控 | 差评率/无结果率/延迟统计、反馈列表 | super_admin |
| 系统配置 | LLM/Embedding/Reranker/Prompt/检索策略/缓存配置 | super_admin |

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
| POST | `/api/upload` | 上传文档（50MB限制，PDF/DOCX/MD/TXT） |
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
| GET | `/api/audit-logs` | 审计日志（仅 super_admin） |
| GET | `/api/stats/dashboard` | 仪表盘统计 |
| GET | `/api/stats/quality` | 质量监控统计 |
| GET | `/api/cache/stats` | 缓存统计 |

## 项目结构

```
knowledge-base/
├── .env / .env.example         # 环境变量
├── app/
│   ├── main.py                 # FastAPI 入口 + 中间件
│   ├── api/
│   │   ├── routes.py           # 路由聚合（12个子路由）
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
│   │   └── stats_routes.py     # 统计数据
│   ├── core/
│   │   ├── auth.py             # JWT 认证
│   │   ├── database.py         # 数据库连接
│   │   ├── embedding.py        # 向量化（重试+缓存）
│   │   ├── llm.py              # LLM 调用 + 查询改写
│   │   ├── loader.py           # 文档加载
│   │   ├── splitter.py         # 文本分块（三种策略）
│   │   ├── vectorstore.py      # 向量存储 + 混合检索
│   │   ├── hybrid_search.py    # BM25 + RRF 融合
│   │   ├── reranker.py         # qwen3-vl-rerank 重排
│   │   └── cache.py            # 查询缓存
│   ├── models/
│   │   ├── models.py           # ORM（10 张表，外键级联）
│   │   └── schema.py           # Pydantic 模型
│   └── static/
│       ├── index.html          # 页面模板
│       ├── style.css           # 样式
│       └── js/                 # 14 个模块化 JS 文件
├── config/
│   ├── models.json             # 模型配置（gitignore）
│   └── prompts.json            # Prompt 模板
├── scripts/
│   ├── init_db.py              # 数据库初始化
│   └── migrate_db.py           # 增量迁移
├── HIGHLIGHTS.md               # 产品亮点
├── prototype.html              # UI 原型
├── requirements.txt
└── README.md
```

## 数据库表（10 张）

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

## 权限体系

| 角色 | 可见菜单 | 知识库 | 文档 | 分块 | 审计日志 |
|---|---|---|---|---|---|
| super_admin | 全部 | 全权 | 上传/删除 | 编辑/删除 | 查看 |
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

## 分期规划

### ✅ P0 — 核心链路
文档上传/分块/向量化/检索/问答，用户/部门/知识库 CRUD，权限体系，审计日志

### ✅ P1 — 架构 + 功能
前后端模块化、安全加固、混合检索（向量+BM25+RRF）、多轮对话、查询改写、qwen3-vl-rerank 重排、查询缓存、用户反馈、文档版本管理

### 🔲 P2 — 增强
- Redis 分布式缓存
- 审计日志导出

### 🔲 P3 — 规模化
- SSO 单点登录
- 向量数据库迁移（Milvus / Qdrant）
- 异步任务队列（Celery）
