"""数据库初始化 — 支持 SQLite / MySQL"""

import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ─── 数据库连接配置 ───────────────────────────────
# 优先读环境变量，fallback 到默认值
DB_TYPE = os.getenv("DB_TYPE", "mysql")  # "mysql" or "sqlite"

if DB_TYPE == "mysql":
    DB_HOST = os.getenv("DB_HOST", "172.26.32.1")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASS = os.getenv("DB_PASS", "Admin1234..")
    DB_NAME = os.getenv("DB_NAME", "knowledge_base")
    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
else:
    DB_PATH = Path(__file__).parent.parent.parent / "data" / "knowledge.db"
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI 依赖注入用"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有表"""
    from app.models.models import Base as ModelsBase  # noqa: F401
    Base.metadata.create_all(bind=engine)
