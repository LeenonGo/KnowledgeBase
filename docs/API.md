# API 接口文档

## 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/login` | 登录（username + password → token） |
| GET | `/api/me` | 当前用户信息 |

## 知识库 & 文档

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/knowledge-bases` | 知识库列表/创建 |
| PUT/DELETE | `/api/knowledge-bases/{id}` | 更新/删除知识库 |
| POST | `/api/upload` | 上传文档（支持批量） |
| GET | `/api/upload/progress/{task_id}` | PDF 处理进度 |
| GET | `/api/documents?kb_id=xxx` | 文档列表 |
| DELETE | `/api/documents/{filename}` | 删除文档 |
| GET | `/api/documents/{filename}/chunks` | 查看分块 |
| PUT/DELETE | `/api/chunks/{chunk_id}` | 编辑/删除分块 |

## 问答 & 对话

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/query` | RAG 问答 |
| POST | `/api/query/stream` | RAG 流式问答（SSE） |
| POST | `/api/query/agent/stream` | Agent 流式问答（SSE，含 Plan-and-Execute） |
| GET/POST | `/api/conversations` | 对话列表/创建 |
| GET/POST | `/api/conversations/{id}/turns` | 对话轮次 |
| PUT | `/api/conversations/{id}/pin` | 置顶/取消置顶 |
| PUT | `/api/conversations/{id}/tags` | 更新标签 |
| GET | `/api/conversations/{id}/export` | 导出 Markdown |
| POST/GET | `/api/feedback` | 提交/查看反馈 |

## 用户记忆 & FAQ

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/memory` | 获取用户记忆列表 + 统计 |
| DELETE | `/api/memory/{id}` | 删除单条记忆 |
| POST | `/api/memory/decay` | 手动执行记忆衰减（admin） |
| GET | `/api/faq` | FAQ 列表（支持 status/kb_id/page 筛选） |
| GET | `/api/faq/stats` | FAQ 统计 |
| POST | `/api/faq/{id}/approve` | 审核通过 FAQ |
| POST | `/api/faq/{id}/reject` | 拒绝 FAQ |
| DELETE | `/api/faq/{id}` | 删除 FAQ |
| POST | `/api/faq/decay` | 手动执行 FAQ 衰减（admin） |

## 用户 & 部门 & 授权

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/users` | 用户列表/创建 |
| PUT/DELETE | `/api/users/{id}` | 更新/禁用用户 |
| GET/POST/DELETE | `/api/departments` | 部门 CRUD |
| GET/POST/DELETE | `/api/kb-access` | 知识库部门授权 |

## 配置 & 统计 & 评测

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/config/models` | 模型配置（LLM/Embedding/Reranker） |
| GET/POST | `/api/config/prompts` | Prompt 模板管理 |
| GET | `/api/stats/dashboard` | 仪表盘统计 |
| GET | `/api/stats/quality` | 质量监控统计 |
| GET | `/api/stats/kb-health` | 知识库健康度 |
| GET | `/api/cache/stats` | 查询缓存统计 |
| POST | `/api/cache/clear` | 清空查询缓存 |
| POST | `/api/eval/generate` | 生成评测集 |
| POST | `/api/eval/run/{dataset_id}` | 启动评测 |
| GET | `/api/eval/runs/{run_id}` | 评测结果 |
| GET | `/api/traces` | 全链路 Trace 列表 |
| GET | `/api/traces/{id}` | Trace 详情 |

## 审计日志

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/audit` | 审计日志列表（筛选/分页） |
