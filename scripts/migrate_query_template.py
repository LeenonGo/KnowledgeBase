"""迁移脚本：创建 query_template 表 + 预置数据"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import engine, SessionLocal
from app.models.models import QueryTemplate, Base


# 预置模板数据
PRESET_TEMPLATES = [
    # 💰 销售分析
    {"category": "💰 销售", "icon": "📈", "name": "本月销售额趋势", "question": "统计本月每天的销售额，按日期排序", "sort_order": 1},
    {"category": "💰 销售", "icon": "🥧", "name": "品类销售占比", "question": "各品类的销售额和占比是多少", "sort_order": 2},
    {"category": "💰 销售", "icon": "📊", "name": "日均订单量", "question": "最近30天每天的订单数量", "sort_order": 3},
    {"category": "💰 销售", "icon": "🏙️", "name": "各城市订单量", "question": "各城市的订单数量排名前10", "sort_order": 4},

    # 👥 用户分析
    {"category": "👥 用户", "icon": "👑", "name": "消费Top10客户", "question": "消费金额最高的10个客户", "sort_order": 1},
    {"category": "👥 用户", "icon": "🌍", "name": "各城市用户量", "question": "各城市的用户数量排名", "sort_order": 2},
    {"category": "👥 用户", "icon": "⭐", "name": "VIP客户分析", "question": "VIP客户和普通客户的数量及平均消费金额", "sort_order": 3},
    {"category": "👥 用户", "icon": "🆕", "name": "新老用户对比", "question": "最近30天新注册用户和老用户的订单量对比", "sort_order": 4},

    # 📦 商品分析
    {"category": "📦 商品", "icon": "🔥", "name": "销量Top10商品", "question": "销量最高的10个商品名称和销量", "sort_order": 1},
    {"category": "📦 商品", "icon": "⭐", "name": "评价最高商品", "question": "平均评分最高的10个商品", "sort_order": 2},
    {"category": "📦 商品", "icon": "💤", "name": "滞销商品", "question": "最近30天销量为0的商品", "sort_order": 3},
    {"category": "📦 商品", "icon": "💰", "name": "最贵商品Top10", "question": "价格最高的10个商品", "sort_order": 4},
]


def migrate():
    print("创建 query_template 表...")
    QueryTemplate.__table__.create(engine, checkfirst=True)
    print("✅ query_template 表创建完成")

    # 插入预置数据（如果表为空）
    db = SessionLocal()
    try:
        count = db.query(QueryTemplate).count()
        if count == 0:
            print(f"插入 {len(PRESET_TEMPLATES)} 条预置模板...")
            for tpl in PRESET_TEMPLATES:
                db.add(QueryTemplate(**tpl))
            db.commit()
            print("✅ 预置模板插入完成")
        else:
            print(f"⏭️  表中已有 {count} 条模板，跳过预置")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
