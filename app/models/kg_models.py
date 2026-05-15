"""知识图谱 ORM 模型 — 实体 + 关系"""

import nanoid
import json
from datetime import datetime, timezone, timedelta

_CST = timezone(timedelta(hours=8))

def _now():
    return datetime.now(_CST)

from sqlalchemy import (
    Column, String, Text, Integer, Float, DateTime, ForeignKey, Index
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def gen_id():
    return nanoid.generate(size=21)


# ─── 实体类型枚举（Python 侧用常量，DB 侧用 String）──
class EntityType:
    PERSON = "PERSON"
    ORG = "ORG"
    CONCEPT = "CONCEPT"
    PRODUCT = "PRODUCT"
    LOCATION = "LOCATION"
    EVENT = "EVENT"
    OTHER = "OTHER"

    ALL = [PERSON, ORG, CONCEPT, PRODUCT, LOCATION, EVENT, OTHER]

    LABELS = {
        PERSON: "人名",
        ORG: "组织",
        CONCEPT: "概念",
        PRODUCT: "产品",
        LOCATION: "地点",
        EVENT: "事件",
        OTHER: "其他",
    }

    COLORS = {
        PERSON: "#4A90D9",
        ORG: "#50B76C",
        CONCEPT: "#9B59B6",
        PRODUCT: "#E67E22",
        LOCATION: "#E74C3C",
        EVENT: "#1ABC9C",
        OTHER: "#95A5A6",
    }


# ─── kg_entity 实体表 ─────────────────────────────
class KGEntity(Base):
    __tablename__ = "kg_entity"

    id = Column(String(32), primary_key=True, default=gen_id)
    kb_id = Column(String(32), ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(256), nullable=False, comment="实体名称")
    entity_type = Column(String(32), default=EntityType.OTHER, comment="实体类型")
    description = Column(Text, default="", comment="实体描述")
    doc_chunk_ids = Column(Text, default="[]", comment="来源 chunk ID JSON 数组")
    frequency = Column(Integer, default=1, comment="出现次数")
    embedding = Column(Text, default="[]", comment="实体向量 JSON 数组")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_kg_entity_kb_name", "kb_id", "name"),
        Index("ix_kg_entity_type", "entity_type"),
        Index("ix_kg_entity_kb", "kb_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "kb_id": self.kb_id,
            "name": self.name,
            "entity_type": self.entity_type,
            "entity_type_label": EntityType.LABELS.get(self.entity_type, "其他"),
            "entity_type_color": EntityType.COLORS.get(self.entity_type, "#95A5A6"),
            "description": self.description,
            "doc_chunk_ids": json.loads(self.doc_chunk_ids) if self.doc_chunk_ids else [],
            "frequency": self.frequency,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ─── kg_relation 关系表 ───────────────────────────
class KGRelation(Base):
    __tablename__ = "kg_relation"

    id = Column(String(32), primary_key=True, default=gen_id)
    kb_id = Column(String(32), ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False)
    subject_id = Column(String(32), ForeignKey("kg_entity.id", ondelete="CASCADE"), nullable=False)
    predicate = Column(String(128), nullable=False, comment="关系谓词")
    object_id = Column(String(32), ForeignKey("kg_entity.id", ondelete="CASCADE"), nullable=False)
    doc_chunk_id = Column(String(64), default="", comment="来源 chunk ID")
    confidence = Column(Float, default=0.8, comment="抽取置信度")
    created_at = Column(DateTime, default=_now)

    subject = relationship("KGEntity", foreign_keys=[subject_id], lazy="joined")
    object_ = relationship("KGEntity", foreign_keys=[object_id], lazy="joined")

    __table_args__ = (
        Index("ix_kg_relation_subject", "subject_id"),
        Index("ix_kg_relation_object", "object_id"),
        Index("ix_kg_relation_kb", "kb_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "kb_id": self.kb_id,
            "subject_id": self.subject_id,
            "subject_name": self.subject.name if self.subject else "",
            "predicate": self.predicate,
            "object_id": self.object_id,
            "object_name": self.object_.name if self.object_ else "",
            "confidence": self.confidence,
            "doc_chunk_id": self.doc_chunk_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
