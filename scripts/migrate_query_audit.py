"""迁移脚本：创建 query_audit_log 表"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import engine
from app.models.models import QueryAuditLog, Base


def migrate():
    print("创建 query_audit_log 表...")
    QueryAuditLog.__table__.create(engine, checkfirst=True)
    print("✅ query_audit_log 表创建完成")


if __name__ == "__main__":
    migrate()
