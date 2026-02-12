import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# 获取 backend 目录的绝对路径
BACKEND_DIR = Path(__file__).parent.parent.parent.resolve()

# 默认 SQLite，如果想换 PostgreSQL 或 MySQL，可以直接改 .env
DATABASE_URL = os.getenv("DATABASE_URL")

# 如果没有设置 DATABASE_URL，使用默认的 SQLite 路径（backend 目录下）
if not DATABASE_URL:
    db_path = BACKEND_DIR / "bili_note.db"
    # 使用 as_posix() 确保在 Windows 上也使用正斜杠，SQLite URL 需要正斜杠
    DATABASE_URL = f"sqlite:///{db_path.as_posix()}"
    print(f"[数据库] 使用默认 SQLite 数据库: {db_path}")

# SQLite 需要特定连接参数，其他数据库不需要
engine_args = {}
if DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true",
    **engine_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_engine():
    return engine


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()