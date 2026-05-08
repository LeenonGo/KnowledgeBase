"""数据模型定义 — 含输入校验"""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """问答请求"""
    question: str = Field(..., min_length=1, max_length=2000, description="用户问题")
    top_k: int = Field(default=10, ge=1, le=20, description="返回结果数")
    kb_id: str | None = None
    use_hybrid: bool = True
    use_reranker: bool = False
    use_rewrite: bool = False
    use_polish: bool = False
    use_agent: bool = False
    history: str | None = Field(default=None, max_length=10000, description="多轮对话上下文")
    conv_id: str | None = None


class QueryResponse(BaseModel):
    """问答响应"""
    question: str
    answer: str
    sources: list[str]


class UploadResponse(BaseModel):
    """上传响应"""
    filename: str
    chunks: int
    message: str


class DocumentInfo(BaseModel):
    """文档信息"""
    filename: str
    chunks: int
    size: str = "-"


class ModelConfig(BaseModel):
    """单个模型配置"""
    provider: str
    base_url: str
    api_key: str
    model: str
    max_tokens: int = 2048
    temperature: float = 0.7
    dimensions: int | None = None


class ModelsConfig(BaseModel):
    """完整模型配置"""
    llm: ModelConfig
    embedding: ModelConfig
    reranker: ModelConfig | None = None
