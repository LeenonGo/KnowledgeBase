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

复制 `.env.example` 为 `.env`，修改配置：

```bash
cp .env.example .env
```

`.env` 文件内容：
```bash
# 安全密钥（生成方式: openssl rand -hex 32）
JWT_SECRET=your-random-hex-string

# 数据库
DB_TYPE=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASS=your-password
DB_NAME=knowledge_base

# 应用
APP_ENV=development
CORS_ORIGINS=http://localhost:8000
```

### 3. 初始化数据库

```bash
# 首次初始化（创建表 + 默认数据）
python scripts/init_db.py

# 增量迁移（添加新索引/约束，不覆盖数据）
python scripts/migrate_db.py
```

### 4. 配置模型

编辑 `config/models.json`，或启动后在 **系统配置 → 模型配置** 界面修改。

支持的提供商：DashScope / Ollama / OpenAI / 自定义 API

### 5. 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问 `http://localhost:8000`，默认管理员：`admin` / `admin123`

## 功能概览

| 页面 | 功能 | 权限 |
|---|---|---|
| 登录页 | 用户名密码登录，JWT 认证 | 全员 |
| 仪表盘 | 统计卡片、7天问答趋势、热门知识库、待处理事项 | 全员 |
| 知识库列表 | 创建/查看/删除知识库，显示授权部门 | 全员（删除需 admin） |
| 知识库详情 | 文档管理、分块查看、知识库设置（含部门授权） | 查看全员，编辑需 admin |
| 文档上传 | 三步向导，支持三种分块策略，同名文件替换确认 | admin/kb_admin |
| 分块查看 | 搜索/排序/折叠/编辑/删除 | 查看全员，编辑需 admin |
| 智能问答 | 多轮对话、混合检索、预设问题、Markdown 渲染、引用标注、点赞/点踩 | 全员 |
| 用户管理 | CRUD、筛选、分页 | super_admin |
| 部门管理 | 树形结构 | super_admin |
| 权限管理 | 角色权限说明 | super_admin |
| 审计日志 | 操作记录筛选 | super_admin |
| 质量监控 | 差评率/无结果率/延迟统计、反馈列表 | super_admin |
| 系统配置 | 模型/Prompt/检索策略/缓存配置 | super_admin |

## 检索特性

### 混合检索（向量 + BM25 + RRF）

- **向量检索**：ChromaDB 语义相似度匹配
- **BM25 检索**：jieba 中文分词 + BM25 关键词匹配
- **RRF 融合**：Reciprocal Rank Fusion 合并两路结果，k=60
- 前端可勾选「混合检索」开关

### 轻量精排

- 对 RRF 融合后的结果用向量余弦相似度二次排序
- 生产环境可替换为 Cross-Encoder（如 bge-reranker-v2-m3）

### 多轮对话

- 自动创建对话，历史消息存入 `conversation` / `conversation_turn` 表
- 传递最近 3 轮上下文给 LLM
- 左侧对话列表支持切换历史会话

### 查询缓存

- 内存 TTL 缓存，正常结果缓存 1 小时，拒答缓存 5 分钟
- `GET /api/cache/stats` 查看缓存统计
- `POST /api/cache/clear` 清空缓存
- 重建索引时自动清空缓存

## API 接口

### 认证
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/login` | 登录，返回 JWT Token |
| GET | `/api/me` | 当前用户信息 |

### 知识库
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/knowledge-bases` | 知识库列表（按权限过滤） |
| POST | `/api/knowledge-bases` | 创建知识库 |
| PUT | `/api/knowledge-bases/{id}` | 更新知识库 |
| DELETE | `/api/knowledge-bases/{id}` | 删除知识库（软删除） |

### 文档 & 分块
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/upload` | 上传文档（格式校验 + 50MB限制 + 同名替换） |
| GET | `/api/documents?kb_id=xxx` | 文档列表 |
| DELETE | `/api/documents/{filename}?kb_id=xxx` | 删除文档 |
| GET | `/api/documents/{filename}/chunks?kb_id=xxx` | 查看分块 |
| PUT | `/api/chunks/{chunk_id}` | 编辑分块（需 admin） |
| DELETE | `/api/chunks/{chunk_id}` | 删除分块（需 admin） |

### 问答 & 对话
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/query` | 语义问答（question, top_k, kb_id, use_hybrid, use_reranker） |
| POST | `/api/reindex` | 重建向量索引 |
| GET | `/api/conversations` | 对话列表 |
| POST | `/api/conversations` | 创建对话 |
| GET | `/api/conversations/{id}/turns` | 对话轮次 |
| POST | `/api/feedback` | 提交反馈（👍👎） |
| GET | `/api/feedback` | 反馈列表 |

### 用户 & 部门
| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/users` | 用户列表/创建 |
| PUT/DELETE | `/api/users/{id}` | 更新/禁用用户 |
| GET/POST | `/api/departments` | 部门列表/创建 |
| DELETE | `/api/departments/{id}` | 删除部门 |

### 授权 & 配置 & 统计
| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST/DELETE | `/api/kb-access` | 知识库部门授权 |
| GET/POST | `/api/config/models` | 模型配置 |
| GET/POST | `/api/config/prompts` | Prompt 模板 |
| GET | `/api/audit-logs` | 审计日志（仅 super_admin） |
| GET | `/api/stats/dashboard` | 仪表盘统计 |
| GET | `/api/stats/quality` | 质量监控统计 |
| GET | `/api/cache/stats` | 缓存统计 |

## 项目结构

```
knowledge-base/
├── .env                        # 环境变量（已 gitignore）
├── .env.example                # 环境变量模板
├── app/
│   ├── main.py                 # FastAPI 入口 + 中间件 + 异常处理
│   ├── api/
│   │   ├── routes.py           # 路由聚合
│   │   ├── deps.py             # 认证依赖 + 权限检查
│   │   ├── auth_routes.py      # 登录/用户信息
│   │   ├── user_routes.py      # 用户 CRUD
│   │   ├── dept_routes.py      # 部门 CRUD
│   │   ├── kb_routes.py        # 知识库 CRUD
│   │   ├── doc_routes.py       # 文档上传/分块管理
│   │   ├── query_routes.py     # 问答/缓存/重建索引
│   │   ├── config_routes.py    # 模型/Prompt 配置
│   │   ├── audit_routes.py     # 审计日志
│   │   ├── access_routes.py    # 知识库授权
│   │   ├── conversation_routes.py  # 对话历史/反馈
│   │   └── stats_routes.py     # 统计数据
│   ├── core/
│   │   ├── config.py           # 配置加载
│   │   ├── database.py         # 数据库连接（从 .env 读取）
│   │   ├── auth.py             # JWT 认证（从 .env 读取密钥）
│   │   ├── embedding.py        # 向量化（重试 + 缓存）
│   │   ├── llm.py              # LLM 调用（Prompt 可配置）
│   │   ├── loader.py           # 文档加载（TXT/PDF/DOCX/MD）
│   │   ├── splitter.py         # 文本分块（三种策略）
│   │   ├── vectorstore.py      # 向量存储 + 混合检索
│   │   ├── hybrid_search.py    # BM25 + RRF 融合
│   │   └── cache.py            # 查询缓存（内存 TTL）
│   ├── models/
│   │   ├── models.py           # SQLAlchemy ORM（10 张表，外键级联）
│   │   └── schema.py           # Pydantic 模型
│   └── static/
│       ├── index.html          # 页面骨架 + HTML 模板
│       ├── style.css           # 全局样式
│       └── js/
│           ├── api.js          # 统一 fetch + Token 注入
│           ├── router.js       # Hash 路由
│           ├── components/
│           │   └── ui.js       # 分页/模态框/Tab/Markdown
│           └── pages/
│               ├── auth.js     # 登录/登出
│               ├── dashboard.js
│               ├── kb.js       # 知识库管理 + 部门授权
│               ├── upload.js   # 文档上传
│               ├── qa.js       # 智能问答（多轮对话+反馈）
│               ├── users.js    # 用户管理
│               ├── depts.js    # 部门管理
│               ├── audit.js    # 审计日志
│               ├── config.js   # 系统配置
│               ├── chunks.js   # 分块查看/编辑
│               └── quality.js  # 质量监控+反馈列表
├── config/
│   ├── models.json             # 模型配置（已 gitignore）
│   └── prompts.json            # Prompt 模板
├── data/                       # 运行时数据（已 gitignore）
├── scripts/
│   ├── init_db.py              # 数据库初始化
│   └── migrate_db.py           # 增量迁移
├── prototype.html              # UI 原型参考
├── requirements.txt
└── README.md
```

## 数据库表（10 张）

| 表名 | 用途 | 级联删除 |
|---|---|---|
| `user` | 用户（super_admin / kb_admin / user） | — |
| `department` | 部门树（path + parent_id） | — |
| `knowledge_base` | 知识库 | — |
| `document` | 文档元数据（SHA-256 去重，联合唯一约束） | — |
| `kb_department_access` | 知识库 × 部门授权 | KB/部门删除时级联 |
| `kb_user_access` | 知识库 × 用户授权 | KB/用户删除时级联 |
| `conversation` | 会话 | 用户删除时级联 |
| `conversation_turn` | 对话轮次 | 对话删除时级联 |
| `qa_feedback` | 用户反馈（👍👎） | 轮次/用户删除时级联 |
| `audit_log` | 审计日志 | — |

## 权限体系

| 角色 | 可见菜单 | 知识库操作 | 分块操作 |
|---|---|---|---|
| super_admin | 全部 | 全权 | 编辑/删除 |
| kb_admin | 业务菜单 | 上传/删除文档、管理设置 | 编辑/删除 |
| user | 业务菜单 | 查看文档、智能问答 | 仅查看 |

## 分块策略

| 策略 | 说明 | 适用场景 |
|---|---|---|
| 语义分块（默认） | 按句子边界拆分，块间按完整句子重叠 | 通用 |
| 固定长度 | 按字符数硬切，支持重叠 | 简单文本 |
| 结构分析 | 按 Markdown 标题层级切分 | 技术文档 |

## 安全说明

- JWT Secret 通过环境变量配置，**切勿使用默认值**
- 数据库密码通过环境变量配置
- 生产环境需设置 `APP_ENV=development` 以启用 CORS 域名限制
- 文件上传限制 50MB，仅允许 PDF/DOCX/MD/TXT
- `.env` 文件已加入 `.gitignore`

## 分期规划

### ✅ P0 — 核心链路
文档上传/分块/向量化/检索/问答，用户/部门/知识库 CRUD，权限体系，审计日志

### ✅ P1 — 架构重构 + 产品功能
后端路由模块化、前端模块化 + Hash 路由、安全加固、对话历史、反馈 API、权限逻辑修通

### ✅ P1 产品功能
混合检索（向量 + BM25 + RRF）、轻量精排、多轮对话、用户反馈、查询缓存、文档版本管理

### 🔲 P2 — 检索增强
- Cross-Encoder 精排（bge-reranker-v2-m3）
- 查询改写（LLM 指代消解）
- Redis 分布式缓存

### 🔲 P3 — 规模化
- SSO 单点登录
- 向量数据库迁移（Milvus / Qdrant）
- 异步任务队列（Celery）
- 审计日志导出
