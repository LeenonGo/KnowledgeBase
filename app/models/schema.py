"""数据模型定义"""

from pydantic import BaseModel


class QueryRequest(BaseModel):
    """问答请求"""
    question: str
    top_k: int = 5


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
