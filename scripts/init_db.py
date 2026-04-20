#!/usr/bin/env python3
"""初始化数据库 — 创建表并插入默认数据"""

import os
import sys
from pathlib import Path

# 加到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# 默认用 MySQL，可通过环境变量覆盖
os.environ.setdefault("DB_TYPE", "mysql")

from app.core.database import engine, Base, DATABASE_URL
from app.models.models import (  # noqa: F401 — 确保所有模型被导入
    Department, User, KnowledgeBase, Document,
    KBDepartmentAccess, KBUserAccess, Conversation, ConversationTurn,
    QAFeedback, AuditLog,
)


def main():
    # 脱敏打印连接信息
    safe_url = DATABASE_URL
    if "@" in safe_url:
        safe_url = safe_url.split("@")[1]
    print(f"数据库: {safe_url}")
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
        dept_head = Department(
            id="dept-001",
            name="总公司",
            path="/总公司",
            description="集团总部",
            status="active",
        )
        db.add(dept_head)
        db.flush()

        dept_rd = Department(
            id="dept-002",
            name="研发部",
            path="/总公司/研发部",
            parent_id="dept-001",
            description="研发部门",
            status="active",
        )
        db.add(dept_rd)

        dept_sales = Department(
            id="dept-003",
            name="销售部",
            path="/总公司/销售部",
            parent_id="dept-001",
            description="销售部门",
            status="active",
        )
        db.add(dept_sales)
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

    except Exception as e:
        db.rollback()
        print(f"❌ 初始化失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
