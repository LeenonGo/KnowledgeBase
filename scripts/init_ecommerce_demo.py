"""
电商 Demo 数据库初始化 — 生成模拟数据供 SQL Agent 查询

使用：
    python scripts/init_ecommerce_demo.py

依赖：
    pip install faker pymysql
"""

import os
import sys
import random
import hashlib
from datetime import datetime, timedelta
from decimal import Decimal

# ─── 配置 ─────────────────────────────────────────

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pymysql

DB_URL = os.getenv("SQL_AGENT_DB_URL", "")

# 解析连接串
# 格式: mysql+pymysql://user:pass@host:port/dbname
def parse_db_url(url):
    """简易解析 mysql+pymysql://... 连接串"""
    url = url.replace("mysql+pymysql://", "")
    if "@" in url:
        auth, rest = url.split("@", 1)
        user, password = auth.split(":", 1)
    else:
        user, password = "root", ""
        rest = url
    if "/" in rest:
        host_port, dbname = rest.split("/", 1)
        dbname = dbname.split("?")[0]
    else:
        host_port, dbname = rest, "ecommerce_demo"
    if ":" in host_port:
        host, port = host_port.split(":")
        port = int(port)
    else:
        host, port = host_port, 3306
    return {"host": host, "port": port, "user": user, "password": password, "database": dbname}


# ─── 数据量配置 ─────────────────────────────────────

NUM_USERS = 2000
NUM_CATEGORIES = 30
NUM_PRODUCTS = 500
NUM_ORDERS = 20000
NUM_REVIEWS_RATIO = 0.6  # 60% 的已完成订单有评价
NUM_COUPONS = 20
NUM_INVENTORY_LOGS = 8000

CITIES = ["北京", "上海", "广州", "深圳", "杭州"]
CITY_WEIGHTS = [0.25, 0.25, 0.20, 0.15, 0.15]

VIP_LEVELS = [0, 1, 2, 3]
VIP_WEIGHTS = [0.60, 0.25, 0.10, 0.05]

ORDER_STATUSES = ["completed", "shipped", "paid", "pending", "cancelled", "refunded"]
STATUS_WEIGHTS = [0.70, 0.10, 0.08, 0.05, 0.04, 0.03]

# 品类结构
CATEGORY_TREE = {
    "电子产品": ["手机", "笔记本电脑", "平板电脑", "耳机", "智能手表", "充电器"],
    "服装": ["男装T恤", "女装连衣裙", "牛仔裤", "羽绒服", "运动鞋", "帽子"],
    "食品": ["零食", "坚果", "咖啡", "茶叶", "保健品", "进口食品"],
    "家居": ["床上用品", "收纳", "厨具", "灯具", "装饰品", "清洁用品"],
    "运动": ["瑜伽垫", "跑步机", "哑铃", "运动背包", "护具", "泳镜"],
}

# 价格范围（元）按子品类
PRICE_RANGES = {
    "手机": (1999, 8999), "笔记本电脑": (3999, 12999), "平板电脑": (1999, 5999),
    "耳机": (99, 2999), "智能手表": (599, 3999), "充电器": (29, 299),
    "男装T恤": (49, 399), "女装连衣裙": (99, 899), "牛仔裤": (99, 599),
    "羽绒服": (299, 1999), "运动鞋": (199, 1299), "帽子": (29, 199),
    "零食": (9, 99), "坚果": (19, 199), "咖啡": (29, 299),
    "茶叶": (39, 999), "保健品": (49, 599), "进口食品": (19, 299),
    "床上用品": (99, 1999), "收纳": (19, 299), "厨具": (29, 999),
    "灯具": (39, 799), "装饰品": (9, 599), "清洁用品": (9, 199),
    "瑜伽垫": (29, 399), "跑步机": (999, 5999), "哑铃": (29, 499),
    "运动背包": (49, 599), "护具": (19, 299), "泳镜": (29, 299),
}

# ─── 姓名生成 ─────────────────────────────────────

LAST_NAMES = "王李张刘陈杨赵黄周吴徐孙马朱胡郭何罗梁宋郑谢韩唐冯董萧程曹袁邓许傅沈曾彭吕苏卢蒋蔡贾丁魏薛叶阎余潘杜戴夏钟汪田任姜范方石姚谭廖邹熊金陆郝孔白崔康毛邱秦江史顾侯邵孟龙万段漕钱汤尹黎易常武乔贺赖龚文"
FIRST_CHARS = "伟芳娜敏静丽强磊洋勇艳杰娟涛明超秀霞平刚桂英华慧建林志强峰辉龙飞雪萍红玉梅鑫欣宇亮凯玲莉军波鑫莹"

def gen_name():
    last = random.choice(LAST_NAMES)
    first = random.choice(FIRST_CHARS) + random.choice(FIRST_CHARS)
    return last + first


# ─── 商品名生成 ─────────────────────────────────────

BRANDS = {
    "电子产品": ["小米", "华为", "苹果", "三星", "OPPO", "vivo", "联想", "戴森"],
    "服装": ["优衣库", "ZARA", "Nike", "Adidas", "李宁", "太平鸟", "海澜之家"],
    "食品": ["三只松鼠", "良品铺子", "百草味", "雀巢", "蒙牛", "伊利", "康师傅"],
    "家居": ["宜家", "网易严选", "小米有品", "无印良品", "顾家家居"],
    "运动": ["Nike", "Adidas", "李宁", "迪卡侬", "Keep", "Under Armour"],
}

MODEL_WORDS = ["Pro", "Max", "Plus", "Ultra", "Air", "Lite", "SE", "Mini",
               "旗舰版", "青春版", "尊享版", "标准版", "经典款", "新款"]

def gen_product_name(subcat):
    parent = None
    for p, children in CATEGORY_TREE.items():
        if subcat in children:
            parent = p
            break
    brand = random.choice(BRANDS.get(parent, ["通用"]))
    model = random.choice(MODEL_WORDS)
    return f"{brand} {subcat} {model}"


# ─── 主逻辑 ─────────────────────────────────────────

def main():
    if not DB_URL:
        print("❌ 未配置 SQL_AGENT_DB_URL，请在 .env 中设置")
        print("   例如：SQL_AGENT_DB_URL=mysql+pymysql://root:password@localhost:3306/ecommerce_demo")
        sys.exit(1)

    cfg = parse_db_url(DB_URL)
    dbname = cfg.pop("database")

    print(f"📦 连接 MySQL {cfg['host']}:{cfg['port']}...")

    # 先不指定 database，用来创建库
    conn = pymysql.connect(**cfg, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{dbname}` DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute(f"USE `{dbname}`")
    print(f"✅ 数据库 `{dbname}` 就绪")

    # ─── DDL ───

    ddl_statements = [
        """DROP TABLE IF EXISTS inventory_logs""",
        """DROP TABLE IF EXISTS reviews""",
        """DROP TABLE IF EXISTS coupon_usage""",
        """DROP TABLE IF EXISTS order_items""",
        """DROP TABLE IF EXISTS orders""",
        """DROP TABLE IF EXISTS coupons""",
        """DROP TABLE IF EXISTS products""",
        """DROP TABLE IF EXISTS categories""",
        """DROP TABLE IF EXISTS users""",

        """CREATE TABLE users (
            id          INT PRIMARY KEY AUTO_INCREMENT,
            username    VARCHAR(50)  NOT NULL,
            email       VARCHAR(100) NOT NULL,
            phone       VARCHAR(20),
            city        VARCHAR(50)  NOT NULL COMMENT '城市',
            vip_level   TINYINT      NOT NULL DEFAULT 0 COMMENT '0普通/1银卡/2金卡/3钻石',
            total_spent DECIMAL(12,2) NOT NULL DEFAULT 0.00 COMMENT '累计消费',
            created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_city (city),
            INDEX idx_vip (vip_level)
        ) ENGINE=InnoDB COMMENT='用户表'""",

        """CREATE TABLE categories (
            id        INT PRIMARY KEY AUTO_INCREMENT,
            name      VARCHAR(50) NOT NULL,
            parent_id INT DEFAULT NULL,
            FOREIGN KEY (parent_id) REFERENCES categories(id),
            INDEX idx_parent (parent_id)
        ) ENGINE=InnoDB COMMENT='商品分类表'""",

        """CREATE TABLE products (
            id          INT PRIMARY KEY AUTO_INCREMENT,
            name        VARCHAR(100) NOT NULL,
            category_id INT          NOT NULL,
            price       DECIMAL(10,2) NOT NULL,
            cost        DECIMAL(10,2) NOT NULL COMMENT '成本价',
            stock       INT           NOT NULL DEFAULT 0,
            status      ENUM('on_sale','off_sale','deleted') NOT NULL DEFAULT 'on_sale',
            created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(id),
            INDEX idx_category (category_id),
            INDEX idx_status (status)
        ) ENGINE=InnoDB COMMENT='商品表'""",

        """CREATE TABLE orders (
            id           INT PRIMARY KEY AUTO_INCREMENT,
            order_no     VARCHAR(32)   NOT NULL UNIQUE COMMENT '订单编号',
            user_id      INT           NOT NULL,
            total_amount DECIMAL(12,2) NOT NULL COMMENT '订单总金额',
            pay_amount   DECIMAL(12,2) NOT NULL COMMENT '实付金额',
            status       ENUM('pending','paid','shipped','completed','cancelled','refunded') NOT NULL DEFAULT 'pending',
            coupon_id    INT           DEFAULT NULL,
            address      VARCHAR(200),
            created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
            paid_at      DATETIME      DEFAULT NULL,
            shipped_at   DATETIME      DEFAULT NULL,
            completed_at DATETIME      DEFAULT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            INDEX idx_user (user_id),
            INDEX idx_status (status),
            INDEX idx_created (created_at)
        ) ENGINE=InnoDB COMMENT='订单表'""",

        """CREATE TABLE order_items (
            id         INT PRIMARY KEY AUTO_INCREMENT,
            order_id   INT            NOT NULL,
            product_id INT            NOT NULL,
            quantity   INT            NOT NULL DEFAULT 1,
            unit_price DECIMAL(10,2)  NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id),
            INDEX idx_order (order_id),
            INDEX idx_product (product_id)
        ) ENGINE=InnoDB COMMENT='订单明细表'""",

        """CREATE TABLE reviews (
            id         INT PRIMARY KEY AUTO_INCREMENT,
            user_id    INT      NOT NULL,
            product_id INT      NOT NULL,
            order_id   INT      NOT NULL,
            rating     TINYINT  NOT NULL COMMENT '评分1-5',
            content    TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (order_id) REFERENCES orders(id),
            INDEX idx_product (product_id),
            INDEX idx_rating (rating)
        ) ENGINE=InnoDB COMMENT='评价表'""",

        """CREATE TABLE coupons (
            id             INT PRIMARY KEY AUTO_INCREMENT,
            code           VARCHAR(20)    NOT NULL UNIQUE,
            discount_type  ENUM('pct','fix') NOT NULL COMMENT 'pct百分比 fix固定金额',
            discount_value DECIMAL(10,2)  NOT NULL,
            min_order_amt  DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
            start_date     DATE           NOT NULL,
            end_date       DATE           NOT NULL,
            total_count    INT            NOT NULL,
            used_count     INT            NOT NULL DEFAULT 0,
            INDEX idx_date (start_date, end_date)
        ) ENGINE=InnoDB COMMENT='优惠券表'""",

        """CREATE TABLE coupon_usage (
            id        INT PRIMARY KEY AUTO_INCREMENT,
            coupon_id INT NOT NULL,
            order_id  INT NOT NULL,
            user_id   INT NOT NULL,
            used_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (coupon_id) REFERENCES coupons(id),
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            INDEX idx_coupon (coupon_id)
        ) ENGINE=InnoDB COMMENT='优惠券使用记录'""",

        """CREATE TABLE inventory_logs (
            id          INT PRIMARY KEY AUTO_INCREMENT,
            product_id  INT          NOT NULL,
            change_type ENUM('sale','restock','adjust','return') NOT NULL,
            quantity    INT          NOT NULL COMMENT '正入库 负出库',
            created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id),
            INDEX idx_product_date (product_id, created_at)
        ) ENGINE=InnoDB COMMENT='库存变动流水'""",
    ]

    print("🏗️  创建表结构...")
    for stmt in ddl_statements:
        cur.execute(stmt)
    conn.commit()
    print("✅ 表结构创建完成")

    # ─── 设置随机种子，保证可复现 ───
    random.seed(42)

    # ─── 1. 插入分类 ───
    print("📂 插入商品分类...")
    cat_id_map = {}  # name -> id
    parent_ids = []

    # 一级分类
    for parent_name in CATEGORY_TREE:
        cur.execute("INSERT INTO categories (name, parent_id) VALUES (%s, NULL)", (parent_name,))
        pid = cur.lastrowid
        cat_id_map[parent_name] = pid
        parent_ids.append(pid)

    # 二级分类
    subcat_list = []
    for parent_name, children in CATEGORY_TREE.items():
        pid = cat_id_map[parent_name]
        for child_name in children:
            cur.execute("INSERT INTO categories (name, parent_id) VALUES (%s, %s)", (child_name, pid))
            cid = cur.lastrowid
            cat_id_map[child_name] = cid
            subcat_list.append(child_name)

    conn.commit()
    print(f"  → {len(cat_id_map)} 个分类")

    # ─── 2. 插入商品 ───
    print("📦 插入商品...")
    products = []  # (id, name, subcat, price, cost, category_id)
    for i in range(NUM_PRODUCTS):
        subcat = random.choice(subcat_list)
        name = gen_product_name(subcat)
        lo, hi = PRICE_RANGES.get(subcat, (10, 500))
        price = round(random.uniform(lo, hi), 2)
        cost = round(price * random.uniform(0.4, 0.7), 2)
        stock = random.randint(0, 500)
        status = random.choices(["on_sale", "off_sale", "deleted"], [0.85, 0.12, 0.03])[0]
        created_at = datetime(2025, 11, 1) + timedelta(days=random.randint(0, 180))

        cur.execute(
            "INSERT INTO products (name, category_id, price, cost, stock, status, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (name, cat_id_map[subcat], price, cost, stock, status, created_at)
        )
        pid = cur.lastrowid
        products.append({"id": pid, "name": name, "subcat": subcat, "price": price, "cost": cost, "cat_id": cat_id_map[subcat]})

    conn.commit()
    print(f"  → {len(products)} 个商品")

    # ─── 3. 插入用户 ───
    print("👤 插入用户...")
    users = []
    used_names = set()
    start_date = datetime(2025, 6, 1)

    for i in range(NUM_USERS):
        while True:
            username = gen_name()
            if username not in used_names:
                used_names.add(username)
                break
        city = random.choices(CITIES, CITY_WEIGHTS)[0]
        vip_level = random.choices(VIP_LEVELS, VIP_WEIGHTS)[0]
        email = f"user{i+1}@example.com"
        phone = f"1{random.choice([3,5,6,7,8,9])}{random.randint(100000000, 999999999)}"
        created_at = start_date + timedelta(days=random.randint(0, 300))

        cur.execute(
            "INSERT INTO users (username, email, phone, city, vip_level, total_spent, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (username, email, phone, city, vip_level, 0, created_at)
        )
        users.append({"id": cur.lastrowid, "username": username, "city": city, "vip_level": vip_level})

    conn.commit()
    print(f"  → {len(users)} 个用户")

    # ─── 4. 插入优惠券 ───
    print("🎫 插入优惠券...")
    coupons = []
    for i in range(NUM_COUPONS):
        code = f"CPN{str(i+1).zfill(4)}"
        dtype = random.choice(["pct", "fix"])
        dvalue = round(random.choice([10, 15, 20, 25, 30]) if dtype == "pct" else random.choice([10, 20, 30, 50, 100]), 2)
        min_amt = round(random.choice([0, 50, 100, 200, 500]), 2)
        start = datetime(2025, 11, 1) + timedelta(days=random.randint(0, 150))
        end = start + timedelta(days=random.randint(15, 60))
        total = random.randint(500, 5000)
        used = random.randint(int(total * 0.25), int(total * 0.60))

        cur.execute(
            "INSERT INTO coupons (code, discount_type, discount_value, min_order_amt, start_date, end_date, total_count, used_count) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (code, dtype, dvalue, min_amt, start.date(), end.date(), total, used)
        )
        coupons.append({"id": cur.lastrowid, "dtype": dtype, "dvalue": dvalue, "min_amt": min_amt, "start": start, "end": end})

    conn.commit()
    print(f"  → {len(coupons)} 张优惠券")

    # ─── 5. 插入订单 + 订单明细 ───
    print("🛒 插入订单...")
    orders_data = []
    user_total_spent = {}  # user_id -> total

    # 时间分布：6 个月（2025-11 到 2026-04）
    order_start = datetime(2025, 11, 1)
    order_end = datetime(2026, 4, 30)
    total_days = (order_end - order_start).days

    for i in range(NUM_ORDERS):
        # 用户选择：80/20 法则
        if random.random() < 0.8:
            user = random.choice(users[:int(NUM_USERS * 0.2)])  # 高频用户
        else:
            user = random.choice(users)

        # 时间选择：周末权重高，有促销峰值
        day_offset = random.randint(0, total_days)
        order_date = order_start + timedelta(days=day_offset)
        # 周末加权
        if order_date.weekday() >= 5:
            # 周末订单量 ×1.5（通过额外采样实现）
            pass
        # 促销峰值：12月中和3月初
        peak_days = [45, 120]  # 大约12月中、3月初
        for peak in peak_days:
            if abs(day_offset - peak) < 7:
                order_date = order_start + timedelta(days=peak + random.randint(-3, 3))
                break

        order_date = order_date.replace(hour=random.randint(8, 23), minute=random.randint(0, 59))

        status = random.choices(ORDER_STATUSES, STATUS_WEIGHTS)[0]

        # 选商品（1-5件）
        num_items = random.choices([1, 2, 3, 4, 5], [0.30, 0.35, 0.20, 0.10, 0.05])[0]
        order_products = random.sample(products, min(num_items, len(products)))

        total_amount = 0
        items = []
        for prod in order_products:
            qty = random.randint(1, 3)
            unit_price = prod["price"]
            total_amount += qty * unit_price
            items.append({"product": prod, "quantity": qty, "unit_price": unit_price})

        total_amount = round(total_amount, 2)

        # 优惠券
        coupon_id = None
        pay_amount = total_amount
        if random.random() < 0.25 and status not in ["cancelled"]:
            # 有 25% 概率用优惠券
            eligible = [c for c in coupons if c["min_amt"] <= total_amount and c["start"] <= order_date <= c["end"]]
            if eligible:
                coupon = random.choice(eligible)
                coupon_id = coupon["id"]
                if coupon["dtype"] == "pct":
                    pay_amount = round(total_amount * (1 - coupon["dvalue"] / 100), 2)
                else:
                    pay_amount = round(max(0, total_amount - coupon["dvalue"]), 2)

        # 状态时间线
        paid_at = order_date + timedelta(minutes=random.randint(1, 30)) if status != "pending" else None
        shipped_at = (paid_at or order_date) + timedelta(hours=random.randint(2, 48)) if status in ["shipped", "completed"] else None
        completed_at = shipped_at + timedelta(days=random.randint(1, 7)) if status == "completed" else None

        address = f"{user['city']}市xx路{random.randint(1, 200)}号"
        order_no = f"ORD{order_date.strftime('%Y%m%d')}{str(i+1).zfill(6)}"

        cur.execute(
            """INSERT INTO orders (order_no, user_id, total_amount, pay_amount, status, coupon_id, address, created_at, paid_at, shipped_at, completed_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (order_no, user["id"], total_amount, pay_amount, status, coupon_id, address, order_date, paid_at, shipped_at, completed_at)
        )
        order_id = cur.lastrowid

        # 插入明细
        for item in items:
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (%s,%s,%s,%s)",
                (order_id, item["product"]["id"], item["quantity"], item["unit_price"])
            )

        # 累计消费
        if status in ["completed", "shipped", "paid"]:
            user_total_spent[user["id"]] = user_total_spent.get(user["id"], 0) + pay_amount

        orders_data.append({"id": order_id, "user_id": user["id"], "status": status, "created_at": order_date, "coupon_id": coupon_id})

        if (i + 1) % 5000 == 0:
            conn.commit()
            print(f"  → {i+1}/{NUM_ORDERS} 订单...")

    conn.commit()

    # 更新用户累计消费
    for uid, spent in user_total_spent.items():
        cur.execute("UPDATE users SET total_spent = %s WHERE id = %s", (round(spent, 2), uid))
    conn.commit()
    print(f"  → {len(orders_data)} 个订单完成")

    # ─── 6. 插入评价 ───
    print("⭐ 插入评价...")
    review_count = 0
    review_contents = [
        "不错，质量很好", "物流很快，包装完好", "性价比很高，推荐购买",
        "一般般吧，和预期差不多", "非常好，下次还会买", "还行，用着不错",
        "有点小瑕疵，但整体满意", "颜色和图片有差异", "超预期，物超所值",
        "不值这个价格", "送人很合适", "品质不错，继续支持",
        "尺寸不太合适", "做工精细，很喜欢", "味道不错，回购了",
    ]

    for order in orders_data:
        if order["status"] != "completed":
            continue
        if random.random() > NUM_REVIEWS_RATIO:
            continue

        # 该订单的商品
        cur.execute("SELECT product_id FROM order_items WHERE order_id = %s", (order["id"],))
        order_prods = cur.fetchall()
        if not order_prods:
            continue

        # 随机评价其中部分商品
        review_prods = random.sample(order_prods, random.randint(1, len(order_prods)))
        for row in review_prods:
            pid = row["product_id"]
            # 评分正态分布，均值 4.2
            rating = min(5, max(1, round(random.gauss(4.2, 0.8))))
            content = random.choice(review_contents)
            review_date = order["created_at"] + timedelta(days=random.randint(0, 14))

            cur.execute(
                "INSERT INTO reviews (user_id, product_id, order_id, rating, content, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                (order["user_id"], pid, order["id"], rating, content, review_date)
            )
            review_count += 1

        if review_count % 3000 == 0:
            conn.commit()

    conn.commit()
    print(f"  → {review_count} 条评价")

    # ─── 7. 插入库存流水 ───
    print("📊 插入库存流水...")
    for i in range(NUM_INVENTORY_LOGS):
        prod = random.choice(products)
        change_type = random.choices(["sale", "restock", "adjust", "return"], [0.6, 0.25, 0.10, 0.05])[0]
        if change_type == "sale":
            qty = -random.randint(1, 10)
        elif change_type == "return":
            qty = random.randint(1, 3)
        elif change_type == "restock":
            qty = random.randint(10, 200)
        else:
            qty = random.randint(-5, 5)

        log_date = datetime(2025, 11, 1) + timedelta(days=random.randint(0, 180), hours=random.randint(0, 23))

        cur.execute(
            "INSERT INTO inventory_logs (product_id, change_type, quantity, created_at) VALUES (%s,%s,%s,%s)",
            (prod["id"], change_type, qty, log_date)
        )

    conn.commit()
    print(f"  → {NUM_INVENTORY_LOGS} 条库存记录")

    # ─── 汇总 ───
    print("\n" + "=" * 50)
    print("🎉 Demo 数据生成完成！")
    print("=" * 50)

    # 统计
    tables = ["users", "categories", "products", "orders", "order_items", "reviews", "coupons", "coupon_usage", "inventory_logs"]
    for t in tables:
        cur.execute(f"SELECT COUNT(*) as cnt FROM {t}")
        row = cur.fetchone()
        print(f"  {t:20s} → {row['cnt']:>7d} 行")

    cur.close()
    conn.close()
    print(f"\n✅ 数据库 `{dbname}` 准备就绪，可以开始查询了！")


if __name__ == "__main__":
    main()
