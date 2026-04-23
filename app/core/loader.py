"""文档加载器 — 支持 TXT、Word、PDF、Markdown"""

import logging
from pathlib import Path

logger = logging.getLogger("kb.loader")


def load_document(file_path: str, progress_callback=None) -> tuple[str, list[str]]:
    """
    根据文件扩展名选择加载方式，返回 (纯文本, 警告列表)。
    """
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

    if ext == ".pdf":
        return loader(path, progress_callback=progress_callback)
    return loader(path)


def _load_txt(path: Path) -> tuple[str, list[str]]:
    """加载 TXT / Markdown"""
    return path.read_text(encoding="utf-8"), []


def _load_pdf(path: Path, progress_callback=None) -> tuple[str, list[str]]:
    """加载 PDF：统一走 OCR 解析"""
    warnings = []
    logger.info("OCR 解析 PDF: %s", path.name)

    try:
        from app.core.ocr import OCREngine, build_clean_output, build_markdown

        engine = OCREngine(device="cpu")
        raw = engine.analyze_pdf(str(path), progress_callback=progress_callback)

        # 收集引擎处理中的错误
        for page in raw.get("pages", []):
            for region in page.get("regions", []):
                if region.get("error"):
                    label = region.get("type", "unknown")
                    warnings.append(f"区域 [{label}] 处理失败: {region['error']}")

        clean = build_clean_output(raw)
        md = build_markdown(clean)

        if md.strip():
            logger.info("OCR 完成，提取 %d 字符", len(md.strip()))
            return md.strip(), warnings
    except ValueError:
        # 预检失败（模型/依赖缺失）— 直接向上抛，不 fallback
        raise
    except Exception as e:
        msg = f"OCR 处理失败: {e}"
        logger.warning(msg)
        warnings.append(msg)

    # OCR 处理异常（非预检问题），回退 PyMuPDF
    import fitz
    doc = fitz.open(str(path))
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    warnings.append("已回退到基础文本提取（PyMuPDF），内容可能不完整")
    return text.strip(), warnings


def _load_docx(path: Path) -> tuple[str, list[str]]:
    """加载 Word 文档"""
    from docx import Document

    doc = Document(str(path))
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return text, []
