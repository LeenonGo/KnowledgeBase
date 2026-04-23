#!/usr/bin/env python3
"""PDF 版面分析 CLI — 知识库优化版

用法：
    python scripts/ocr_cli.py pdf input.pdf -o output.json --md output.md
    python scripts/ocr_cli.py pdf input.pdf --dpi 250 -o out.json --md out.md
    python scripts/ocr_cli.py pdf input.pdf --raw -o raw_out.json
"""

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.ocr import OCREngine, build_clean_output, build_markdown


def main():
    parser = argparse.ArgumentParser(description="PDF 版面分析工具（知识库优化版）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_pdf = sub.add_parser("pdf", help="PDF 版面分析")
    p_pdf.add_argument("path", help="PDF 路径")
    p_pdf.add_argument("--lang", default="ch")
    p_pdf.add_argument("--device", default="cpu")
    p_pdf.add_argument("--dpi", type=int, default=200)
    p_pdf.add_argument("--confidence", type=float, default=0.5)
    p_pdf.add_argument("--no-ocr", action="store_true")
    p_pdf.add_argument("--no-table", action="store_true")
    p_pdf.add_argument("--formula", action="store_true")
    p_pdf.add_argument("--skip", nargs="+", default=[],
                       help="跳过的区域类型, 如 figure header footer")
    p_pdf.add_argument("-o", "--output", help="输出 JSON 路径")
    p_pdf.add_argument("--md", help="输出 Markdown 路径")
    p_pdf.add_argument("--raw", action="store_true",
                       help="保留完整原始数据（不精简）")

    args = parser.parse_args()
    engine = OCREngine(lang=args.lang, device=args.device)

    if args.command == "pdf":
        raw_result = engine.analyze_pdf(
            args.path,
            dpi=args.dpi,
            enable_ocr=not args.no_ocr,
            enable_table=not args.no_table,
            enable_formula=args.formula,
            layout_confidence=args.confidence,
            skip_labels=args.skip,
        )

        output_data = raw_result if args.raw else build_clean_output(raw_result)

        # 打印摘要
        print(f"\n{'=' * 60}")
        print(f"  文件: {output_data['file']}")
        print(f"  页数: {output_data['total_pages']}")
        print(f"  耗时: {output_data['elapsed_ms']}ms")
        print(f"{'=' * 60}")

        for page in output_data.get("pages", []):
            pidx = page.get("page", page.get("page_index", 0) + 1)
            print(f"\n  第 {pidx} 页:")
            for s in page.get("sections", page.get("regions", [])):
                stype = s.get("type", "?")
                if stype == "table":
                    md = s.get("markdown", s.get("html", ""))
                    preview = md[:120].replace("\n", " ") if md else "(空)"
                    print(f"    [表格] {preview}")
                elif stype == "formula":
                    print(f"    [公式] {s.get('latex', '')[:80]}")
                else:
                    content = s.get("content", s.get("full_text", ""))
                    print(f"    [{stype}] {content[:100].replace(chr(10), ' ')}")

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2, default=str)
            size = os.path.getsize(args.output)
            print(f"\n[+] JSON 已保存: {args.output} ({size:,} bytes)")

        if args.md:
            md_content = build_markdown(output_data)
            with open(args.md, "w", encoding="utf-8") as f:
                f.write(md_content)
            size = os.path.getsize(args.md)
            print(f"[+] Markdown 已保存: {args.md} ({size:,} bytes)")


if __name__ == "__main__":
    t0 = datetime.datetime.now()
    main()
    t1 = datetime.datetime.now()
    print(f"程序用时: {t1 - t0}s")
