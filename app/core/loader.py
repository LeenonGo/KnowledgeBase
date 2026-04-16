"""文档加载器 — 支持 TXT、Word、PDF、Markdown"""

from pathlib import Path


def load_document(file_path: str) -> str:
    """根据文件扩展名选择加载方式，返回纯文本"""
    path = Path(file_path)
    ext = path.suffix.lower()

    loaders = {
        ".txt": _load_txt,
        ".md": _load_txt,
        ".pdf": _load_pdf,
        ".docx": _load_docx,
    }

    loader = loaders.get(ext)
    if loader is None:
        raise ValueError(f"不支持的文件格式: {ext}")

    return loader(path)


def _load_txt(path: Path) -> str:
    """加载 TXT / Markdown"""
    return path.read_text(encoding="utf-8")


def _load_pdf(path: Path) -> str:
    """加载 PDF"""
    import fitz  # PyMuPDF

    doc = fitz.open(str(path))
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text


def _load_docx(path: Path) -> str:
    """加载 Word 文档"""
    from docx import Document

    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
