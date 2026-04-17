# RAG 知识库管理系统

基于 RAG（Retrieval-Augmented Generation）架构的企业级智能知识库管理与问答平台。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + Uvicorn |
| 数据库 | MySQL 9.6（关系型）+ SQLite（备选） |
| 向量数据库 | ChromaDB（持久化） |
| ORM | SQLAlchemy |
| 认证 | PyJWT + Werkzeug（密码哈希） |
| LLM | OpenAI 兼容接口（支持 DashScope / Ollama / OpenAI / 自定义） |
| Embedding | OpenAI 兼容接口（同上） |
| 前端 | 纯 HTML + CSS + JavaScript（SPA 单页应用） |

## 快速开始

### 1. 安装依赖

```bash
cd knowledge-base
pip install -r requirements.txt
```

依赖列表：
```
fastapi, uvicorn, python-multipart, openai, chromadb,
python-docx, PyMuPDF, sqlalchemy, pyjwt, werkzeug, pymysql, cryptography
```

### 2. 配置数据库

默认连接 MySQL（地址 `172.26.32.1:3306`），可在 `app/core/database.py` 修改。

初始化表和默认数据：
```bash
python scripts/init_db.py
```

### 3. 配置模型

编辑 `config/models.json`，或启动后在 **系统配置 → 模型配置** 界面修改。

支持的提供商：
- **阿里云 DashScope**（云端，需 API Key）
- **Ollama**（本地部署，无需 API Key）
- **OpenAI**（需 API Key）
- **自定义 API**（任意 OpenAI 兼容接口）

### 4. 启动服务

```bash
python -m app.main
```

服务默认运行在 `http://localhost:8000`

## 功能概览

### 前端界面（12 个页面）

| 页面 | 功能 |
|---|---|
| 登录页 | 用户名密码登录 |
| 仪表盘 | 统计卡片、问答趋势图表、待处理事项 |
| 知识库列表 | 创建/搜索/筛选/删除知识库 |
| 知识库详情 | 文档管理（上传/删除/查看分块）、权限设置、模型配置、统计分析 |
| 文档上传 | 三步向导（选文件→配策略→上传结果），支持三种分块策略，完成后可跳转查看分块 |
| 分块查看/编辑 | 搜索/排序/折叠/编辑/删除单个分块 |
| 智能问答 | 多会话管理、预设问题、Markdown 渲染、引用标注、点赞/点踩反馈、60s 超时保护 |
| 用户管理 | CRUD、批量导入 |
| 部门管理 | 树形部门结构 |
| 权限管理 | 角色定义、知识库授权矩阵 |
| 审计日志 | 操作记录筛选 |
| 质量监控 | 差评率、无结果率、反馈审核 |
| 系统配置 | 通用设置、模型配置、Prompt 管理、检索策略、缓存设置 |

### API 接口

#### 文档管理

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/upload` | 上传文档（form: file, kb_id, chunk_size, chunk_overlap, chunk_strategy, heading_level） |
| GET | `/api/documents?kb_id=xxx` | 获取文档列表 |
| DELETE | `/api/documents/{filename}?kb_id=xxx` | 删除文档 |
| POST | `/api/query` | 语义问答（body: question, top_k, kb_id），上下文自动限制 3000 字符 |
| POST | `/api/reindex?kb_id=xxx` | 重建向量索引 |

#### 分块管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/documents/{filename}/chunks?kb_id=xxx` | 获取文档所有分块 |
| PUT | `/api/chunks/{chunk_id}` | 编辑分块（自动重新 Embedding） |
| DELETE | `/api/chunks/{chunk_id}` | 删除单个分块 |

#### 知识库管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/knowledge-bases` | 知识库列表 |
| POST | `/api/knowledge-bases` | 创建知识库 |
| DELETE | `/api/knowledge-bases/{id}` | 删除知识库（软删除+清除向量） |

#### 用户与部门

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/users` | 用户列表 |
| POST | `/api/users` | 创建用户 |
| DELETE | `/api/users/{id}` | 禁用用户 |
| GET | `/api/departments` | 部门列表 |
| POST | `/api/departments` | 创建部门 |
| DELETE | `/api/departments/{id}` | 删除部门 |

#### 系统配置

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/config/models` | 获取模型配置 |
| POST | `/api/config/models` | 保存模型配置 |
| GET | `/api/config/prompts` | 获取所有 Prompt 模板 |
| POST | `/api/config/prompts` | 保存 Prompt 模板 |

### Prompt 管理

系统支持多种 Prompt 模板，可在 **系统配置 → Prompt 管理** 界面编辑：

| 类型 | 用途 | 变量 |
|---|---|---|
| `qa` | 问答主 Prompt | `{context}` `{question}` `{history}` |
| `rewrite` | 多轮对话指代消解 | `{history}` `{question}` |
| `refuse` | 检索不足时拒答话术 | 无 |

模板存储于 `config/prompts.json`，修改后立即生效。

### 智能问答特性

- **预设问题**：空对话状态下显示快捷提问按钮，点击即问
- **Markdown 渲染**：LLM 返回的 Markdown 格式自动解析（加粗、列表、代码块、标题等）
- **上下文长度控制**：传给 LLM 的上下文自动限制 3000 字符，避免响应过慢
- **引用标注**：回答中的 `[来源: 文档名]` 自动渲染为蓝色标签
- **超时保护**：60 秒超时，超时后提示用户

## 项目结构

```
knowledge-base/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── api/
│   │   └── routes.py        # API 路由（所有接口）
│   ├── core/
│   │   ├── config.py         # 配置加载
│   │   ├── database.py       # 数据库连接（MySQL/SQLite）
│   │   ├── embedding.py      # 向量化（支持多提供商，动态配置）
│   │   ├── llm.py            # LLM 调用（支持多提供商，Prompt 可配置）
│   │   ├── loader.py         # 文档加载（TXT/PDF/DOCX/MD）
│   │   ├── splitter.py       # 文本分块
│   │   └── vectorstore.py    # 向量存储（按知识库隔离）
│   ├── models/
│   │   ├── models.py         # SQLAlchemy ORM 模型
│   │   └── schema.py         # Pydantic 请求/响应模型
│   └── static/
│       └── index.html        # 前端 SPA（12+页面）
├── config/
│   ├── models.json           # 模型配置（含 API Key，已 gitignore）
│   ├── models.json.example   # 配置模板
│   └── prompts.json          # Prompt 模板（可追踪）
├── data/
│   ├── chroma_db/            # ChromaDB 向量数据
│   ├── uploads/              # 上传文件存储
│   └── knowledge.db          # SQLite 备份数据库
├── scripts/
│   └── init_db.py            # 数据库初始化脚本
├── venv/                     # Python 虚拟环境
├── requirements.txt
├── prototype.html            # UI 原型参考
└── README.md
```

## 数据库表（10 张）

| 表名 | 用途 |
|---|---|
| `user` | 用户管理（角色: super_admin / kb_admin / user） |
| `department` | 部门树（path 路径继承） |
| `knowledge_base` | 知识库 |
| `document` | 文档元数据（SHA-256 去重） |
| `kb_department_access` | 知识库 × 部门授权 |
| `kb_user_access` | 知识库 × 用户授权 |
| `conversation` | 会话 |
| `conversation_turn` | 对话轮次 |
| `qa_feedback` | 用户反馈（点赞/点踩） |
| `audit_log` | 审计日志 |

默认部门结构：
```
🏢 总公司 (/总公司)
  ├─ 📂 研发部 (/总公司/研发部)
  └─ 📂 销售部 (/总公司/销售部)
```

默认管理员：`admin` / `admin123`（隶属总公司，super_admin 角色）

## 分块策略

上传文档时可选择三种分块策略：

| 策略 | 说明 | 适用场景 |
|---|---|---|
| **语义分块**（默认） | 按句子边界拆分，保证语义完整，块间按完整句子重叠 | 通用场景，推荐优先使用 |
| **固定长度** | 按固定字符数硬切，支持字符重叠 | 简单文本、对分块速度要求高 |
| **结构分析** | 按 Markdown 标题层级切分，超长段落自动二次拆分 | 带标题结构的文档（Markdown、技术文档） |

参数说明：
- **chunk_size**：每块最大字符数（默认 512）
- **chunk_overlap**：块间重叠字符数，语义/固定策略使用（默认 64）
- **heading_level**：结构分析策略的切分层级（H2 或 H3）

## 权限体系

### 角色（系统级）

| 角色 | 可见 KB | 操作权限 |
|---|---|---|
| super_admin | 全部 | 全权（管理用户/部门/配置/审计日志） |
| kb_admin | 所属部门有授权的 KB | 上传/删除文档、修改 KB 设置 |
| user | 所属部门有授权的 KB | 查看文档、智能问答 |

### 权限判定

```
super_admin → 全部 KB，admin 权限
其他用户 → 查 kb_department_access，所在部门有授权即可访问
  ├─ kb_admin → admin 权限（可管理）
  └─ user → viewer 权限（只读）
```

### 前端控制

- 侧边栏菜单按角色显示/隐藏
- 知识库操作按钮按角色显示/隐藏
- 查询接口强制过滤，无权限 KB 的文档不可检索

## 模型迁移

更换 Embedding 模型后，所有文档需要重新向量化。操作步骤：

1. **系统配置 → 模型配置**：修改 Embedding 提供商和模型名
2. 点击 **保存配置**
3. 点击 **重建全部索引**（或只重建指定知识库）

系统会从向量库中取出原始文本，用新模型重新计算向量，不需要重新上传文件。

## 分期规划

### ✅ 第一期 P0 — 核心链路

- [x] FastAPI 后端框架 + 前端代码拆分（HTML/CSS/JS 分离）
- [x] MySQL 数据库（10 张表）
- [x] 用户管理（CRUD + 编辑/禁用/启用 + 部门/角色/状态筛选 + 分页）
- [x] 部门管理（树形结构 + CRUD）
- [x] 知识库管理（CRUD + 权限隔离 + 统计显示 + 分页）
- [x] 文档管理（列表 + 大小/分块数 + 查看/删除 + 分页）
- [x] 文档上传（三种分块策略：固定长度 / 语义分块 / 结构分析）
- [x] Embedding 向量化（多提供商 + 失败重试 + 配置缓存）
- [x] 语义检索 + LLM 问答（超时保护 + 上下文限制 + 权限过滤）
- [x] Prompt 管理（界面可编辑）
- [x] 智能问答（预设问题 + Markdown 渲染 + 引用标注）
- [x] 模型配置持久化
- [x] 索引重建
- [x] 统计存库（Document 表，上传时写入，不再实时计算）
- [x] 知识库设置（编辑名称/描述/模型配置）
- [x] 前端 SPA（10+ 页面，分页组件）

### ✅ 第二期 P1 — 权限与安全

- [x] JWT 认证 + API 权限中间件（登录/Token/401 拦截）
- [x] 角色权限控制（super_admin / kb_admin / user，前端菜单+按钮可见性）
- [x] 知识库权限体系（部门授权，三级权限：admin/editor/viewer）
- [x] 查询权限隔离（无 kb_id 时只搜索有权限的 KB）
- [x] 审计日志持久化（登录/上传/删除/查询等操作记录入库 + 分页查询）
- [ ] 混合检索（向量 + BM25 + RRF 融合）
- [ ] Cross-Encoder 精排（BGE-Reranker-v2-m3）
- [ ] 多轮会话 + 指代消解
- [ ] 用户反馈机制（联通后端）
- [ ] 查询缓存（Redis）
- [ ] 文档去重（SHA-256 + 版本管理）

### 🔲 第三期 P2 — 规模化

- [ ] SSO 单点登录
- [ ] 向量数据库迁移（Milvus / Qdrant）
- [ ] 异步任务队列（Celery）
- [ ] 质量监控面板
- [ ] 人工评估流程

## 参考文档

- `RAG知识库管理系统_PRD_v1.0.docx` — 产品需求文档
- `RAG知识库管理系统_整体设计方案_v2.docx` — 技术设计方案
- `prototype.html` — UI 原型参考
