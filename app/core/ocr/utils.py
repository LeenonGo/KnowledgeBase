"""OCR 工具函数"""

import re
import logging
import numpy as np
from PIL import Image

logger = logging.getLogger("kb.ocr")


def to_dict(obj) -> dict:
    """将 PaddleOCR 返回对象统一转为 dict。"""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "res"):
        return obj.res if isinstance(obj.res, dict) else to_dict(obj.res)
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    try:
        return dict(obj)
    except (TypeError, ValueError):
        return {"_raw": str(obj)}


def find_html(obj, depth=0) -> str:
    """递归搜索包含 <table> 的字符串字段。"""
    if depth > 8:
        return ""
    if isinstance(obj, str) and "<table" in obj.lower():
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            found = find_html(v, depth + 1)
            if found:
                return found
    if isinstance(obj, (list, tuple)):
        for v in obj:
            found = find_html(v, depth + 1)
            if found:
                return found
    return ""


def clean_table_html(html: str) -> str:
    """去掉 <html><body> 包装，只保留 <table>。"""
    if not html:
        return ""
    match = re.search(r'(<table[\s\S]*?</table>)', html, re.IGNORECASE)
    if match:
        return match.group(1)
    return html


def html_table_to_markdown(html: str) -> str:
    """HTML 表格 → Markdown 表格（用 lxml 解析，比正则更可靠）。"""
    if not html:
        return ""

    try:
        from lxml import etree
        tree = etree.HTML(html)
        rows = tree.xpath("//tr")
        if not rows:
            return html

        md_rows = []
        for row in rows:
            cells = row.xpath(".//td|.//th")
            cleaned = []
            for cell in cells:
                text = etree.tostring(cell, method="text", encoding="unicode").strip()
                text = text.replace("\n", " ").replace("|", "\\|")
                cleaned.append(text)
            if cleaned:
                md_rows.append("| " + " | ".join(cleaned) + " |")

        if not md_rows:
            return html

        ncols = md_rows[0].count("|") - 1
        separator = "| " + " | ".join(["---"] * max(ncols, 1)) + " |"
        md_rows.insert(1, separator)
        return "\n".join(md_rows)

    except ImportError:
        # fallback: 正则解析
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.IGNORECASE | re.DOTALL)
        if not rows:
            return html

        md_rows = []
        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.IGNORECASE | re.DOTALL)
            cleaned = []
            for cell in cells:
                text = re.sub(r'<[^>]+>', '', cell).strip()
                text = text.replace('\n', ' ').replace("|", "\\|")
                cleaned.append(text)
            if cleaned:
                md_rows.append("| " + " | ".join(cleaned) + " |")

        if not md_rows:
            return html

        ncols = md_rows[0].count("|") - 1
        separator = "| " + " | ".join(["---"] * max(ncols, 1)) + " |"
        md_rows.insert(1, separator)
        return "\n".join(md_rows)


def crop_by_poly(image: Image.Image, poly) -> Image.Image | None:
    """根据多边形坐标裁剪图片区域。"""
    try:
        pts = np.array(poly).reshape(-1, 2).astype(int)
        x_min, y_min = pts.min(axis=0)
        x_max, y_max = pts.max(axis=0)
        w, h = image.size
        x_min, y_min = max(0, x_min), max(0, y_min)
        x_max, y_max = min(w, x_max), min(h, y_max)
        if x_max <= x_min or y_max <= y_min:
            return None
        return image.crop((x_min, y_min, x_max, y_max))
    except Exception:
        return None


def sort_text_lines_by_y(texts: list[dict]) -> list[dict]:
    """将 OCR 文字行按 y 坐标升序排列（从上到下）。"""
    if not texts:
        return texts
    return sorted(texts, key=lambda t: (
        t.get("center_y", t.get("poly", [[0, 0]])[0][1] if t.get("poly") else 0)
    ))


def sort_regions_reading_order(regions: list[dict], page_width: int | None = None) -> list[dict]:
    """
    按阅读顺序排序区域：双栏左先右后，各栏内从上到下。

    算法：
    1. 计算每个区域的水平中心
    2. 用中位数分割分成左右栏
    3. 各栏内按 y 坐标排序
    4. 左栏在前，右栏在后
    """
    if len(regions) <= 1:
        return regions

    for r in regions:
        bbox = r.get("bbox", [0, 0, 0, 0])
        r["_cx"] = (bbox[0] + bbox[2]) / 2
        r["_cy"] = bbox[1]

    if page_width is None:
        page_width = max((r["bbox"][2] for r in regions), default=1000)

    mid_x = page_width / 2
    left_col = [r for r in regions if r["_cx"] < mid_x]
    right_col = [r for r in regions if r["_cx"] >= mid_x]

    if not left_col or not right_col:
        regions.sort(key=lambda r: r["_cy"])
        return regions

    if len(left_col) >= 2 and len(right_col) >= 2:
        left_col.sort(key=lambda r: r["_cy"])
        right_col.sort(key=lambda r: r["_cy"])
        return left_col + right_col

    regions.sort(key=lambda r: r["_cy"])
    return regions
