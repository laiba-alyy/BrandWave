import logging

from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database.connection import get_db
from models.brand_profile import BrandProfile
from models.ads_generated import GeneratedAd
from modules.ads_generation.image_polish import add_text_overlay

from modules.ads_generation.schemas import (
    GenerateImageAdRequest, GenerateImageAdResponse,
    GenerateVideoAdRequest, GenerateVideoAdResponse,
    ProductOut, ProductListOut, BrandOut, GalleryItem, GalleryDetail,
    ASPECT_RATIO_MAP, GENERATION_MODES
)
from modules.ads_generation.prompt_builder import build_copy_prompt_context
from modules.ads_generation.groq_service import generate_ad_copy
from modules.ads_generation.video_service import generate_video_ad

# Base image ab compositing providers banate hain — Bria (scene) ya Claid
# (on_model). Dono product ke asal pixels rakhte hain.
#
# openai_service (gpt-image-1) JAAN BOOJH KAR file mein maujood hai lekin ab
# route nahi hota: woh product ko repaint karta tha (shape/rang/kapra badal
# jate the), jo is module ke liye qabil-e-qubool nahi. Bria/Claid ke end-to-end
# confirm hone tak use delete nahi kar rahe.
from modules.ads_generation.services.common import (
    AdCreditsExhaustedError,
    AdImageServiceError,
)
from modules.ads_generation.input_guard import (
    InvalidAdInput, MAX_AD_TEXT, MAX_CTA, MAX_CUSTOM_PROMPT,
    clean_ad_text, clean_choice,
)
from modules.ads_generation.services.dispatch import generate_base_image
from modules.auth import get_current_user, require_owner

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Ads Generation"])


# ---------- 1. User ke saare brands ----------
@router.get("/my-brands/{user_id}", response_model=list[BrandOut])
def get_my_brands(user_id: str, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(caller, user_id)
    brands = db.query(BrandProfile).filter(BrandProfile.user_id == user_id).all()
    return [
        BrandOut(id=b.id, business_name=b.business_name, website_url=b.website_url)
        for b in brands
    ]
def _get_owned_brand(brand_id: int, user_id: str | None, db: Session) -> BrandProfile:
    """
    Brand fetch karta hai aur ownership verify karta hai.

    user_id diya ho to brand usi account ka hona chahiye — warna ek user
    doosre ka brand_id pass karke uske products dekh sakta tha.
    """
    q = db.query(BrandProfile).filter(BrandProfile.id == brand_id)
    if user_id:
        q = q.filter(BrandProfile.user_id == user_id)
    brand = q.first()
    if not brand:
        raise HTTPException(404, f"Brand {brand_id} not found for this account.")
    return brand


def _resolve_product(brand, product_id, product_index):
    """
    Ad ke liye product select karta hai.

    product_id authoritative hai. Pehle index se select hota tha, lekin rescrape
    par catalogue ka size badal jata hai (ab 1,000 se 7,000+), to purani tab ka
    stale index CHUP-CHAAP kisi doosre product ka ad bana deta tha. Ab id se
    lookup hota hai aur na milne par saaf 404 aata hai.

    Return: (product, index) — index sirf historical record ke liye.
    """
    products = brand.products or []
    catalogue_has_ids = any(p.get("id") is not None for p in products)

    if product_id is not None:
        for i, p in enumerate(products):
            if p.get("id") == product_id:
                return p, i
        if not catalogue_has_ids:
            raise HTTPException(
                409,
                "This brand profile was scraped before product IDs were stored. "
                "Please re-scrape the store, then generate the ad again.",
            )
        raise HTTPException(
            404,
            f"Product {product_id} no longer exists in this catalogue. "
            "It may have been removed since the last re-scrape — refresh the product list.",
        )

    if product_index is not None:
        # Legacy path — sirf un catalogues ke liye jinke paas ids hain hi nahi.
        if catalogue_has_ids:
            raise HTTPException(
                400,
                "This catalogue has product IDs — send product_id instead of product_index.",
            )
        try:
            return products[product_index], product_index
        except IndexError:
            raise HTTPException(404, "Invalid product index")

    raise HTTPException(400, "Either product_id or product_index is required")


# ---------- 3. Product search (NAYA) ----------
@router.get("/products/search", response_model=list[ProductOut])
def search_products(
    brand_id: int,
    query: str,
    caller: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    brand = _get_owned_brand(brand_id, caller, db)
    if not brand.products:
        return []

    query_words = [w.strip().lower() for w in query.split() if w.strip()]
    if not query_words:
        return []

    scored_results = []

    for i, p in enumerate(brand.products):
        name = (p.get("name") or "")
        category = p.get("category")
        # category kabhi list bhi ho sakti hai, safely string bana lo
        if isinstance(category, list):
            category = " ".join(str(c) for c in category)
        category = category or ""
        description = (p.get("description") or "")

        name_lower = name.lower()
        category_lower = category.lower()
        description_lower = description.lower()

        score = 0
        for word in query_words:
            word_singular = word.rstrip('s')
            # Name mein match = sabse zyada important (weight 3)
            if word in name_lower or word_singular in name_lower:
                score += 3
            # Category mein match = zyada important (weight 2)
            if word in category_lower or word_singular in category_lower:
                score += 2
            # Description mein match = kam important (weight 1)
            if word in description_lower or word_singular in description_lower:
                score += 1

        if score > 0:
            scored_results.append((score, ProductOut(
                id=p.get("id"), index=i, name=p.get("name"), price=p.get("price"),
                description=p.get("description"), image_url=p.get("image_url"),
                category=p.get("category") if isinstance(p.get("category"), str) else category,
            )))

    # Highest score pehle
    scored_results.sort(key=lambda x: x[0], reverse=True)

    return [item for score, item in scored_results[:30]]

# ---------- 2. Poori product list (already tha) ----------
@router.get("/products/{brand_id}", response_model=ProductListOut)
def get_products(
    brand_id: int,
    caller: str = Depends(get_current_user),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Brand ke products — PAGINATED. Pehle poori list jati thi, jo 7,157 products
    par 3.31 MB thi.
    """
    brand = _get_owned_brand(brand_id, caller, db)
    if not brand.products:
        raise HTTPException(404, "No products found for this brand")

    products = brand.products
    total = len(products)
    start = min(offset, total)
    page = products[start:start + limit]

    return ProductListOut(
        products=[
            ProductOut(
                id=p.get("id"), index=start + i, name=p.get("name"), price=p.get("price"),
                description=p.get("description"), image_url=p.get("image_url"),
                category=p.get("category"),
            )
            for i, p in enumerate(page)
        ],
        total_products=total,
        offset=start,
        limit=limit,
    )

# ---------- 4. Image Ad Generate Karna ----------
@router.post("/generate-image", response_model=GenerateImageAdResponse)
def generate_image_ad(payload: GenerateImageAdRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    # generate par user_id hamesha aata hai — ownership yahan strictly enforce hoti hai
    brand = _get_owned_brand(payload.brand_id, caller, db)
    if not brand.products:
        raise HTTPException(404, "Brand or products not found")

    product, product_index = _resolve_product(brand, payload.product_id, payload.product_index)

    if payload.generation_mode not in GENERATION_MODES:
        raise HTTPException(
            400,
            f"Unknown generation mode '{payload.generation_mode}'. "
            f"Choose one of: {', '.join(GENERATION_MODES)}.",
        )

    width, height = ASPECT_RATIO_MAP.get(payload.aspect_ratio, (1024, 1024))

    # ── User ka har lafz yahan se saaf ho kar guzarta hai ─────────────────
    #
    # Ye SAB SE PEHLE hota hai — provider ko call karne se, aur credit kharch
    # karne se pehle. Pehle ek 50,000-harf ka prompt seedha Bria ko jata tha:
    # request 200 second latakti aur phir provider ka cryptic 400 aata, jabke
    # credit kharch ho chuka hota.
    #
    # InvalidAdInput -> 400 (user ki ghalti, wo theek kar sakta hai), 500 nahi.
    try:
        custom_prompt = clean_ad_text(
            payload.custom_prompt, max_len=MAX_CUSTOM_PROMPT, field="Custom prompt")
        ad_text = clean_ad_text(payload.ad_text, max_len=MAX_AD_TEXT, field="Ad text")
        ad_cta = clean_ad_text(payload.ad_cta, max_len=MAX_CTA, field="Button text")
        platform = clean_choice(payload.platform, field="platform")
        cta_goal = clean_choice(payload.cta_goal, field="CTA goal")
        mood = clean_choice(payload.mood, field="mood")
        occasion = clean_choice(payload.occasion, field="occasion")
    except InvalidAdInput as e:
        raise HTTPException(400, e.message)

    form_data = {
        "platform": platform,
        "cta_goal": cta_goal,
        "mood": mood,
        "occasion": occasion,
        "custom_prompt": custom_prompt,
    }

    # 1. Groq se ad copy (real product description se, form context ke saath)
    #
    # Ye call NAKAM ho sakti hai aur pehle poori request ko 500 kar deti thi:
    #   * Groq rate limit  -> RateLimitedError
    #   * model ka jawab   -> json.loads() par JSONDecodeError
    # Dono soorton mein image ban hi nahi paati thi, halanke image copy par
    # depend NAHI karti. Ab copy ki nakami sirf copy ko degrade karti hai:
    # headline product ke naam se, CTA form se. Aur agar user ne apna ad_text
    # diya hai to us par koi farq parta hi nahi.
    fallback_copy = {
        "headline": product.get("name", "") or (brand.business_name or "New arrival"),
        "cta": cta_goal or "Shop Now",
        "caption": "",
        "hashtags": [],
        "discount_text": None,
    }
    try:
        copy_context = build_copy_prompt_context(product, form_data, brand)
        ad_copy = generate_ad_copy(copy_context)
        if not isinstance(ad_copy, dict):
            raise ValueError(f"ad copy was {type(ad_copy).__name__}, not a dict")
    except Exception as e:
        logger.warning(
            "[ads] ad copy failed (brand=%s, product=%s) — using product name "
            "as the headline instead: %s: %s",
            payload.brand_id, product.get("id"), type(e).__name__, e,
        )
        ad_copy = fallback_copy

    # LLM ka jawab dict to hai, magar uske andar ki shakl ki koi zamanat nahi.
    # `hashtags` string bhi aa sakti hai ya numbers ki list — dono soorton mein
    # neeche ",".join(...) TypeError deta tha, yani 500 US WAQT jab image ban
    # chuki thi aur credit kharch ho chuka tha.
    _raw_tags = ad_copy.get("hashtags")
    if isinstance(_raw_tags, str):
        _raw_tags = [_raw_tags]
    ad_copy["hashtags"] = [str(t).strip() for t in (_raw_tags or []) if str(t).strip()][:12]
    for _k in ("headline", "cta", "caption", "discount_text"):
        if ad_copy.get(_k) is not None and not isinstance(ad_copy[_k], str):
            ad_copy[_k] = str(ad_copy[_k])

    # 2. Base image — chune hue mode ka provider. Product ki asal photo hi
    #    input hai aur provider use badalta nahi, sirf scene/model banata hai.
    try:
        ad_image_path = generate_base_image(
            payload.generation_mode, product, form_data, brand, width, height
        )
    except AdCreditsExhaustedError as e:
        # 402 alag se: "dobara koshish karein" is soorat mein jhoot hai, aur
        # UI is code par apna "out of credits" panel dikhati hai.
        logger.error(
            "Image credits exhausted (provider=%s, brand=%s): %s",
            e.provider, payload.brand_id, e.detail,
        )
        raise HTTPException(402, e.message)
    except AdImageServiceError as e:
        # Raw provider response SIRF log mein — response mein kabhi nahi.
        logger.error(
            "Base image failed (mode=%s, provider=%s, brand=%s, product=%s): %s",
            payload.generation_mode, e.provider, payload.brand_id,
            product.get("id"), e.detail,
        )
        raise HTTPException(502, e.message)

    # 3. Pillow se crisp text overlay.
    #
    # User ka apna text AI ke headline par foqiyat rakhta hai — agar usne
    # likha hai ke image par kya likhna hai, to bilkul wahi chhapta hai.
    headline_text = ad_text or ad_copy.get("headline", "")
    cta_button_text = ad_cta or ad_copy.get("cta") or cta_goal or "Shop Now"

    # Overlay ka fail hona poori ad ko zaya nahi karna chahiye — base image
    # ban chuki hai aur uska credit kharch ho chuka hai. Aisi soorat mein
    # bina text wali image hi save karte hain.
    try:
        ad_image_path = add_text_overlay(
            image_path=ad_image_path,
            headline=headline_text,
            cta_text=cta_button_text,
            discount_text=ad_copy.get("discount_text"),
        )
    except Exception as e:
        logger.error(
            "Text overlay failed (brand=%s, product=%s) — saving base image "
            "without text: %s: %s",
            payload.brand_id, product.get("id"), type(e).__name__, e,
        )

    # 4. DB mein save karo (gallery ke liye)
    new_ad = GeneratedAd(
        user_id=caller,
        brand_id=payload.brand_id,
        product_name=product.get("name", ""),
        # product_id authoritative hai; product_index sirf historical reference
        # ke liye rakha gaya hai (resolved index, request ka raw nahi).
        product_id=product.get("id"),
        product_index=product_index,
        aspect_ratio=payload.aspect_ratio,
        platform=platform,
        cta_goal=cta_goal,
        mood=mood,
        occasion=occasion,
        custom_prompt=custom_prompt,
        headline=headline_text or ad_copy.get("headline"),
        caption=ad_copy.get("caption"),
        hashtags=",".join(ad_copy.get("hashtags", [])),
        image_path=ad_image_path,
    )
    db.add(new_ad)
    db.commit()
    db.refresh(new_ad)

    return GenerateImageAdResponse(
        success=True,
        ad_id=new_ad.id,
        ad_image_url=ad_image_path,
        product_name=product.get("name", ""),
        headline=headline_text or ad_copy.get("headline", ""),
        caption=ad_copy.get("caption", ""),
        hashtags=ad_copy.get("hashtags", [])
    )


# ---------- 5. Video Ad Generate Karna (existing ad_id se) ----------
@router.post("/generate-video", response_model=GenerateVideoAdResponse)
def generate_video_ad_endpoint(payload: GenerateVideoAdRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    ad = db.query(GeneratedAd).filter(GeneratedAd.id == payload.ad_id).first()
    if not ad:
        raise HTTPException(404, "Ad not found")
    # Ownership: only the ad owner can generate a video from it
    if ad.user_id != caller:
        raise HTTPException(403, "You can only generate videos from your own ads.")

    video_path = generate_video_ad(image_path=ad.image_path, product_name=ad.product_name)

    ad.video_path = video_path
    db.commit()

    return GenerateVideoAdResponse(success=True, ad_video_url=video_path)


# ---------- 6. Gallery — User Ke Saare Generated Ads ----------
@router.get("/gallery/{user_id}", response_model=list[GalleryItem])
def get_gallery(user_id: str, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(caller, user_id)
    ads = (
        db.query(GeneratedAd)
        .filter(GeneratedAd.user_id == user_id)
        .order_by(desc(GeneratedAd.created_at))
        .all()
    )
    return [
        GalleryItem(
            ad_id=a.id, product_name=a.product_name,
            image_path=a.image_path, video_path=a.video_path,
            created_at=a.created_at.isoformat()
        )
        for a in ads
    ]


# ---------- 7. Ek Specific Ad Ki Poori Detail (View button ke liye) ----------
@router.get("/gallery/detail/{ad_id}", response_model=GalleryDetail)
def get_gallery_detail(ad_id: int, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    ad = db.query(GeneratedAd).filter(GeneratedAd.id == ad_id).first()
    if not ad:
        raise HTTPException(404, "Ad not found")
    if ad.user_id != caller:
        raise HTTPException(403, "You can only view your own ads.")

    return GalleryDetail(
        ad_id=ad.id, product_name=ad.product_name,
        image_path=ad.image_path, video_path=ad.video_path,
        headline=ad.headline, caption=ad.caption, hashtags=ad.hashtags,
        aspect_ratio=ad.aspect_ratio, platform=ad.platform, mood=ad.mood,
        created_at=ad.created_at.isoformat()
    )