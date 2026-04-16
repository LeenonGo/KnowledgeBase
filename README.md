# 知识库问答平台 (Knowledge Base)

基于 RAG 架构的智能知识库问答系统。

## 技术栈

- **后端**: FastAPI
- **向量数据库**: Chroma
- **LLM / Embedding**: OpenAI 兼容接口，JSON 配置

## 快速开始

### 1. 安装依赖

```bash
cd knowledge-base
pip install -r requirements.txt
```

### 2. 配置模型

编辑 `config/models.json`，填入你的 API Key 和模型信息。

### 3. 启动服务

```bash
cd knowledge-base
python -m app.main
```

服务默认运行在 `http://localhost:8000`，API 文档：`http://localhost:8000/docs`

## API

### 上传文档

```
POST /api/upload
Content-Type: multipart/form-data

file: <文件>
```

支持格式：TXT、Markdown、PDF、Word (docx)

### 提问

```
POST /api/query
Content-Type: application/json

{
  "question": "你的问题",
  "top_k": 5
}
```

## 版本路线

- [x] Phase 1: MVP — 核心问答验证
- [ ] Phase 2: 基础版 — 知识库管理 + 权限
- [ ] Phase 3: 系统配置 + 日志
- [ ] Phase 4: Agent — Function Calling
