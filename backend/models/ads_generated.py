from sqlalchemy import BigInteger, Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from database.connection import Base


class GeneratedAd(Base):
    __tablename__ = "generated_ads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    brand_id = Column(Integer, index=True)
    product_name = Column(String)
    # Shopify product id — authoritative reference to the product this ad is for.
    #
    # BIGINT, INTEGER nahi. Shopify ki ids 64-bit hain (misal 9580762136811),
    # aur Postgres ka INTEGER sirf 2147483647 tak jata hai. Pehle ye INTEGER
    # tha, to har asli Shopify product par INSERT
    # `psycopg.errors.NumericValueOutOfRange: integer out of range` deta tha —
    # image ban chuki hoti, credit kharch ho chuka hota, aur request phir bhi
    # 500 ho jati thi.
    product_id = Column(BigInteger, nullable=True, index=True)
    # Position in the catalogue at generation time. Historical only: rescrape
    # catalogue ka size badal deta hai, to ye index baad mein reliable nahi rehta.
    product_index = Column(Integer, nullable=True)

    aspect_ratio = Column(String)          # "1080x1080", "1080x1920", etc.
    platform = Column(String, nullable=True)
    cta_goal = Column(String, nullable=True)
    mood = Column(String, nullable=True)
    occasion = Column(String, nullable=True)
    custom_prompt = Column(Text, nullable=True)

    headline = Column(String, nullable=True)
    caption = Column(Text, nullable=True)
    hashtags = Column(Text, nullable=True)   # comma-separated

    image_path = Column(String)             # generated_ads/images/xxx.png
    video_path = Column(String, nullable=True)

    created_at = Column(DateTime, default=func.now())

# ── Additive Schema Migration ─────────────────
_ADDED_COLUMNS = {
    "generated_ads": [
        ("product_id", "BIGINT"),
    ],
}

# Woh columns jo PEHLE ghalat (chhoti) type se ban chuke hain. ADD COLUMN
# purane database ko theek nahi karta — us ke liye ALTER TYPE chahiye.
_WIDEN_COLUMNS = {
    "generated_ads": [
        ("product_id", "integer", "BIGINT"),
    ],
}


def ensure_ads_schema(engine) -> None:
    """generated_ads mein naye columns idempotently add karta hai."""
    from sqlalchemy import inspect

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {col["name"] for col in inspector.get_columns(table)}
            for name, col_type in columns:
                if name in present:
                    continue
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")

        # Type widening — idempotent: sirf tab chalta hai jab column abhi bhi
        # purani type par ho.
        for table, columns in _WIDEN_COLUMNS.items():
            if table not in existing_tables:
                continue
            current = {col["name"]: str(col["type"]).lower()
                       for col in inspector.get_columns(table)}
            for name, old_type, new_type in columns:
                actual = current.get(name)
                if actual is None or old_type not in actual:
                    continue
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ALTER COLUMN {name} TYPE {new_type}"
                )
