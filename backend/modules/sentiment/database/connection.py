"""
Sentiment module ka DB access — ab app ke SHARED pool se.

Pehle is file mein apna `create_engine(...)` tha: usi DATABASE_URL par ek
DOOSRA connection pool (pool_size=10, max_overflow=20). Uske do nuqsan the:

  1. Supabase par connection budget dugna kharch hota tha, jabke asli queries
     `database.connection` wale pool se hi ja rahi thin (routes.py hamesha se
     wahan ka get_db import karti hai).
  2. Is pool mein `pool_pre_ping` aur TCP keepalives nahi the — wo settings
     main pool mein JAAN BOOJH KAR daali gayi hain taake Supabase ke stale SSL
     sockets par queries na girein. Yani jo bhi is file ko import karta, usay
     wo tahaffuz milta hi nahi.

Ab yahan koi engine nahi banta — sab kuch aage bhej diya jata hai, taake koi
bhi purana import khud-ba-khud shared (aur mehfooz) pool par aa jaye.
"""

from database.connection import Base, SessionLocal, engine, get_db

__all__ = ["Base", "SessionLocal", "engine", "get_db", "init_db"]


def init_db() -> None:
    """Saari tables banao — ab ye poore app ki tables hain, sirf sentiment ki nahi."""
    Base.metadata.create_all(bind=engine)
