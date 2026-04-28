# RAG 知识库管理系统

基于 RAG 架构的企业级智能知识库管理与问答平台。15 分钟部署上线，支持多部门权限隔离、混合检索、多轮对话、效果评测。

**核心能力**
- **三种分块策略**：语义分块 / 结构分析 / 固定长度，用户可选
- **混合检索**：向量语义 + BM25 关键词 + RRF 融合，精确关键词也能找到
- **部门权限隔离**：部门级授权 + 三级权限，检索时自动过滤
- **多轮对话**：上下文自动传递，像跟同事聊天一样问知识库
- **查询缓存**：重复问题 <100ms 返回，省 60% LLM 费用
- **反馈闭环**：用户 👍👎 + 质量监控，持续优化有数据支撑
- **效果评测**：LLM-as-Judge 9 维度自动评分
- **OCR 解析**：PaddleOCR 版面检测 + 文字识别 + 表格识别
- **Agent 模式**（v4.0 新增）：LLM 自主决策工具调用，支持跨知识库对比、文档总结等多步骤推理，工具层权限代理确保零越权

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
| 前端 | HTML + CSS + JavaScript（SPA + Hash 路由） |

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

## 功能概览

| 页面 | 功能 | 权限 |
|---|---|---|
| 登录页 | JWT 认证 | 全员 |
| 仪表盘 | 统计卡片、7天趋势、热门知识库 | 全员 |
| 知识库列表 | 创建/查看/删除，部门选择 | 全员（删除需 admin） |
| 知识库详情 | 文档管理、分块查看、部门授权 | 查看全员，编辑需 admin |
| 文档上传 | 三步向导、多种分块策略、PDF OCR 异步处理+按页进度、支持 PDF/Word/Excel/CSV/PPT/TXT/Markdown | admin/kb_admin |
| 分块查看 | 搜索/排序/折叠/编辑/删除 | 查看全员，编辑需 admin |
| 智能问答 | 多轮对话、混合检索、Query 润色、预设问题、Markdown 渲染、点赞/点踩 | 全员 |
| 用户管理 | CRUD、筛选、分页 | super_admin |
| 部门管理 | 树形结构 | super_admin |
| 审计日志 | 操作记录筛选 | super_admin |
| 质量监控 | 差评率/无结果率/延迟统计、反馈列表 | super_admin |
| 效果评测 | 评测集自动生成、LLM-as-Judge 9 维度评分 | super_admin |
| 系统配置 | LLM/Embedding/Reranker/Prompt/检索策略 | super_admin |

---

## 智能问答流程

```
用户提问 → JWT认证 → 权限校验 → 查询改写(多轮时) → 查缓存
  → Query润色(纠错+扩展+关键词) → Embedding向量化 → 向量检索(ChromaDB) + BM25检索(jieba)
  → RRF融合 → qwen3-rerank重排 → LLM生成回答 → 写缓存 → 返回
```

| 步骤 | 说明 | 代码位置 |
|------|------|----------|
| 查询改写 | 有对话历史时，LLM 将指代问题改写为独立查询 | `core/llm.py` |
| 向量检索 | ChromaDB 语义相似度匹配 | `core/vectorstore.py` |
| BM25 检索 | jieba 中文分词 + BM25 关键词匹配 | `core/hybrid_search.py` |
| RRF 融合 | Reciprocal Rank Fusion 合并两路结果 | `core/hybrid_search.py` |
| 重排序 | qwen3-rerank 对结果二次排序 | `core/reranker.py` |


---

## 效果评测

从知识库文档自动生成评测数据，通过 LLM-as-Judge 进行多维度评估。

**评测集生成**：LLM 自动生成 5 类测试问题：
- 事实型（40%）、超范围（20%）、多文档（15%）、歧义（15%）、错误前提（10%）

**9 维度评分**：检索精确率、检索召回率、排序质量、忠实度、相关性、完整性、拒答准确性、时效性、多跳推理

---

## Agent 模式（v4.0 新增）

LLM 自主决策工具调用，支持多步骤推理。开启后 Agent 自主决定调用哪些工具、以什么顺序组合。

**工具列表：**
| 工具 | 功能 | 权限 |
|---|---|---|
| search_kb | 知识库语义检索 | viewer |
| list_kb | 列出可访问知识库 | 自动过滤 |
| get_doc_content | 获取文档全文 | viewer |
| summarize_doc | 文档摘要生成 | viewer |
| list_docs | 列出知识库文档 | viewer |

**执行流程：** 用户提问 → LLM 判断是否需要工具 → Tool-Call 循环（最多 5 轮）→ 生成回答

**安全设计：**
- 每个工具独立执行权限校验，不信任 LLM 参数
- user/db 不暴露给 LLM，无法伪造身份
- list_kb 仅返回有权限的知识库
- 循环上限 5 轮，防止 token 消耗失控
- 所有工具调用记录审计日志

详细设计见 [PRD v4.0](docs/RAG知识库管理系统_PRD_v4.0.docx) 和 [设计方案 v4.0](docs/RAG知识库管理系统_整体设计方案_v4.0.docx)

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
| POST | `/api/upload` | 上传文档（PDF 走 OCR 异步处理） |
| GET | `/api/upload/progress/{task_id}` | PDF 处理进度（按页更新） |
| GET | `/api/documents?kb_id=xxx` | 文档列表 |
| DELETE | `/api/documents/{filename}` | 删除文档（级联清理） |
| GET | `/api/documents/{filename}/chunks` | 查看分块 |
| PUT/DELETE | `/api/chunks/{chunk_id}` | 编辑/删除分块 |

### 问答 & 对话
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/query` | 语义问答 |
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
| GET/POST | `/api/config/models` | 模型配置 |
| GET/POST | `/api/config/prompts` | Prompt 模板 |
| GET | `/api/stats/dashboard` | 仪表盘统计 |
| GET | `/api/stats/quality` | 质量监控统计 |
| POST | `/api/eval/generate` | 生成评测集 |
| POST | `/api/eval/run/{dataset_id}` | 启动评测 |
| GET | `/api/eval/runs/{id}/results` | 评测结果详情 |

---

## 项目结构

```
knowledge-base/
├── app/
│   ├── main.py                     # FastAPI 入口
│   ├── api/                        # 14 个路由模块
│   │   ├── doc_routes.py           # 文档上传/删除（含 OCR 异步处理）
│   │   ├── kb_routes.py            # 知识库 CRUD
│   │   ├── query_routes.py         # 问答
│   │   ├── eval_routes.py          # 效果评测
│   │   └── ...
│   ├── core/
│   │   ├── ocr/                    # OCR 模块
│   │   │   ├── engine.py           # PaddleOCR 引擎（版面/文字/表格识别）
│   │   │   ├── postprocess.py      # 后处理 → Markdown
│   │   │   └── utils.py            # 工具函数
│   │   ├── loader.py               # 文档加载（PDF 统一走 OCR）
│   │   ├── splitter.py             # 文本分块（语义/固定/结构）
│   │   ├── vectorstore.py          # ChromaDB 向量存储 + 混合检索
│   │   ├── llm.py                  # LLM 调用 + 查询改写
│   │   ├── reranker.py             # 重排序
│   │   ├── progress.py             # 上传任务进度追踪
│   │   └── ...
│   ├── models/                     # ORM + Pydantic
│   └── static/                     # 前端 SPA（13 个页面模块）
├── config/                         # 模型/Prompt 配置
├── scripts/                        # init_db / migrate_db / ocr_cli
├── data/chroma_db/                 # 向量库持久化
└── README.md
```

---

## 数据库（14 张表）

| 表 | 用途 |
|---|---|
| `user` / `department` | 用户与部门 |
| `knowledge_base` | 知识库 |
| `document` | 文档元数据（SHA-256 去重） |
| `kb_department_access` / `kb_user_access` | 知识库授权 |
| `conversation` / `conversation_turn` | 多轮对话 |
| `qa_feedback` | 用户反馈 |
| `audit_log` | 审计日志 |
| `eval_dataset` / `eval_question` / `eval_run` / `eval_result` | 效果评测 |

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
- 前端 12 个页面、产品原型 + PRD + 设计方案
- 数据库层搭建（10 张核心表）
- 模型配置持久化 + Ollama 支持 + 知识库文档隔离

**Phase 2 — 文档管理完善**
- 文档分块查看/编辑、上传三步向导、Prompt 管理系统
- 语义分块 + 结构分析分块策略、Embedding 重试机制
- 问答预设问题、Markdown 渲染、上下文长度优化

**Phase 3 — 安全与架构**
- JWT 认证 + 知识库权限体系 + 审计日志 + 用户管理
- 架构重构：安全加固 + 前后端模块化 + CORS
- 混合检索（向量+BM25+RRF）+ 多轮对话 + 反馈 + 缓存
- 文档版本管理（同名文件替换确认）

**Phase 4 — 质量监控与统计**
- 质量监控页、统计 API、仪表盘数据接入
- 全面 Bug 修复 + 架构优化 + 代码清理

**Phase 5 — 检索增强**
- 查询改写 + qwen3-vl-rerank 重排
- 问答页知识库选择器 + 对话删除 + 级联删除

**Phase 6 — 效果评测系统**
- 评测集自动生成 + LLM-as-Judge 9 维度评分
- 评测 Prompt 管理、MySQL 兼容修复、多轮 Bug 修复
- 文档归档（PRD v3.0 + 设计方案 v3.0）

**Phase 7 — OCR 与异步处理**
- PaddleOCR PDF 解析（版面检测+文字识别+表格识别）
- 异步上传按页进度、级联删除修复、错误提示优化

**Phase 8 — Query 润色与多格式支持（2026-04-27）**
- Query 润色：LLM 拼写纠错 + 同义扩展 + 关键词提取，检索前自动优化查询
- 多格式支持：Excel（.xlsx/.xls）、CSV、PowerPoint（.pptx）文档解析
- Excel 分块优化：每条记录独立 ## 标题，heading 策略不合并，确保检索粒度精确
- BM25 索引按 kb_id 隔离，修复跨知识库检索泄露
- 缓存 key 改用原始问题，润色逻辑移至缓存未命中后
- 密码复杂度校验 + 修改密码功能
- 运维手册 v1.0

**Phase 9 — Agent 智能化（v4.0，Phase 1+2 已完成）**
- ✅ Agent / Function Calling：LLM 自主决策工具调用，Tool-Call 循环（最多5轮）
- ✅ 5 个工具：search_kb / list_kb / list_docs / get_doc_content / summarize_doc
- ✅ 权限安全：工具层权限代理 + 部门权限继承 + 缓存按用户隔离
- ✅ Agent 专用 Prompt：鼓励工具调用，完整呈现工具结果
- ✅ summarize_doc：读取全文调用 LLM 生成结构化摘要
- ✅ get_doc_content：支持 max_chars 参数，最大 30000 字符
- ⏳ MCP Server 拆分（长期目标）
- ⏳ 联网搜索补全
- ⏳ 多 Agent 协作

---

## 待办功能

### 产品功能

- [x] 润色 Query（拼写纠错、同义扩展、关键词提取）
- [x] 更多文档格式（Excel/PPT/CSV）
- [x] keywords 喂给 BM25 + Reranker URL 修复 + 缓存逻辑重构 + 缓存按用户隔离
- [x] Agent / Function Calling（LLM 自主决策调用工具）—— Phase 1+2 已完成，5 个工具
- [ ] 数据源同步（飞书/Confluence/Git 自动导入）
- [ ] API 开放 + Bot 发布（API Key / Widget / Webhook）
- [ ] 多 KB 路由 + 工作流编排
- [ ] 知识图谱增强（实体抽取 + 图谱检索）
- [ ] Prompt 在线调试 + A/B 测试

### 系统优化 & 安全加固

- [x] 用户名和角色显示移到右上角，点击头像出现下拉菜单（修改密码、退出登录）
- [x] 密码复杂度要求：字母+数字，最少 8 位
- [x] 运维手册（部署、扩缩容、故障排查、数据恢复流程）
- [ ] JWT 过期时间 + 刷新机制（access_token + refresh_token 双 token）
- [ ] 告警：OOM、磁盘满、LLM API 不可用时要有告警
- [ ] 缓存层：查询缓存接 Redis，支持多实例部署
- [ ] MySQL 定时备份脚本 + cron 配置
