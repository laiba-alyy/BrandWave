from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL: 
    raise RuntimeError("DATABASE_URL is not configured.")

engine_kwargs = {
    # Validate pooled connections before use to avoid stale SSL sockets.
    "pool_pre_ping": True,
    # Recycle periodically so long-lived SSL connections are refreshed.
    "pool_recycle": int(os.getenv("DB_POOL_RECYCLE_SECONDS", "1800")),
    "pool_use_lifo": True,
}

try:
    backend_name = make_url(DATABASE_URL).get_backend_name()
except Exception:
    backend_name = ""

if backend_name in {"postgresql", "postgres"}:
    engine_kwargs["connect_args"] = {
        "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
        "keepalives": 1,
        "keepalives_idle": int(os.getenv("DB_KEEPALIVES_IDLE", "30")),
        "keepalives_interval": int(os.getenv("DB_KEEPALIVES_INTERVAL", "10")),
        "keepalives_count": int(os.getenv("DB_KEEPALIVES_COUNT", "5")),
    }

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()