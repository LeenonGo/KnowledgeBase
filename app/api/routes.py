"""API 路由"""

import os
import shutil
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException

from app.core.splitter import load_and_split
from app.core.vectorstore import add_documents, query, list_documents, delete_document
from app.core.llm import generate_answer
from app.models.schema import QueryRequest, QueryResponse, UploadResponse, DocumentInfo

router = APIRouter(prefix="/api")

UPLOAD_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"


@router.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    上传文档 → 解析 → 分块 → 入向量库
    """
    # 保存文件
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        # 加载并分块
        chunks = load_and_split(str(file_path))

        if not chunks:
            raise HTTPException(status_code=400, detail="文档内容为空或无法解析")

        # 写入向量库
        count = add_documents(chunks, file.filename)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return UploadResponse(
        filename=file.filename,
        chunks=count,
        message=f"文档已处理，共 {count} 个文本块",
    )


@router.get("/documents", response_model=list[DocumentInfo])
async def get_documents():
    """获取已上传文档列表"""
    return list_documents()


@router.delete("/documents/{filename:path}")
async def remove_document(filename: str):
    """删除文档及其向量数据"""
    count = delete_document(filename)
    if count == 0:
        raise HTTPException(status_code=404, detail="文档不存在")
    # 删除源文件
    file_path = UPLOAD_DIR / filename
    if file_path.exists():
        file_path.unlink()
    return {"message": f"已删除 {filename}（{count} 个文本块）"}


@router.post("/query", response_model=QueryResponse)
async def query_knowledge_base(req: QueryRequest):
    """
    用户提问 → 语义检索 → LLM 生成回答
    """
    # 检索相关文档
    docs = query(req.question, top_k=req.top_k)

    if not docs:
        return QueryResponse(
            question=req.question,
            answer="知识库中暂无相关内容，请先上传文档。",
            sources=[],
        )

    # 拼接上下文
    context = "\n\n".join(f"[来源: {d['source']}]\n{d['text']}" for d in docs)
    sources = list(set(d["source"] for d in docs))

    # LLM 生成回答
    answer = generate_answer(req.question, context)

    return QueryResponse(
        question=req.question,
        answer=answer,
        sources=sources,
    )
