"""迁移脚本：创建 tool_registry 表 + 迁移内置工具"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import engine, SessionLocal
from app.models.models import ToolDef, Base
from app.core.tools import registry


def migrate():
    print("创建 tool_registry 表...")
    ToolDef.__table__.create(engine, checkfirst=True)
    print("✅ tool_registry 表创建完成")

    db = SessionLocal()
    try:
        count = db.query(ToolDef).count()
        if count > 0:
            print(f"⏭️  表中已有 {count} 条工具记录，跳过迁移")
            return

        # 从 registry 获取所有内置工具
        print(f"迁移 {len(registry._handlers)} 个内置工具...")
        for name, handler in registry._handlers.items():
            meta = getattr(handler, "_tool_meta", None)
            if not meta:
                continue

            tool = ToolDef(
                name=meta["name"],
                description=meta["description"],
                parameters=json.dumps(meta["parameters"], ensure_ascii=False),
                handler=f"app.core.tools:{name.lstrip('_')}",
                category=meta["category"],
                is_active=True,
                is_builtin=True,
                sort_order=0,
            )
            db.add(tool)
            print(f"  ✅ {meta['name']}")

        db.commit()
        print("✅ 内置工具迁移完成")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
