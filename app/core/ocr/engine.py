"""PaddleOCR PDF 解析引擎 — 模块化版"""

import logging
import os
import time
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from PIL import Image

from app.core.ocr.utils import (
    to_dict,
    find_html,
    clean_table_html,
    crop_by_poly,
    sort_regions_reading_order,
)

logger = logging.getLogger("kb.ocr.engine")


class OCREngine:
    """
    手动串联 PP-StructureV3 的各个子模型，支持懒加载。

    用法：
        engine = OCREngine(device="cpu")
        raw = engine.analyze_pdf("input.pdf")
    """

    def __init__(self, lang: str = "ch", device: str = "cpu"):
        self.lang = lang
        self.device = device

        self._layout_detector = None
        self._text_detector = None
        self._text_recognizer = None
        self._table_recognizer = None
        self._formula_recognizer = None
        self._loaded_modules: set[str] = set()

    # ================================================================
    # 子模型加载（懒加载）
    # ================================================================

    def _img_for_paddle(self, image: Image.Image) -> np.ndarray:
        return np.array(image)

    def _ensure_loaded(self, module: str, loader) -> None:
        """统一的懒加载入口，避免重复判断。"""
        if module not in self._loaded_modules:
            logger.info("加载 %s 模型...", module)
            loader()
            self._loaded_modules.add(module)
            logger.info("%s 模型就绪", module)

    def _load_layout_detector(self):
        from paddleocr import LayoutDetection
        self._layout_detector = LayoutDetection(device=self.device)

    def _load_text_detector(self):
        from paddleocr import TextDetection
        self._text_detector = TextDetection(device=self.device)

    def _load_text_recognizer(self):
        from paddleocr import TextRecognition
        self._text_recognizer = TextRecognition(device=self.device)

    def _load_table_recognizer(self):
        from paddleocr import TableRecognitionPipelineV2
        self._table_recognizer = TableRecognitionPipelineV2(device=self.device)

    def _load_formula_recognizer(self):
        from paddleocr import FormulaRecognition
        self._formula_recognizer = FormulaRecognition(device=self.device)

    # ================================================================
    # 预检：验证模型和依赖是否可用
    # ================================================================

    def preflight_check(self) -> None:
        """
        预检所有模型是否可加载。失败则抛出 ValueError，包含具体缺失的模型名。
        """
        import importlib
        errors = []

        # 检查 PaddlePaddle 是否可用
        try:
            import paddle
        except ImportError:
            errors.append("PaddlePaddle 未安装")

        # 检查 paddleocr 是否可用
        try:
            import paddleocr
        except ImportError:
            errors.append("paddleocr 未安装")

        if errors:
            raise ValueError("OCR 模型配置有误，缺少依赖：" + "、".join(errors))

        # 逐个尝试加载核心模型
        model_checks = [
            ("版面检测", "LayoutDetection"),
            ("文字检测", "TextDetection"),
            ("文字识别", "TextRecognition"),
        ]
        for label, cls_name in model_checks:
            try:
                cls = getattr(importlib.import_module("paddleocr"), cls_name)
                cls(device=self.device)
            except Exception as e:
                err_short = str(e).split("\n")[0][:150]
                errors.append(f"{label}模型({cls_name})加载失败: {err_short}")

        if errors:
            raise ValueError("OCR 模型配置有误：" + "；".join(errors))

    # ================================================================
    # PDF → 图片
    # ================================================================

    def pdf_page_count(self, pdf_path: str) -> int:
        """快速获取 PDF 页数（不渲染）"""
        try:
            doc = fitz.open(pdf_path)
            count = len(doc)
            doc.close()
            return count
        except Exception as e:
            raise ValueError(f"无法打开 PDF 文件: {pdf_path}") from e

    def pdf_to_images(self, pdf_path: str, dpi: int = 200) -> list[Image.Image]:
        """渲染 PDF 为图片。DPI 建议 200（表格/中文更清晰）。"""
        logger.info("渲染 PDF: %s (DPI=%d)", pdf_path, dpi)
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            raise ValueError(f"无法打开 PDF 文件: {pdf_path}") from e

        images = []
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
        doc.close()
        logger.info("渲染完成: %d 页", len(images))
        return images

    # ================================================================
    # 版面检测
    # ================================================================

    def detect_layout(self, image: Image.Image) -> list[dict]:
        self._ensure_loaded("layout", self._load_layout_detector)
        img_array = np.array(image)
        raw_results = self._layout_detector.predict(img_array)
        regions = []

        for item in raw_results:
            item_dict = to_dict(item)
            boxes = item_dict.get("boxes", [])
            if not boxes:
                for k, v in item_dict.items():
                    if isinstance(v, list) and len(v) > 0:
                        first = v[0]
                        if isinstance(first, dict) and any(
                            kk in first for kk in ("label", "coordinate", "bbox", "type")
                        ):
                            boxes = v
                            break
            if not boxes and any(k in item_dict for k in ("label", "coordinate", "bbox")):
                boxes = [item_dict]
            regions.extend(boxes)

        return regions

    # ================================================================
    # 文字区域 OCR
    # ================================================================

    def ocr_region(self, image: Image.Image, bbox: list) -> dict:
        x1, y1, x2, y2 = [int(c) for c in bbox]
        cropped = image.crop((x1, y1, x2, y2))

        self._ensure_loaded("text_det", self._load_text_detector)
        self._ensure_loaded("text_rec", self._load_text_recognizer)

        det_results = self._text_detector.predict(self._img_for_paddle(cropped))
        texts = []

        for det in det_results:
            det_dict = to_dict(det)
            polys = det_dict.get("dt_polys", [])
            for poly in polys:
                line_img = crop_by_poly(cropped, poly)
                if line_img is None:
                    continue
                rec_results = self._text_recognizer.predict(self._img_for_paddle(line_img))
                for rec in rec_results:
                    rec_dict = to_dict(rec)
                    text = rec_dict.get("rec_text", rec_dict.get("text", ""))
                    score = rec_dict.get("rec_score", 0.0)
                    if text:
                        pts = np.array(poly).reshape(-1, 2)
                        abs_pts = pts + [x1, y1]
                        center_y = float(abs_pts[:, 1].mean())
                        center_x = float(abs_pts[:, 0].mean())
                        texts.append({
                            "text": text,
                            "confidence": round(float(score), 4),
                            "center_x": center_x,
                            "center_y": center_y,
                        })

        texts.sort(key=lambda t: (t["center_y"], t["center_x"]))

        return {
            "bbox": [x1, y1, x2, y2],
            "texts": texts,
            "full_text": "\n".join(t["text"] for t in texts),
        }

    # ================================================================
    # 表格识别
    # ================================================================

    def recognize_table(self, image: Image.Image, bbox: list) -> dict:
        self._ensure_loaded("table", self._load_table_recognizer)

        x1, y1, x2, y2 = [int(c) for c in bbox]
        cropped = image.crop((x1, y1, x2, y2))
        img_array = self._img_for_paddle(cropped)

        results = self._table_recognizer.predict(img_array)
        result = to_dict(next(iter(results)))

        # 从深层嵌套中提取 HTML
        html = result.get("html", "") or result.get("structure", "")

        if not html:
            table_res_list = result.get("table_res_list", [])
            if table_res_list:
                first_table = table_res_list[0] if isinstance(table_res_list[0], dict) else to_dict(table_res_list[0])
                html = first_table.get("pred_html", "")

        if not html:
            html = find_html(result)

        html = clean_table_html(html)

        cell_texts = []
        if not html:
            ocr_res = result.get("table_ocr_pred", result.get("overall_ocr_res", {}))
            if isinstance(ocr_res, dict):
                rec_texts = ocr_res.get("rec_texts", [])
                if rec_texts:
                    cell_texts = list(rec_texts)

        return {
            "bbox": [x1, y1, x2, y2],
            "html": html,
            "cell_texts": cell_texts,
        }

    # ================================================================
    # 公式识别
    # ================================================================

    def recognize_formula(self, image: Image.Image, bbox: list) -> dict:
        self._ensure_loaded("formula", self._load_formula_recognizer)
        x1, y1, x2, y2 = [int(c) for c in bbox]
        cropped = image.crop((x1, y1, x2, y2))

        results = self._formula_recognizer.predict(self._img_for_paddle(cropped))
        result = to_dict(next(iter(results)))

        return {
            "bbox": [x1, y1, x2, y2],
            "latex": result.get("latex", result.get("text", "")),
            "confidence": result.get("score", 0.0),
        }

    # ================================================================
    # 主流程
    # ================================================================

    def analyze_pdf(
        self,
        pdf_path: str,
        dpi: int = 200,
        enable_ocr: bool = True,
        enable_table: bool = True,
        enable_formula: bool = False,
        layout_confidence: float = 0.5,
        skip_labels: list[str] | None = None,
        progress_callback=None,
    ) -> dict:
        """
        分析 PDF 文件，返回结构化结果。

        Args:
            pdf_path: PDF 文件路径
            dpi: 渲染分辨率
            enable_ocr: 是否启用文字 OCR
            enable_table: 是否启用表格识别
            enable_formula: 是否启用公式识别
            layout_confidence: 版面检测置信度阈值
            skip_labels: 跳过的区域类型列表
            progress_callback: 进度回调 callback(current_page, total_pages)
        """
        skip_labels = skip_labels or []
        t0 = time.time()

        # 预检模型可用性
        self.preflight_check()

        images = self.pdf_to_images(pdf_path, dpi=dpi)
        doc = fitz.open(pdf_path)
        all_pages = []

        for page_idx, img in enumerate(images):
            page_t0 = time.time()
            page_width = img.width
            logger.info("=== 第 %d/%d 页 ===", page_idx + 1, len(images))

            regions = self.detect_layout(img)
            logger.info("  版面检测: %d 个区域", len(regions))

            filtered = []
            for r in regions:
                label = r.get("label", "unknown")
                score = r.get("score", r.get("confidence", 0))
                if label in skip_labels:
                    continue
                if score < layout_confidence:
                    continue
                filtered.append(r)

            logger.info("  过滤后: %d 个区域", len(filtered))
            filtered = sort_regions_reading_order(filtered, page_width)

            page_regions = []
            for r_idx, region in enumerate(filtered):
                label = region.get("label", "unknown")
                bbox = region.get("coordinate", region.get("bbox", []))

                region_result = {"type": label, "bbox": bbox}

                try:
                    if label in ("text", "title", "header", "footer",
                                 "reference", "abstract") and enable_ocr:
                        region_result.update(self.ocr_region(img, bbox))

                    elif label in ("table", "table_title") and enable_table:
                        region_result.update(self.recognize_table(img, bbox))

                    elif label in ("formula", "equation") and enable_formula:
                        region_result.update(self.recognize_formula(img, bbox))

                    elif label in ("figure", "image"):
                        if enable_ocr:
                            region_result.update(self.ocr_region(img, bbox))
                        region_result["content"] = "[图片区域]"

                    elif label in ("figure_title", "figure_caption"):
                        if enable_ocr:
                            region_result.update(self.ocr_region(img, bbox))

                    else:
                        if enable_ocr:
                            region_result.update(self.ocr_region(img, bbox))

                except Exception as e:
                    logger.warning("  区域 %d 处理失败: %s", r_idx + 1, e)
                    region_result["error"] = str(e)

                page_regions.append(region_result)

            page_elapsed = (time.time() - page_t0) * 1000
            logger.info("  第 %d 页完成 (%.0fms)", page_idx + 1, page_elapsed)

            all_pages.append({
                "page_index": page_idx,
                "regions": page_regions,
                "elapsed_ms": round(page_elapsed),
            })

            if progress_callback:
                try:
                    progress_callback(page_idx + 1, len(images))
                except Exception:
                    pass

        doc.close()
        total_elapsed = (time.time() - t0) * 1000

        return {
            "file": os.path.basename(pdf_path),
            "total_pages": len(all_pages),
            "elapsed_ms": round(total_elapsed),
            "pages": all_pages,
        }
