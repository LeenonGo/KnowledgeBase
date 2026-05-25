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
    kb_id = Column(String(32), ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False)
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
    kb_id = Column(String(32), ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False)
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
    conv_type = Column(String(16), default="rag", comment="rag / agent")
    status = Column(String(16), default="active")  # active / closed
    is_pinned = Column(Boolean, default=False, comment="置顶")
    tags = Column(String(512), default="", comment="JSON 数组，如 [\"重要\",\"待确认\"]")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_conv_user", "user_id"),
        Index("ix_conv_user_type", "user_id", "conv_type"),
    )


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

    __table_args__ = (
        Index("ix_feedback_user", "user_id"),
        Index("ix_feedback_turn", "turn_id"),
    )


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


# ─── SQL 查询审计日志 ────────────────────────────
class QueryAuditLog(Base):
    __tablename__ = "query_audit_log"

    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), nullable=True)
    username = Column(String(64), default="")
    question = Column(Text, nullable=False, comment="自然语言问题")
    generated_sql = Column(Text, default="", comment="LLM 生成的 SQL")
    output_format = Column(String(16), default="table", comment="输出格式: json/table/report")
    row_count = Column(Integer, default=0, comment="结果行数")
    elapsed_ms = Column(Integer, default=0, comment="SQL 执行耗时(ms)")
    total_ms = Column(Integer, default=0, comment="端到端总耗时(ms)")
    error = Column(Text, default="", comment="错误信息（如有）")
    status = Column(String(16), default="success")  # success / error
    created_at = Column(DateTime, default=_now)

    __table_args__ = (
        Index("ix_qaudit_user", "user_id"),
        Index("ix_qaudit_time", "created_at"),
    )


# ─── SQL 查询模板 ──────────────────────────────
class QueryTemplate(Base):
    __tablename__ = "query_template"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50), nullable=False, comment="分类：销售/用户/商品")
    name = Column(String(100), nullable=False, comment="显示名")
    question = Column(Text, nullable=False, comment="实际提问")
    icon = Column(String(10), default="📊", comment="图标")
    sort_order = Column(Integer, default=0, comment="排序")
    is_active = Column(Boolean, default=True, comment="启用/禁用")
    created_at = Column(DateTime, default=_now)

    __table_args__ = (
        Index("ix_qtpl_category", "category"),
    )


# ─── 工具注册表 ──────────────────────────────
class ToolDef(Base):
    __tablename__ = "tool_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False, comment="工具名：search_kb")
    description = Column(Text, default="", comment="给 LLM 看的描述")
    parameters = Column(Text, default="{}", comment="JSON Schema")
    handler = Column(String(256), nullable=False, comment="执行函数路径：app.core.tools:search_kb")
    category = Column(String(32), default="general", comment="分类：kb/sql/kg/system/general")
    is_active = Column(Boolean, default=True, comment="启用/禁用")
    is_builtin = Column(Boolean, default=False, comment="内置工具不可删除")
    sort_order = Column(Integer, default=0, comment="排序")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_treg_category", "category"),
    )


# ─── SQL 表级权限 ──────────────────────────────
class SqlTablePermission(Base):
    __tablename__ = "sql_table_permission"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(String(32), nullable=False, comment="角色：user / kb_admin / super_admin")
    table_name = Column(String(64), nullable=False, comment="表名：orders / users / products")
    can_query = Column(Boolean, default=True, comment="允许查询")
    max_rows = Column(Integer, default=500, comment="最大返回行数")
    columns_deny = Column(Text, default="", comment="禁止查询的列（逗号分隔）")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("role", "table_name", name="uk_role_table"),
        Index("ix_stp_role", "role"),
    )


# ─── 评测集 ─────────────────────────────────────
class EvalDataset(Base):
    __tablename__ = "eval_dataset"

    id = Column(String(32), primary_key=True, default=gen_id)
    kb_id = Column(String(32), ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False)
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


# ─── 全链路 Trace ─────────────────────────────────
class Trace(Base):
    __tablename__ = "trace"

    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), nullable=True)
    question = Column(Text, default="")
    total_duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)

    spans = relationship("TraceSpan", backref="trace", lazy="joined")

    __table_args__ = (
        Index("ix_trace_user", "user_id"),
        Index("ix_trace_time", "created_at"),
    )


# ─── 用户记忆 ─────────────────────────────────────
class UserMemory(Base):
    __tablename__ = "user_memory"

    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    memory_type = Column(String(32), nullable=False, comment="preference / context / correction")
    content = Column(Text, nullable=False, comment="记忆内容（自然语言）")
    source_conv_id = Column(String(32), nullable=True, comment="来源对话 ID")
    confidence = Column(Float, default=1.0, comment="置信度，随时间衰减")
    hit_count = Column(Integer, default=0, comment="被引用次数")
    last_hit_at = Column(DateTime, nullable=True)
    expired_at = Column(DateTime, nullable=True, comment="过期时间")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_um_user", "user_id"),
        Index("ix_um_type", "user_id", "memory_type"),
    )


# ─── FAQ 沉淀 ─────────────────────────────────────
class FAQ(Base):
    __tablename__ = "faq"

    id = Column(String(32), primary_key=True, default=gen_id)
    kb_id = Column(String(32), ForeignKey("knowledge_base.id"), nullable=True, comment="关联知识库，NULL 表示全局")
    question = Column(Text, nullable=False, comment="标准问题")
    answer = Column(Text, nullable=False, comment="沉淀答案")
    source_turn_id = Column(String(32), nullable=True, comment="来源对话轮次 ID")
    source_citations = Column(Text, default="[]", comment="JSON：原始引用来源")
    hit_count = Column(Integer, default=0, comment="命中次数")
    avg_rating = Column(Float, nullable=True, comment="平均评分")
    status = Column(String(16), default="auto", comment="auto / approved / rejected / archived")
    confidence = Column(Float, default=1.0, comment="置信度，随时间衰减")
    approved_by = Column(String(32), nullable=True, comment="审核人")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_faq_kb", "kb_id"),
        Index("ix_faq_status", "status"),
    )


# ─── FAQ 标签 ─────────────────────────────────────
class FAQTag(Base):
    __tablename__ = "faq_tag"

    faq_id = Column(String(32), ForeignKey("faq.id", ondelete="CASCADE"), primary_key=True)
    tag = Column(String(100), primary_key=True)


# ─── FAQ 候选统计（高频问题计数）─────────────────
class FAQCandidate(Base):
    __tablename__ = "faq_candidate"

    id = Column(String(32), primary_key=True, default=gen_id)
    kb_id = Column(String(32), nullable=True)
    question_hash = Column(String(64), nullable=False, comment="问题归一化哈希")
    question_sample = Column(Text, nullable=False, comment="样本问题")
    hit_count = Column(Integer, default=1)
    positive_count = Column(Integer, default=0, comment="好评次数")
    last_answer = Column(Text, default="", comment="最近一次回答")
    last_citations = Column(Text, default="[]", comment="最近引用来源")
    last_turn_id = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_faqc_hash", "question_hash"),
        Index("ix_faqc_kb", "kb_id"),
    )


class TraceSpan(Base):
    __tablename__ = "trace_span"

    id = Column(String(32), primary_key=True, default=gen_id)
    trace_id = Column(String(32), ForeignKey("trace.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    duration_ms = Column(Integer, default=0)
    input_preview = Column(Text, default="")
    output_preview = Column(Text, default="")
    seq = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)

    __table_args__ = (
        Index("ix_span_trace", "trace_id"),
    )


# ─── Skills 插件化 ─────────────────────────────
class Skill(Base):
    """技能定义 — 可插拔的 Agent 能力单元"""
    __tablename__ = "skill"

    id = Column(String(32), primary_key=True, default=gen_id)
    name = Column(String(100), unique=True, nullable=False, comment="唯一标识：knowledge_search")
    display_name = Column(String(100), nullable=False, comment="显示名称：知识库检索")
    description = Column(Text, default="", comment="功能描述")
    category = Column(String(50), default="general", comment="分类：retrieval/analysis/generation/utility/memory")
    version = Column(String(20), default="1.0.0")
    author = Column(String(100), default="system")
    icon = Column(String(10), default="⚡", comment="图标 emoji")

    # Skill 配置（JSON Schema）
    parameters_schema = Column(Text, default="{}", comment="参数 JSON Schema")
    return_schema = Column(Text, default="{}", comment="返回值 JSON Schema")

    # 执行配置
    handler_type = Column(String(20), default="python", comment="python / http / prompt")
    handler_config = Column(Text, default="{}", comment="执行逻辑配置 JSON")
    # python: {"module": "app.core.tools", "function": "_search_kb"}
    # http: {"url": "https://api.example.com", "method": "POST"}
    # prompt: {"system": "...", "template": "...", "tools": ["sql_query"]}

    # 权限 & 限制
    required_role = Column(String(32), default="user", comment="最低角色要求")
    rate_limit = Column(Integer, default=100, comment="每分钟调用上限")
    timeout_seconds = Column(Integer, default=30, comment="超时时间")

    # 状态 & 统计
    is_enabled = Column(Boolean, default=True)
    is_builtin = Column(Boolean, default=False, comment="内置 Skill 不可删除")
    usage_count = Column(Integer, default=0, comment="调用次数")
    avg_latency_ms = Column(Float, default=0, comment="平均延迟")
    last_used_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_skill_category", "category"),
        Index("ix_skill_enabled", "is_enabled"),
    )


class SkillExecutionLog(Base):
    """Skill 执行日志"""
    __tablename__ = "skill_execution_log"

    id = Column(String(32), primary_key=True, default=gen_id)
    skill_id = Column(String(32), ForeignKey("skill.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(32), nullable=True)
    arguments = Column(Text, default="{}", comment="调用参数 JSON")
    result_preview = Column(Text, default="", comment="结果预览（前200字）")
    success = Column(Boolean, default=True)
    error_message = Column(Text, default="")
    latency_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)

    __table_args__ = (
        Index("ix_skill_log_skill", "skill_id"),
        Index("ix_skill_log_user", "user_id"),
    )
