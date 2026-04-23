"""文本分块 — 支持固定长度、结构分析、语义感知三种策略"""

import re

from app.core.loader import load_document


# ─── 策略 1：固定长度 + Overlap ──────────────────

def _split_fixed(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """按字符数硬切，支持重叠"""
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


# ─── 策略 2：结构分析分块 ────────────────────────

_HEADING_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)


def _split_structural(text: str, chunk_size: int = 1024, heading_level: int = 2) -> list[str]:
    """
    基于 Markdown 标题层级切分。
    按指定级别（及更高级别）的标题拆成段落，超长段落再按句子二次拆分。
    """
    if not text.strip():
        return []

    # 找到所有标题及其位置
    headings = [(m.start(), m.end(), len(m.group(1)), m.group(2).strip())
                for m in _HEADING_PATTERN.finditer(text)]

    if not headings:
        # 没有标题，降级为固定长度
        return _split_fixed(text, chunk_size, chunk_overlap=0)

    # 按指定层级切割段落
    sections = []
    for i, (start_pos, end_pos, level, title) in enumerate(headings):
        if level > heading_level:
            continue
        # 内容从当前标题结束到下一个同级或更高级标题
        content_start = end_pos
        content_end = len(text)
        for j in range(i + 1, len(headings)):
            if headings[j][2] <= level:
                content_end = headings[j][0]
                break
        section_text = text[content_start:content_end].strip()
        heading_line = text[start_pos:end_pos].strip()
        full_section = heading_line + "\n" + section_text if section_text else heading_line
        sections.append({"title": title, "text": full_section, "level": level})

    # 合并小段落 + 拆分大段落
    chunks = []
    buffer = ""
    for sec in sections:
        candidate = (buffer + "\n\n" + sec["text"]).strip() if buffer else sec["text"]
        if len(candidate) <= chunk_size:
            buffer = candidate
        else:
            # 先把 buffer 产出
            if buffer:
                chunks.append(buffer)
            # 当前段落超长，按句子二次拆分
            if len(sec["text"]) > chunk_size:
                sub_chunks = _split_fixed(sec["text"], chunk_size, chunk_overlap=0)
                chunks.extend(sub_chunks)
                buffer = ""
            else:
                buffer = sec["text"]
    if buffer:
        chunks.append(buffer)

    return chunks


# ─── 策略 3：语义感知分块 ────────────────────────

_SENTENCE_PATTERN = re.compile(r'(?<=[。！？.!?])\s*|(?<=\n)')


def _split_sentences(text: str) -> list[str]:
    """按句子边界拆分文本"""
    parts = _SENTENCE_PATTERN.split(text)
    return [s.strip() for s in parts if s.strip()]


def _split_semantic(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """
    语义感知分块：按句子边界拆分，保证每块语义完整。
    重叠取末尾若干个完整句子。
    """
    if not text.strip():
        return []

    sentences = _split_sentences(text)
    if not sentences:
        return []

    total_chars = sum(len(s) for s in sentences)
    avg_len = total_chars / len(sentences) if sentences else 1
    overlap_sents = max(1, int(chunk_overlap / avg_len)) if avg_len > 0 else 1

    chunks = []
    current_sents = []
    current_len = 0

    for sent in sentences:
        sent_len = len(sent)

        # 单句超长：当前块结束，超长句单独成块
        if sent_len > chunk_size and current_sents:
            chunks.append("".join(current_sents))
            current_sents = []
            current_len = 0

        # 加入当前句会超限：当前块结束
        if current_sents and current_len + sent_len > chunk_size:
            chunks.append("".join(current_sents))
            overlap_start = max(0, len(current_sents) - overlap_sents)
            current_sents = current_sents[overlap_start:]
            current_len = sum(len(s) for s in current_sents)

        current_sents.append(sent)
        current_len += sent_len

    if current_sents:
        chunks.append("".join(current_sents))

    return chunks


# ─── 统一入口 ────────────────────────────────────

_STRATEGIES = {
    "fixed": _split_fixed,
    "structural": _split_structural,
    "semantic": _split_semantic,
}


def split_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    strategy: str = "semantic",
    heading_level: int = 2,
) -> list[str]:
    """
    统一分块入口。

    Args:
        text: 原始文本
        chunk_size: 每块最大字符数
        chunk_overlap: 块间重叠（fixed/semantic 策略使用）
        strategy: 分块策略 — fixed / structural / semantic
        heading_level: 结构分析的切分层级（1-6）
    Returns:
        分块后的文本列表
    """
    fn = _STRATEGIES.get(strategy, _split_semantic)
    if strategy == "structural":
        return fn(text, chunk_size=chunk_size, heading_level=heading_level)
    return fn(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def load_and_split(
    file_path: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    strategy: str = "semantic",
    heading_level: int = 2,
    progress_callback=None,
) -> tuple[list[str], list[str]]:
    """加载文档并分块，返回 (分块列表, 警告列表)"""
    text, warnings = load_document(file_path, progress_callback=progress_callback)
    chunks = split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap,
                        strategy=strategy, heading_level=heading_level)
    return chunks, warnings
