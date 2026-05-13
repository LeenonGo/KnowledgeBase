# RAG 知识库管理系统

基于 RAG 架构的企业级智能知识库管理与问答平台。15 分钟部署上线，支持多部门权限隔离、混合检索、多轮对话、效果评测。

## 核心能力

| 能力 | 说明 |
|------|------|
| 📄 多格式文档解析 | PDF(含OCR) / Word / Excel / CSV / PPT / TXT / Markdown |
| 🔍 混合检索 | 向量语义 + BM25 + RRF 融合 + qwen3-rerank 重排 |
| 🔐 部门权限隔离 | 部门级授权 + 三级角色（super_admin / kb_admin / user） |
| 🧠 Agent 模式 | Plan-and-Execute 多步推理、Self-RAG 自适应检索、14 个工具 |
| 💾 长期记忆层 | 用户记忆（偏好/背景/纠正）+ FAQ 高频问答自动沉淀 |
| 📈 效果评测 | LLM-as-Judge 9 维度自动评分 |
| 💬 多轮对话 | 上下文传递、Query 润色、查询改写、引用标注 [C1][C2] |

## 技术栈

FastAPI + MySQL + ChromaDB + OpenAI 兼容接口 + PaddleOCR + 纯前端 SPA + ECharts

## 快速开始

```bash
cd knowledge-base
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env  # 编辑 JWT_SECRET、数据库连接等

python scripts/init_db.py
python scripts/migrate_db.py

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问 `http://localhost:8000`，默认管理员：`admin` / `admin123`

## 功能页面

| 页面 | 功能 | 权限 |
|---|---|---|
| 仪表盘 | 统计卡片、7 天趋势、健康度评分 | 全员 |
| 知识库列表/详情 | CRUD、文档管理、分块查看、部门授权 | 全员/编辑需 admin |
| 文档上传 | 三步向导、分块策略、PDF OCR 异步+按页进度 | admin/kb_admin |
| 💬 智能问答 | RAG 模式：混合检索、引用标注、FAQ 预匹配 | 全员 |
| 🧠 Agent 工作台 | Plan-and-Execute、推理链可视化、图表生成 | 全员 |
| 💾 我的记忆 | 查看/删除用户记忆记录 | 全员 |
| 📝 FAQ 管理 | 审核/通过/拒绝/删除 FAQ | admin/kb_admin |
| 用户/部门/权限管理 | CRUD、树形结构 | super_admin |
| 审计日志 / 质量监控 / 效果评测 | 操作记录、差评率、自动评分 | super_admin |
| 系统配置 | LLM/Embedding/Reranker/Prompt/检索策略 | super_admin |

## Agent 工具（14 个）

| 工具 | 功能 |
|---|---|
| search_kb | 知识库语义检索（带相关度评分） |
| list_kb / list_docs / get_doc_content | 知识库/文档浏览 |
| summarize_doc / knowledge_compare | 文档摘要 / 知识对比 |
| web_search | 联网搜索 |
| chart_generator | 数据可视化（ECharts） |
| doc_stats | 知识库统计 |
| calculator / current_time | 数学计算 / 当前时间 |
| recall_memory / search_faq | 用户记忆 / FAQ 查询 |
| http_request | HTTP 请求调用外部 API（SSRF 防护） |

## 版本计划

### 🔥 v5.2 — Agent 智能化增强
- **代码执行沙箱**（code_executor）— Agent 能写 Python 做数据分析
- **人机协作确认节点** — 子任务执行完暂停等用户批准
- **HTTP 请求工具** — Agent 能调 REST API，连接外部系统

### 📋 v5.3 — 产品体验
- Prompt 调试工作台（可视化编辑 + 实时预览 + 版本管理）
- 结构化输出（JSON Schema / 表格 / 报告格式）
- 工具插件化注册（Tool Registry 热加载）

### 💡 v6.0 — 架构演进
- 多 Agent 协作 / 知识图谱 / 数据源同步 / API 开放 + Bot 发布

### 🛡️ 系统优化
- JWT 双 token / 告警机制 / Redis 缓存 / MySQL 定时备份

## 详细文档

- [API 接口文档](docs/API.md)
- [架构设计](docs/ARCHITECTURE.md)
