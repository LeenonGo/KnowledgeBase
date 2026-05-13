# 架构设计

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
│   │   ├── config_routes.py        # 系统配置
│   │   ├── stats_routes.py         # 统计 & 健康度
│   │   ├── eval_routes.py          # 效果评测
│   │   ├── trace_routes.py         # 全链路 Trace
│   │   └── deps.py                 # 认证 + 权限检查
│   ├── core/
│   │   ├── llm.py                  # LLM 调用 + Agent + Plan-and-Execute + Self-RAG
│   │   ├── tools.py                # 14 个 Agent 工具 + 工具注册表
│   │   ├── memory_service.py       # 记忆提取/检索/衰减 + FAQ 沉淀/匹配/生命周期
│   │   ├── vectorstore.py          # ChromaDB 向量存储 + 混合检索
│   │   ├── hybrid_search.py        # 混合检索编排
│   │   ├── splitter.py             # 文本分块（语义/固定/结构）
│   │   ├── reranker.py             # qwen3-rerank 重排序
│   │   ├── embedding.py            # Embedding 向量化
│   │   ├── loader.py               # 多格式文档加载
│   │   ├── web_search.py           # 联网搜索
│   │   ├── eval_generator.py       # 评测集自动生成
│   │   ├── eval_runner.py          # 评测运行器
│   │   ├── trace.py                # 全链路 Trace
│   │   ├── auth.py                 # JWT 认证
│   │   ├── config.py               # 配置加载
│   │   ├── database.py             # 数据库连接
│   │   ├── cache/                  # 缓存层（内存/Redis）
│   │   └── ocr/                    # PaddleOCR 模块
│   ├── models/
│   │   ├── models.py               # SQLAlchemy ORM（19 张表）
│   │   └── schema.py               # Pydantic 请求/响应模型
│   └── static/                     # 前端 SPA
│       ├── index.html              # 主页面 + 路由
│       ├── style.css               # 全局样式
│       └── js/
│           ├── router.js           # Hash 路由
│           ├── api.js              # API 封装
│           ├── components/ui.js    # 通用组件
│           └── pages/              # 16 个页面模块
├── config/
│   ├── models.json                 # LLM/Embedding/Reranker 配置
│   └── prompts.json                # Prompt 模板
├── scripts/
│   ├── init_db.py                  # 数据库初始化
│   ├── migrate_db.py               # 增量迁移
│   └── ocr_cli.py                  # OCR 命令行工具
├── data/chroma_db/                 # 向量库持久化
└── docs/                           # 文档
```

## 数据库（19 张表）

| 表 | 用途 |
|---|---|
| `user` / `department` | 用户与部门 |
| `knowledge_base` | 知识库 |
| `document` | 文档元数据（SHA-256 去重） |
| `kb_department_access` / `kb_user_access` | 知识库授权 |
| `conversation` / `conversation_turn` | 多轮对话（conv_type 区分 RAG/Agent） |
| `user_memory` | 用户长期记忆 |
| `faq` / `faq_tag` / `faq_candidate` | FAQ 沉淀 + 候选统计 |
| `qa_feedback` | 用户反馈 |
| `audit_log` | 审计日志 |
| `eval_dataset` / `eval_question` / `eval_run` / `eval_result` | 效果评测 |
| `trace` / `trace_span` | 全链路 Trace |

## 核心流程

### RAG 问答

```
用户提问 → 权限校验 → 查询改写 → 查缓存 → FAQ预匹配
  → Query润色 → Embedding → 向量+BM25混合检索 → RRF融合 → rerank重排
  → 注入用户记忆 → LLM生成(引用标注[C1][C2]) → 返回
```

### Agent 问答

```
用户提问 → 注入用户记忆 → Planning(拆子任务)
  → 每个子任务: ReAct循环 Thought→Tool→Observe (最多7轮)
  → Self-RAG(检索/相关度/事实校验三重反思)
  → Synthesize(综合生成) → 异步提取记忆+记录FAQ候选
```

## Agent 工具列表

详见 README.md。
