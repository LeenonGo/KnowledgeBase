"""
PaddleOCR PDF 解析模块

用法：
    from app.core.ocr import OCREngine, build_clean_output, build_markdown

    engine = OCREngine(device="cpu")
    raw = engine.analyze_pdf("input.pdf")
    clean = build_clean_output(raw)
    md = build_markdown(clean)
"""

from app.core.ocr.engine import OCREngine
from app.core.ocr.postprocess import build_clean_output, build_markdown

__all__ = ["OCREngine", "build_clean_output", "build_markdown"]
