#!/usr/bin/env python3
"""
数据库增量迁移 — 添加新约束和索引，不删除现有数据。

用法:
  python scripts/migrate_db.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()
os.environ.setdefault("DB_TYPE", "mysql")

from sqlalchemy import text
from app.core.database import engine, DATABASE_URL


def migrate():
    safe_url = DATABASE_URL.split("@")[1] if "@" in DATABASE_URL else DATABASE_URL
    print(f"数据库: {safe_url}")

    with engine.connect() as conn:
        dialect = engine.dialect.name
        print(f"数据库类型: {dialect}")

        # ── 1. 检查 document 表是否有重复的 (kb_id, filename) ──
        print("\n📋 检查 document 表重复数据...")
        try:
            result = conn.execute(text("""
                SELECT kb_id, filename, COUNT(*) as cnt
                FROM document
                WHERE status != 'deleted'
                GROUP BY kb_id, filename
                HAVING cnt > 1
            """))
            dupes = result.fetchall()
            if dupes:
                print(f"  ⚠️  发现 {len(dupes)} 组重复的 (kb_id, filename):")
                for row in dupes:
                    print(f"    kb_id={row[0]}, filename={row[1]}, count={row[2]}")
                print("  处理方式: 保留最新的记录，标记旧的为 deleted")
                for row in dupes:
                    conn.execute(text("""
                        UPDATE document
                        SET status = 'deleted'
                        WHERE kb_id = :kb AND filename = :fn AND status != 'deleted'
                        AND id NOT IN (
                            SELECT id FROM (
                                SELECT id FROM document
                                WHERE kb_id = :kb AND filename = :fn AND status != 'deleted'
                                ORDER BY created_at DESC LIMIT 1
                            ) AS keep
                        )
                    """), {"kb": row[0], "fn": row[1]})
                conn.commit()
                print("  ✅ 重复数据已处理")
            else:
                print("  ✅ 无重复数据")
        except Exception as e:
            print(f"  ⚠️  检查失败（表可能不存在）: {e}")

        # ── 2. 添加索引和约束 ──
        migrations = [
            # Document 唯一约束
            ("document", "uq_doc_kb_filename",
             "ALTER TABLE document ADD CONSTRAINT uq_doc_kb_filename UNIQUE (kb_id, filename)"),
            # Document 索引
            ("document", "ix_doc_kb",
             "CREATE INDEX ix_doc_kb ON document (kb_id)" if dialect == "mysql"
             else "CREATE INDEX IF NOT EXISTS ix_doc_kb ON document (kb_id)"),
            ("document", "ix_doc_hash",
             "CREATE INDEX ix_doc_hash ON document (file_hash)" if dialect == "mysql"
             else "CREATE INDEX IF NOT EXISTS ix_doc_hash ON document (file_hash)"),
            # KBDepartmentAccess 索引
            ("kb_department_access", "ix_kb_dept_kb",
             "CREATE INDEX ix_kb_dept_kb ON kb_department_access (kb_id)" if dialect == "mysql"
             else "CREATE INDEX IF NOT EXISTS ix_kb_dept_kb ON kb_department_access (kb_id)"),
            ("kb_department_access", "ix_kb_dept_dept",
             "CREATE INDEX ix_kb_dept_dept ON kb_department_access (department_id)" if dialect == "mysql"
             else "CREATE INDEX IF NOT EXISTS ix_kb_dept_dept ON kb_department_access (department_id)"),
            # KBUserAccess 索引
            ("kb_user_access", "ix_kb_user_kb",
             "CREATE INDEX ix_kb_user_kb ON kb_user_access (kb_id)" if dialect == "mysql"
             else "CREATE INDEX IF NOT EXISTS ix_kb_user_kb ON kb_user_access (kb_id)"),
            ("kb_user_access", "ix_kb_user_uid",
             "CREATE INDEX ix_kb_user_uid ON kb_user_access (user_id)" if dialect == "mysql"
             else "CREATE INDEX IF NOT EXISTS ix_kb_user_uid ON kb_user_access (user_id)"),
            # AuditLog 索引
            ("audit_log", "ix_audit_user",
             "CREATE INDEX ix_audit_user ON audit_log (user_id)" if dialect == "mysql"
             else "CREATE INDEX IF NOT EXISTS ix_audit_user ON audit_log (user_id)"),
            ("audit_log", "ix_audit_time",
             "CREATE INDEX ix_audit_time ON audit_log (created_at)" if dialect == "mysql"
             else "CREATE INDEX IF NOT EXISTS ix_audit_time ON audit_log (created_at)"),
            # ConversationTurn 索引
            ("conversation_turn", "ix_turn_conv",
             "CREATE INDEX ix_turn_conv ON conversation_turn (conversation_id)" if dialect == "mysql"
             else "CREATE INDEX IF NOT EXISTS ix_turn_conv ON conversation_turn (conversation_id)"),
        ]

        print("\n📋 添加索引和约束...")
        for table, name, sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
                print(f"  ✅ {table}.{name}")
            except Exception as e:
                err_msg = str(e).lower()
                if "duplicate" in err_msg or "already exists" in err_msg or "1061" in err_msg:
                    print(f"  ⏭️  {table}.{name}（已存在，跳过）")
                else:
                    print(f"  ❌ {table}.{name}: {e}")

    print("\n✅ 迁移完成")


if __name__ == "__main__":
    migrate()
