from sqlalchemy import BigInteger, Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from database.connection import Base


class GeneratedVideoAd(Base):
    """
    Kling (fal.ai) se bana product video ad.

    JAAN BOOJH KAR `generated_ads` se ALAG table hai. Image ad ka row ek
    generation ka record hai jis mein headline/caption/hashtags hain; video ad
    ka row is se mukhtalif hai — is mein length plan, segment count, model id
    aur woh final prompt hai jo Kling ko gaya. Dono ko ek table mein thoosne se
    aadhe columns hamesha NULL rehte aur image ad ki chalti hui schema ko
    chhoona parta.
    """

    __tablename__ = "generated_video_ads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    brand_id = Column(Integer, index=True)

    # ---- Source image (Kling ka input) ----
    # "product"  -> scraped catalogue ka product image (default rasta)
    # "image_ad" -> pehle se bana hua image ad (generated_ads.id)
    source = Column(String, default="product")
    source_ad_id = Column(Integer, nullable=True)      # sirf source="image_ad" par
    source_image_url = Column(Text, nullable=True)     # jo URL/path Kling ko gaya

    product_name = Column(String, nullable=True)
    # BIGINT — wahi wajah jo models/ads_generated.py mein likhi hai: Shopify
    # ki ids 64-bit hain aur INTEGER par INSERT "integer out of range" deta hai.
    product_id = Column(BigInteger, nullable=True, index=True)
    # Historical only — rescrape par index shift ho jata hai (wahi wajah jo
    # models/ads_generated.py mein likhi hai).
    product_index = Column(Integer, nullable=True)

    # ---- Form ke jawabat (regenerate/debug ke liye mehfooz) ----
    ad_style = Column(String, nullable=True)
    scene = Column(String, nullable=True)
    mood = Column(String, nullable=True)
    camera_motion = Column(String, nullable=True)
    lighting = Column(String, nullable=True)
    pacing = Column(String, nullable=True)
    custom_prompt = Column(Text, nullable=True)
    # Prompt kahan se aaya: "form" | "ai" | "manual" (dekho schemas.PROMPT_SOURCES).
    # Bura video aane par pehla sawal yehi hota hai — prompt AI ne likha tha ya
    # user ne? custom_prompt akela ye nahi batata, kyunki AI ka draft user ke
    # apne likhe hue se bilkul ek jaisa dikhta hai.
    prompt_source = Column(String, nullable=True)

    # ---- Generation plan ----
    duration_seconds = Column(Integer)     # 10 | 15 | 20
    segments = Column(Integer)             # 1 | 2 | 3 (base + extensions)
    model_id = Column(String, nullable=True)
    # Kaun sa provider chala ("Kling" / "Veo") aur kis plan par. Dono record
    # karna zaroori hai: model_id se provider nikala ja sakta hai, lekin plan
    # nahi — aur jab asal billing aayegi to yehi purana data batayega ke kis
    # plan par kya bana tha.
    provider = Column(String, nullable=True)
    user_plan = Column(String, nullable=True)
    # Woh mukammal prompt jo pehle segment ke saath gaya (fixed layer samet).
    # Bill diya ja chuka hai, is liye "kya bheja tha" ka record rakhna zaroori
    # hai — bura result aane par dobara generate kiye baghair diagnose ho sake.
    final_prompt = Column(Text, nullable=True)

    video_path = Column(String)            # generated_ads/videos/xxx.mp4

    created_at = Column(DateTime, default=func.now())


# ── Additive Schema Migration ─────────────────
# create_all() maujooda table mein naye columns add nahi karta — is liye har
# naya column yahan bhi darj hota hai, warna woh sirf NAYE databases mein banta
# hai aur purane par query girti hai.
_ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "generated_video_ads": [
        # Veo add karte waqt aaye (multi-provider support).
        ("provider", "VARCHAR"),
        ("user_plan", "VARCHAR"),
        # "Write the prompt for me" add karte waqt aaya.
        ("prompt_source", "VARCHAR"),
    ],
}

# Ghalat (chhoti) type se ban chuke columns — ADD COLUMN inhe theek nahi karta.
# source_ad_id JAAN BOOJH KAR yahan NAHI hai: wo generated_ads.id (serial
# INTEGER) ko point karta hai, Shopify id ko nahi.
_WIDEN_COLUMNS: dict[str, list[tuple[str, str, str]]] = {
    "generated_video_ads": [
        ("product_id", "integer", "BIGINT"),
    ],
}


def ensure_video_ads_schema(engine) -> None:
    """generated_video_ads mein naye columns idempotently add karta hai."""
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

        # Type widening — idempotent.
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
