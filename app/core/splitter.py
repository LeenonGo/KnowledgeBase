"""文本分块"""

from app.core.loader import load_document


def split_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[str]:
    """
    按字符数分块，支持重叠。
    
    Args:
        text: 原始文本
        chunk_size: 每块最大字符数
        chunk_overlap: 块之间重叠字符数
    Returns:
        分块后的文本列表
    """
    if not text.strip():
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - chunk_overlap

    return chunks


def load_and_split(file_path: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """加载文档并分块"""
    text = load_document(file_path)
    return split_text(text, chunk_size, chunk_overlap)
