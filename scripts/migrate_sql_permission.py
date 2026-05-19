"""迁移脚本：创建 sql_table_permission 表 + 默认权限 + 测试用户"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import engine, SessionLocal
from app.models.models import SqlTablePermission, User, Base
from werkzeug.security import generate_password_hash


# 默认权限配置
DEFAULT_PERMISSIONS = [
    # user 角色：受限访问
    {"role": "user", "table_name": "orders", "can_query": True, "max_rows": 100, "columns_deny": ""},
    {"role": "user", "table_name": "products", "can_query": True, "max_rows": 200, "columns_deny": "cost_price"},
    {"role": "user", "table_name": "categories", "can_query": True, "max_rows": 100, "columns_deny": ""},
    {"role": "user", "table_name": "users", "can_query": False, "max_rows": 0, "columns_deny": ""},
    {"role": "user", "table_name": "order_items", "can_query": False, "max_rows": 0, "columns_deny": ""},
    {"role": "user", "table_name": "reviews", "can_query": True, "max_rows": 100, "columns_deny": "user_id"},
    {"role": "user", "table_name": "addresses", "can_query": False, "max_rows": 0, "columns_deny": ""},
    {"role": "user", "table_name": "coupons", "can_query": True, "max_rows": 50, "columns_deny": ""},
    {"role": "user", "table_name": "login_logs", "can_query": False, "max_rows": 0, "columns_deny": ""},

    # kb_admin 角色：大部分表可访问
    {"role": "kb_admin", "table_name": "orders", "can_query": True, "max_rows": 500, "columns_deny": ""},
    {"role": "kb_admin", "table_name": "products", "can_query": True, "max_rows": 500, "columns_deny": ""},
    {"role": "kb_admin", "table_name": "categories", "can_query": True, "max_rows": 500, "columns_deny": ""},
    {"role": "kb_admin", "table_name": "users", "can_query": True, "max_rows": 500, "columns_deny": "password_hash"},
    {"role": "kb_admin", "table_name": "order_items", "can_query": True, "max_rows": 500, "columns_deny": ""},
    {"role": "kb_admin", "table_name": "reviews", "can_query": True, "max_rows": 500, "columns_deny": ""},
    {"role": "kb_admin", "table_name": "addresses", "can_query": True, "max_rows": 500, "columns_deny": ""},
    {"role": "kb_admin", "table_name": "coupons", "can_query": True, "max_rows": 500, "columns_deny": ""},
    {"role": "kb_admin", "table_name": "login_logs", "can_query": True, "max_rows": 500, "columns_deny": ""},
]

# 测试用户
TEST_USERS = [
    {"username": "sales01", "display_name": "张三（销售）", "role": "user", "password": "123456"},
    {"username": "finance01", "display_name": "李四（财务）", "role": "user", "password": "123456"},
    {"username": "operator01", "display_name": "王五（运营）", "role": "kb_admin", "password": "123456"},
]


def migrate():
    print("创建 sql_table_permission 表...")
    SqlTablePermission.__table__.create(engine, checkfirst=True)
    print("✅ sql_table_permission 表创建完成")

    db = SessionLocal()
    try:
        # 插入默认权限
        count = db.query(SqlTablePermission).count()
        if count == 0:
            print(f"插入 {len(DEFAULT_PERMISSIONS)} 条默认权限...")
            for p in DEFAULT_PERMISSIONS:
                db.add(SqlTablePermission(**p))
            db.commit()
            print("✅ 默认权限插入完成")
        else:
            print(f"⏭️  权限表中已有 {count} 条记录，跳过")

        # 插入测试用户
        print("\n创建测试用户...")
        for u in TEST_USERS:
            exists = db.query(User).filter(User.username == u["username"]).first()
            if exists:
                print(f"  ⏭️  {u['username']} 已存在")
                continue
            user = User(
                username=u["username"],
                display_name=u["display_name"],
                role=u["role"],
                password_hash=generate_password_hash(u["password"]),
                status="active",
            )
            db.add(user)
            print(f"  ✅ {u['username']} ({u['display_name']}) - 角色: {u['role']}")
        db.commit()
        print("✅ 测试用户创建完成")

    finally:
        db.close()


if __name__ == "__main__":
    migrate()
