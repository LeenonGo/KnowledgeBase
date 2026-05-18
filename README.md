# RAG 知识库管理系统

基于 RAG 架构的企业级智能知识库管理与问答平台。15 分钟部署上线，支持多部门权限隔离、混合检索、多轮对话、效果评测。

## 核心能力

| 能力 | 说明 |
|------|------|
| 📄 多格式文档解析 | PDF(含OCR) / Word / Excel / CSV / PPT / TXT / Markdown |
| 🔍 混合检索 | 向量语义 + BM25 + RRF 融合 + qwen3-rerank 重排 + FAQ 预匹配 |
| 🔐 部门权限隔离 | 部门级授权 + 三级角色（super_admin / kb_admin / user） |
| 🧠 Agent 模式 | Plan-and-Execute 多步推理 + Self-RAG 自适应检索 + 16 个工具 |
| ⏸️ 人机协作 | 执行计划确认 / 逐步审批 / 用户可控 Agent 行为 |
| 🌐 外部连接 | HTTP 请求工具（SSRF 防护）+ 联网搜索，Agent 可调任意 REST API |
| 💾 长期记忆层 | 用户记忆（偏好/背景/纠正）+ FAQ 高频问答自动沉淀 + 衰减淘汰 |
| 📈 效果评测 | LLM-as-Judge 9 维度自动评分 |
| 💬 多轮对话 | 上下文传递、Query 润色、查询改写、引用标注 [C1][C2] |
| 📊 数据可视化 | Agent 可生成 ECharts 图表（柱状图/饼图/折线图） |

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
| 📊 SQL 分析 | 自然语言查电商数据、SQL可视化、图表分析 | 全员 |
| 💾 我的记忆 | 查看/删除用户记忆记录 | 全员 |
| 📝 FAQ 管理 | 审核/通过/拒绝/删除 FAQ | admin/kb_admin |
| 用户/部门/权限管理 | CRUD、树形结构 | super_admin |
| 审计日志 / 质量监控 / 效果评测 | 操作记录、差评率、自动评分 | super_admin |
| 系统配置 | LLM/Embedding/Reranker/Prompt/检索策略 | super_admin |

## Agent 工具（17 个）

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
| sql_query | 自然语言查询电商数据库 |
| sql_schema | 查看电商数据库表结构 |
| search_kg | 知识图谱检索（实体关联 + 多跳推理） |

## 版本计划

### ✅ v5.2 — Agent 智能化增强（已完成）
- **HTTP 请求工具** — Agent 能调 REST API，SSRF 防护 ✅
- **人机协作确认节点** — 执行计划确认 + 逐步审批 ✅
- **代码执行沙箱**（code_executor）— Agent 能写 Python 做数据分析（待做）

### ✅ v5.3 — SQL 分析助手（已完成）
- **Text-to-SQL** — 自然语言→SQL→结果→分析总结，SSE 流式返回 ✅
- **SQL 可视化** — 展示生成的 SQL，支持编辑后重新执行 ✅
- **电商 Demo 数据库** — 9 张表、2 万订单，Faker 模拟数据 ✅
- **Agent 工具集成** — sql_query / sql_schema 两个工具 ✅
- **Prompt 配置化** — 拆分模块化管理（core/agent/sql）✅
- **多轮追问** — 基于上下文的连续数据探索 ✅
- **图表生成** — 柱状图/折线图/饼图自动推荐 ✅

### ✅ v5.4 — 知识图谱增强（已完成）
- **LLM 实体抽取** — 自动从文档中抽取实体和关系（LLM-driven KG Construction）✅
- **知识图谱存储** — kg_entity / kg_relation 两张表，实体去重 + 向量化 ✅
- **图谱检索** — 精确匹配 + 向量扩展 + 关系扩展（1-2跳）✅
- **GraphRAG 融合** — 图谱检索 + 向量检索上下文拼接 ✅
- **Agent 工具** — search_kg 工具（13→14 个）✅
- **D3 可视化** — 力导向图 + 搜索/筛选/导出 + 节点详情 ✅
- **图谱构建** — 从已有文档一键构建图谱 ✅
- **技术方案** — [文档](docs/features/kg-enhancement/知识图谱增强_技术方案_v1.0.docx) ✅

### ✅ 数据源同步（Git / 网页 URL）
- Git 仓库同步 — 浅克隆 + SHA-256 diff + 增量更新 ✅
- 网页 URL 同步 — 单页/递归爬取 + 正文提取 ✅
- 定时同步（cron 表达式） ✅
- 连接测试 ✅
- 前端管理界面 — 新增/编辑/删除/同步状态轮询 ✅
- 快速失败机制 — API 额度耗尽时自动中止 ✅
- 技术方案 — [文档](docs/features/data-source-sync/数据源同步_技术方案_v1.0.docx) ✅



### ✅ v5.5a — 结构化输出
- 三种输出格式：表格 / JSON / 报告 ✅
- 表格格式：默认，含 highlights + 图表 ✅
- JSON 格式：结构化数据 + 字段 Schema + 一键复制 ✅
- 报告格式：标题 / 摘要 / 分节分析 / 结论 ✅
- 前端格式选择器 ✅

### ✅ v5.5b — SQL 查询审计日志
- 自动记录每次 NL→SQL 查询 ✅
- 审计日志页面：筛选 / 分页 / 详情查看 ✅
- 普通用户查看自己的，管理员查看全部 ✅

### 📋 v5.5c — 待做
- 查询模板（预置常见分析场景）
- 表级权限控制
- 工具插件化注册（Tool Registry 热加载）

### 💡 v6.0 — 架构演进
- 多 Agent 协作 / API 开放 + Bot 发布

### 🛡️ 系统优化
- JWT 双 token / 告警机制 / Redis 缓存 / MySQL 定时备份

## 详细文档

- [文档目录](docs/文档目录.docx)
- [API 接口文档](docs/api/API文档.docx)
- [架构设计](docs/design/架构概览.docx)
- [SQL 分析助手技术方案](docs/features/sql-agent/SQL分析助手_技术方案_v1.0.docx)
- [知识图谱增强技术方案](docs/features/kg-enhancement/知识图谱增强_技术方案_v1.0.docx)
