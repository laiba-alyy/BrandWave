from sqlalchemy import Column, Integer, String, JSON, DateTime, Boolean, inspect, text
from sqlalchemy.sql import func
from database.connection import Base


class BrandProfile(Base):
    __tablename__ = "brand_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    website_url = Column(String, nullable=False)

    #  Core Brand Info 
    business_name = Column(String, nullable=True)
    description = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)
    brand_colors = Column(JSON, nullable=True)
    social_links = Column(JSON, nullable=True)

    #  Business Info 
    business_type = Column(String, nullable=True)
    product_categories = Column(JSON, nullable=True)
    price_range = Column(String, nullable=True)
    target_audience = Column(String, nullable=True)

    #  Market  —  har LLM prompt ka location context isi se banta hai
    # Scrape ke waqt modules/store_locale.py detect karta hai (Shopify
    # /meta.json -> currency -> ccTLD -> address). Detect na ho to
    # "international" save hota hai, KISI mulk par default nahi hota —
    # ghalat mulk batana "pata nahi" se zyada nuqsan-deh hai.
    store_country = Column(String, nullable=True)
    store_currency = Column(String, nullable=True)

    # Store jitni currencies leta hai, sab — ["PKR","AED","USD"].
    # store_currency inhi mein se pehli (primary) hai, back-compat ke liye.
    store_currencies = Column(JSON, nullable=True)

    # Jin markets ke liye content banana hai: [{"iso":"PK","name":"Pakistan"}, ...]
    # Home country hamesha pehla. Multi-market keyword allocation isi par chalti hai.
    store_markets = Column(JSON, nullable=True)

    # "auto" = detection ne set kiya, "manual" = user ne profile page se theek kiya.
    # manual hone par rescrape ise KABHI overwrite nahi karta — warna user ki
    # correction har rescrape par chup-chaap ud jati.
    store_country_source = Column(String, nullable=True, default="auto")

    # Wahi usool social links ke liye. Scraping har site par social links
    # theek nahi nikal pati (kuch stores unhe sirf JS widget mein rakhte hain,
    # aur kabhi fetch hi adhoora aata hai), is liye user unhe khud bhar sakta
    # hai — aur us ke baad rescrape unhe CHHUEGA NAHI. Is flag ke baghair
    # manual entry agle rescrape par chup-chaap mit jati.
    social_links_source = Column(String, nullable=True, default="auto")

    # Store se raabte ki tafseel. Aksar footer mein nahi hoti — contact page
    # se aati hai (dekho scraper.py ka contact-page fallback). Chatbot aur
    # brand improvement dono ko iski zaroorat parti hai.
    contact_email = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)

    # meta.json ke ships_to_countries mein "*" ho to store duniya bhar bhejta
    # hai. Ye keyword/blog prompts ko batata hai ke international buyers bhi
    # scope mein hain, chahe har mulk ka naam maloom na ho.
    store_ships_worldwide = Column(Boolean, nullable=True, default=False)

    #  Products 
    products = Column(JSON, nullable=True)

    #  Platform & Meta 
    platform = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


# ── Additive Schema Migration ─────────────────
# create_all() sirf missing TABLES banata hai — mojooda table mein naye columns
# add nahi karta. store_country/store_currency purani deployments mein missing
# hain, is liye unhe idempotently add karte hain (wahi pattern jo chatbot aur
# seo models mein hai).
_ADDED_COLUMNS = {
    "brand_profiles": [
        ("store_country", "VARCHAR"),
        ("store_currency", "VARCHAR"),
        ("store_currencies", "JSON"),
        ("store_markets", "JSON"),
        ("store_country_source", "VARCHAR"),
        ("store_ships_worldwide", "BOOLEAN"),
        ("social_links_source", "VARCHAR"),
        ("contact_email", "VARCHAR"),
        ("contact_phone", "VARCHAR"),
    ],
}


def ensure_brand_profile_schema(engine) -> None:
    """Market columns add karta hai agar wo abhi tak table mein nahi hain."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                # Table abhi bana hi nahi — create_all() ise poore schema ke saath banayega.
                continue
            present = {col["name"] for col in inspector.get_columns(table)}
            for name, col_type in columns:
                if name in present:
                    continue
                conn.exec_driver_sql("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, col_type))

        # Purane rows ka source set karo — warna wo NULL rehta hai aur
        # rescrape unhe "manual" samajh kar chhor sakta hai.
        if "brand_profiles" in existing_tables:
            conn.execute(text(
                "UPDATE brand_profiles SET store_country_source = 'auto' "
                "WHERE store_country_source IS NULL"
            ))
            conn.execute(text(
                "UPDATE brand_profiles SET social_links_source = 'auto' "
                "WHERE social_links_source IS NULL"
            ))
