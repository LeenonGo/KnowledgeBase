"""SQLAlchemy ORM 模型 — 第一期 P0 核心表"""

import nanoid
from datetime import datetime, timezone, timedelta

# 时区：Asia/Shanghai (UTC+8)
_CST = timezone(timedelta(hours=8))

def _now():
    return datetime.now(_CST)

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def gen_id():
    return nanoid.generate(size=21)


# ─── 部门 ─────────────────────────────────────────
class Department(Base):
    __tablename__ = "department"

    id = Column(String(32), primary_key=True, default=gen_id)
    name = Column(String(128), nullable=False)
    path = Column(String(512), nullable=False, comment="层级路径，如 /总公司/技术中心/研发部")
    parent_id = Column(String(32), ForeignKey("department.id"), nullable=True)
    description = Column(Text, default="")
    status = Column(String(16), default="active")  # active / disabled
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    # 自引用关系
    children = relationship("Department", backref="parent", remote_side=[id])


# ─── 用户 ─────────────────────────────────────────
class User(Base):
    __tablename__ = "user"

    id = Column(String(32), primary_key=True, default=gen_id)
    username = Column(String(64), unique=True, nullable=False)
    display_name = Column(String(128), nullable=False)
    email = Column(String(256), default="")
    phone = Column(String(32), default="")
    password_hash = Column(String(256), nullable=False)
    department_id = Column(String(32), ForeignKey("department.id"), nullable=True)
    position = Column(String(128), default="")
    role = Column(String(32), default="user", comment="super_admin / kb_admin / user")
    status = Column(String(16), default="active")  # active / disabled
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    department = relationship("Department", lazy="joined")


# ─── 知识库 ───────────────────────────────────────
class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id = Column(String(32), primary_key=True, default=gen_id)
    name = Column(String(256), nullable=False)
    description = Column(Text, default="")
    embedding_model = Column(String(128), default="text-embedding-v3")
    llm_model = Column(String(128), default="qwen3.6-plus")
    owner_id = Column(String(32), ForeignKey("user.id"), nullable=True)
    status = Column(String(16), default="active")  # active / archived / deleted
    deleted_at = Column(DateTime, nullable=True, comment="软删除时间")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    owner = relationship("User", lazy="joined")


# ─── 文档 ─────────────────────────────────────────
class Document(Base):
    __tablename__ = "document"

    id = Column(String(32), primary_key=True, default=gen_id)
    filename = Column(String(512), nullable=False)
    original_name = Column(String(512), nullable=False)
    file_hash = Column(String(64), nullable=False, comment="SHA-256 内容哈希")
    file_size = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    kb_id = Column(String(32), ForeignKey("knowledge_base.id"), nullable=False)
    uploader_id = Column(String(32), ForeignKey("user.id"), nullable=True)
    status = Column(String(16), default="indexed")  # indexing / indexed / failed / superseded / deleted
    chunking_strategy = Column(String(32), default="fixed")
    chunk_size = Column(Integer, default=512)
    chunk_overlap = Column(Integer, default=64)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    kb = relationship("KnowledgeBase", lazy="joined")
    uploader = relationship("User", lazy="joined")

    __table_args__ = (
        UniqueConstraint("kb_id", "filename", name="uq_doc_kb_filename"),
        Index("ix_doc_kb", "kb_id"),
        Index("ix_doc_hash", "file_hash"),
    )


# ─── 知识库 × 部门 授权 ───────────────────────────
class KBDepartmentAccess(Base):
    __tablename__ = "kb_department_access"

    id = Column(String(32), primary_key=True, default=gen_id)
    kb_id = Column(String(32), ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(String(32), ForeignKey("department.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(16), default="viewer", comment="admin / editor / viewer")
    created_by = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=_now)

    __table_args__ = (
        UniqueConstraint("kb_id", "department_id", name="uq_kb_dept"),
        Index("ix_kb_dept_kb", "kb_id"),
        Index("ix_kb_dept_dept", "department_id"),
    )


# ─── 知识库 × 用户 授权 ───────────────────────────
class KBUserAccess(Base):
    __tablename__ = "kb_user_access"

    id = Column(String(32), primary_key=True, default=gen_id)
    kb_id = Column(String(32), ForeignKey("knowledge_base.id"), nullable=False)
    user_id = Column(String(32), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(16), default="viewer", comment="admin / editor / viewer")
    created_by = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=_now)

    __table_args__ = (
        UniqueConstraint("kb_id", "user_id", name="uq_kb_user"),
        Index("ix_kb_user_kb", "kb_id"),
        Index("ix_kb_user_uid", "user_id"),
    )


# ─── 会话 ─────────────────────────────────────────
class Conversation(Base):
    __tablename__ = "conversation"

    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(512), default="新对话")
    status = Column(String(16), default="active")  # active / closed
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


# ─── 对话轮次 ─────────────────────────────────────
class ConversationTurn(Base):
    __tablename__ = "conversation_turn"

    id = Column(String(32), primary_key=True, default=gen_id)
    conversation_id = Column(String(32), ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(16), nullable=False, comment="user / assistant")
    content = Column(Text, nullable=False)
    sources = Column(Text, default="", comment="JSON 格式的引用来源列表")
    model = Column(String(128), default="")
    latency_ms = Column(Integer, default=0)
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime, default=_now)

    __table_args__ = (
        Index("ix_turn_conv", "conversation_id"),
    )


# ─── 用户反馈 ─────────────────────────────────────
class QAFeedback(Base):
    __tablename__ = "qa_feedback"

    id = Column(String(32), primary_key=True, default=gen_id)
    turn_id = Column(String(32), ForeignKey("conversation_turn.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(32), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    rating = Column(String(16), nullable=False, comment="up / down")
    comment = Column(Text, default="")
    created_at = Column(DateTime, default=_now)


# ─── 审计日志 ─────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), nullable=True)
    username = Column(String(64), default="")
    action = Column(String(64), nullable=False, comment="login / upload / delete / query / ...")
    resource = Column(String(512), default="", comment="操作对象")
    detail = Column(Text, default="", comment="操作详情（脱敏）")
    ip_address = Column(String(64), default="")
    status = Column(String(16), default="success")  # success / failure
    created_at = Column(DateTime, default=_now)

    __table_args__ = (
        Index("ix_audit_user", "user_id"),
        Index("ix_audit_time", "created_at"),
    )


# ─── 评测集 ─────────────────────────────────────
class EvalDataset(Base):
    __tablename__ = "eval_dataset"

    id = Column(String(32), primary_key=True, default=gen_id)
    kb_id = Column(String(32), ForeignKey("knowledge_base.id"), nullable=False)
    name = Column(String(256), default="")
    question_count = Column(Integer, default=0)
    status = Column(String(16), default="ready")  # generating / ready / error
    created_by = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    kb = relationship("KnowledgeBase", lazy="joined")

    __table_args__ = (
        Index("ix_eval_ds_kb", "kb_id"),
    )


# ─── 评测问题 ─────────────────────────────────────
class EvalQuestion(Base):
    __tablename__ = "eval_question"

    id = Column(String(32), primary_key=True, default=gen_id)
    dataset_id = Column(String(32), ForeignKey("eval_dataset.id", ondelete="CASCADE"), nullable=False)
    kb_id = Column(String(32), nullable=False)
    question = Column(Text, nullable=False)
    expected_answer = Column(Text, default="")
    category = Column(String(32), nullable=False, comment="factual / out_of_scope / multi_doc / ambiguous / false_premise")
    source_hint = Column(String(512), default="")
    ref_chunks = Column(Text, default="[]", comment="JSON 数组：参考原文片段")
    created_at = Column(DateTime, default=_now)

    __table_args__ = (
        Index("ix_eval_q_ds", "dataset_id"),
    )


# ─── 评测运行 ─────────────────────────────────────
class EvalRun(Base):
    __tablename__ = "eval_run"

    id = Column(String(32), primary_key=True, default=gen_id)
    dataset_id = Column(String(32), ForeignKey("eval_dataset.id", ondelete="CASCADE"), nullable=False)
    kb_id = Column(String(32), nullable=False)
    total = Column(Integer, default=0)
    passed = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    avg_score = Column(Float, default=0.0)
    status = Column(String(16), default="running")  # running / completed / error
    started_at = Column(DateTime, default=_now)
    finished_at = Column(DateTime, nullable=True)
    created_by = Column(String(32), nullable=True)

    dataset = relationship("EvalDataset", lazy="joined")

    __table_args__ = (
        Index("ix_eval_run_ds", "dataset_id"),
    )


# ─── 评测结果 ─────────────────────────────────────
class EvalResult(Base):
    __tablename__ = "eval_result"

    id = Column(String(32), primary_key=True, default=gen_id)
    run_id = Column(String(32), ForeignKey("eval_run.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(String(32), ForeignKey("eval_question.id", ondelete="CASCADE"), nullable=False)
    question = Column(Text, default="")
    category = Column(String(32), default="")
    expected_answer = Column(Text, default="")
    retrieved_chunks = Column(Text, default="[]", comment="JSON: 检索到的文本片段")
    actual_answer = Column(Text, default="")
    scores = Column(Text, default="{}", comment="JSON: 各维度分数")
    reasoning = Column(Text, default="")
    avg_score = Column(Float, default=0.0)
    passed = Column(Boolean, default=False)
    latency_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)

    __table_args__ = (
        Index("ix_eval_res_run", "run_id"),
    )
