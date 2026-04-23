"""OCR 后处理：结构化结果 → 精简 JSON + Markdown"""

import logging

from app.core.ocr.utils import (
    find_html,
    clean_table_html,
    html_table_to_markdown,
    sort_text_lines_by_y,
    sort_regions_reading_order,
)

logger = logging.getLogger("kb.ocr.postprocess")


def build_clean_output(raw_result: dict) -> dict:
    """
    将原始分析结果转换为精简的结构化输出。

    - 表格 HTML 正确提取
    - 区域按阅读顺序排序（双栏自适应）
    - 区域内文字行按 y 升序排列
    - 去除膨胀的中间数据
    """
    clean_pages = []

    for page in raw_result.get("pages", []):
        regions = page.get("regions", [])
        page_width = max((r["bbox"][2] for r in regions if r.get("bbox")), default=1000)
        regions = sort_regions_reading_order(regions, page_width)

        sections = []
        full_text_parts = []

        for region in regions:
            rtype = region.get("type", "unknown")
            raw_texts = region.get("texts", [])
            sorted_texts = sort_text_lines_by_y(raw_texts) if raw_texts else []

            if rtype in ("table", "table_title"):
                html = region.get("html", "")
                if not html:
                    raw = region.get("raw", {})
                    html = find_html(raw)
                html = clean_table_html(html)

                if html:
                    md = html_table_to_markdown(html)
                    sections.append({"type": "table", "html": html, "markdown": md})
                    full_text_parts.append("[表格]\n" + md)
                elif region.get("cell_texts"):
                    txt = " | ".join(region["cell_texts"])
                    sections.append({"type": "table", "content": txt})
                    full_text_parts.append("[表格] " + txt)

            elif rtype in ("formula", "equation"):
                latex = region.get("latex", "")
                if latex:
                    sections.append({"type": "formula", "latex": latex})
                    full_text_parts.append(f"$${latex}$$")

            elif rtype in ("figure", "image"):
                if sorted_texts:
                    img_text = " / ".join(t["text"] for t in sorted_texts if t.get("text"))
                    sections.append({"type": "figure", "content": img_text})
                    full_text_parts.append(f"[图片] {img_text}")

            elif rtype in ("figure_title", "figure_caption"):
                if sorted_texts:
                    caption = " ".join(t["text"] for t in sorted_texts)
                    sections.append({"type": "caption", "content": caption})
                    full_text_parts.append(caption)
                else:
                    ft = region.get("full_text", "").strip()
                    if ft:
                        sections.append({"type": "caption", "content": ft})
                        full_text_parts.append(ft)

            elif rtype == "number":
                continue

            else:
                if sorted_texts:
                    content = "\n".join(t["text"] for t in sorted_texts)
                else:
                    content = region.get("full_text", "").strip()
                if content:
                    sections.append({"type": "text", "content": content})
                    full_text_parts.append(content)

        clean_pages.append({
            "page": page.get("page_index", 0) + 1,
            "sections": sections,
            "full_text": "\n\n".join(full_text_parts),
        })

    return {
        "file": raw_result.get("file", ""),
        "total_pages": raw_result.get("total_pages", 0),
        "elapsed_ms": raw_result.get("elapsed_ms", 0),
        "pages": clean_pages,
    }


def build_markdown(clean_result: dict) -> str:
    """将精简结果转为完整 Markdown 文档（适合知识库入库）。"""
    lines = [f"# {clean_result['file']}", ""]

    for page in clean_result.get("pages", []):
        if clean_result["total_pages"] > 1:
            lines.append(f"---\n## 第 {page['page']} 页\n")

        for section in page.get("sections", []):
            stype = section.get("type", "")

            if stype == "text":
                lines.append(section["content"])
                lines.append("")

            elif stype == "table":
                md = section.get("markdown", "")
                if md:
                    lines.append(md)
                    lines.append("")
                elif section.get("html"):
                    lines.append(
                        f"<details><summary>表格(HTML)</summary>\n\n"
                        f"{section['html']}\n\n</details>"
                    )
                    lines.append("")

            elif stype == "formula":
                lines.append(f"$${section['latex']}$$")
                lines.append("")

            elif stype == "caption":
                lines.append(f"*{section['content']}*")
                lines.append("")

            elif stype == "figure":
                lines.append(f"> [图片内容: {section.get('content', '')}]")
                lines.append("")

    return "\n".join(lines)
