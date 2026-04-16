#!/usr/bin/env python3
"""初始化数据库 — 创建表并插入默认数据"""

import sys
from pathlib import Path

# 加到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import engine, Base
from app.models.models import (  # noqa: F401 — 确保所有模型被导入
    Department, User, KnowledgeBase, Document,
    KBDepartmentAccess, KBUserAccess, Conversation, ConversationTurn,
    QAFeedback, AuditLog,
)


def main():
    print("正在创建数据库表...")
    Base.metadata.create_all(bind=engine)

    from app.core.database import SessionLocal
    from app.models.models import User, Department
    from werkzeug.security import generate_password_hash

    db = SessionLocal()
    try:
        # 检查是否已有数据
        if db.query(User).first():
            print("数据库已有数据，跳过初始化")
            db.close()
            return

        # 创建默认部门
        dept = Department(
            id="dept-001",
            name="技术中心",
            path="/总公司/技术中心",
            description="技术研发部门",
            status="active",
        )
        db.add(dept)
        db.flush()

        # 创建默认管理员
        admin = User(
            id="user-admin",
            username="admin",
            display_name="管理员",
            email="admin@example.com",
            password_hash=generate_password_hash("admin123"),
            department_id="dept-001",
            position="IT 负责人",
            role="super_admin",
            status="active",
        )
        db.add(admin)
        db.commit()

        print("✅ 数据库初始化完成！")
        print(f"   管理员账号: admin / admin123")
        print(f"   数据库路径: {Path(__file__).parent.parent / 'data' / 'knowledge.db'}")

    except Exception as e:
        db.rollback()
        print(f"❌ 初始化失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
