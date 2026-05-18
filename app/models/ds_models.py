"""数据源同步 ORM 模型"""

import nanoid
import json
from datetime import datetime, timezone, timedelta

_CST = timezone(timedelta(hours=8))

def _now():
    return datetime.now(_CST)

from sqlalchemy import Column, String, Text, Integer, Float, Boolean, DateTime, ForeignKey, Index

from app.core.database import Base


def gen_id():
    return nanoid.generate(size=21)


class SyncStatus:
    IDLE = "idle"
    SYNCING = "syncing"
    SUCCESS = "success"
    ERROR = "error"


class SourceType:
    GIT = "git"
    WEB_URL = "web_url"
    FEISHU = "feishu"
    CONFLUENCE = "confluence"

    ALL = [GIT, WEB_URL, FEISHU, CONFLUENCE]

    LABELS = {
        GIT: "Git 仓库",
        WEB_URL: "网页 URL",
        FEISHU: "飞书文档",
        CONFLUENCE: "Confluence",
    }

    ICONS = {
        GIT: "🔀",
        WEB_URL: "🌐",
        FEISHU: "📘",
        CONFLUENCE: "📝",
    }


class DataSource(Base):
    __tablename__ = "data_source"

    id = Column(String(32), primary_key=True, default=gen_id)
    kb_id = Column(String(32), nullable=False, comment="关联知识库 ID")
    name = Column(String(256), nullable=False, comment="数据源名称")
    source_type = Column(String(32), nullable=False, comment="git / web_url / feishu / confluence")
    config = Column(Text, default="{}", comment="连接配置 JSON")
    sync_cron = Column(String(64), default="", comment="定时表达式，空=手动")
    sync_status = Column(String(16), default=SyncStatus.IDLE, comment="idle / syncing / success / error")
    last_sync_at = Column(DateTime, nullable=True, comment="上次同步时间")
    last_sync_result = Column(Text, default="{}", comment="同步结果 JSON")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_ds_kb", "kb_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "kb_id": self.kb_id,
            "name": self.name,
            "source_type": self.source_type,
            "source_type_label": SourceType.LABELS.get(self.source_type, self.source_type),
            "source_type_icon": SourceType.ICONS.get(self.source_type, "📁"),
            "config": json.loads(self.config) if self.config else {},
            "sync_cron": self.sync_cron,
            "sync_status": self.sync_status,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_sync_result": json.loads(self.last_sync_result) if self.last_sync_result else {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
