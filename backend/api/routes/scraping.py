from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session, defer
from sqlalchemy import cast, String, text
from database.connection import get_db
from modules.scraping.verifier import (
    UnsafeUrlError,
    assert_safe_url,
    generate_verification_token,
    check_verification,
    verify_shopify_store,
)
from modules.scraping.scraper import scrape_website
from pydantic import BaseModel
from typing import Optional
import asyncio
import json
from datetime import datetime, timezone
from models.brand_profile import BrandProfile
from modules.llm_config import RateLimitedError
from modules.auth import get_current_user, require_owner, verify_access_token

router = APIRouter()


# ── Request Models ────────────────────────────
class VerifyRequest(BaseModel):
    website_url: str

class ScrapeRequest(BaseModel):
    website_url: str
    user_id: str

class VerifyCheckRequest(BaseModel):
    website_url: str
    token: str

class EditProfileRequest(BaseModel):
    business_name: Optional[str] = None
    description: Optional[str] = None
    target_audience: Optional[str] = None
    product_categories: Optional[list] = None
    business_type: Optional[str] = None
    social_links: Optional[dict] = None
    # User country correction — set hone par store_country_source "manual" ho
    # jata hai aur rescrape ise dobara overwrite nahi karta.
    store_country: Optional[str] = None


# ── Health Check ──────────────────────────────
@router.get("/health")
def health_check():
    return {"status": "Scraping module is running ✅"}


# ── Shopify Verify ────────────────────────────
@router.post("/verify-shopify")
def verify_shopify(request: VerifyRequest):
    """URL Shopify store hai ya nahi check karo"""
    try:
        is_shopify = verify_shopify_store(request.website_url)
    except UnsafeUrlError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not is_shopify:
        raise HTTPException(
            status_code=400,
            detail="This URL is not a Shopify store. BrandWave supports Shopify stores only."
        )
    return {"valid": True, "message": "Valid Shopify store detected!"}


# ── Token Generate ────────────────────────────
@router.post("/generate-token")
def generate_token(request: VerifyRequest):
    # URL yahan fetch nahi hota, sirf hash banta hai — magar validate phir bhi
    # karte hain taake user ko galat URL ka pata abhi chal jaye, verify step
    # par pahunch kar nahi.
    try:
        assert_safe_url(request.website_url)
    except UnsafeUrlError as e:
        raise HTTPException(status_code=400, detail=str(e))

    token = generate_verification_token(request.website_url)
    return {
        "token": token,
        "meta_tag": f'<meta name="brandwave-verify" content="{token}">',
        "instruction": "Add this meta tag inside your website <head> tag"
    }


# ── Verify Ownership ──────────────────────────
@router.post("/verify")
def verify_ownership(request: VerifyCheckRequest):
    try:
        is_verified = check_verification(request.website_url, request.token)
    except UnsafeUrlError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not is_verified:
        raise HTTPException(
            status_code=400,
            detail="Verification failed. Meta tag not found on website."
        )
    return {"verified": True, "message": "Website ownership verified!"}


# ── Scrape Website ────────────────────────────
@router.post("/scrape")
async def start_scraping(request: ScrapeRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        brand_profile = await scrape_website(
            website_url=request.website_url,
            user_id=caller,
            db=db
        )
        return {
            "success": True,
            "message": "Shopify store scraped successfully!",
            "data": brand_profile
        }
    except RateLimitedError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── WebSocket — Real-time Progress ───────────
@router.websocket("/scrape-progress/{user_id}")
async def scrape_with_progress(websocket: WebSocket, user_id: str, token: str | None = None, db: Session = Depends(get_db)):
    """WebSocket endpoint — real-time scraping progress.

    Browser WebSockets can't send Authorization headers, so the
    access token arrives as a query parameter (?token=...) and is
    verified before the connection is accepted.
    """
    if not token:
        await websocket.close(code=4001)
        return
    try:
        caller = verify_access_token(token)
        caller_id = caller.get("id")
        if caller_id != user_id:
            await websocket.close(code=4003)
            return
    except (PermissionError, RuntimeError):
        await websocket.close(code=4001)
        return

    await websocket.accept()

    try:
        # URL receive karo from frontend
        data = await websocket.receive_text()
        request_data = json.loads(data)
        website_url = request_data.get("website_url")

        if not website_url:
            await websocket.send_json({"error": "website_url is required"})
            await websocket.close()
            return

        # Progress callback
        async def send_progress(stage: str, percent: int):
            await websocket.send_json({
                "stage": stage,
                "percent": percent
            })

        # Scraping start karo
        result = await scrape_website(
            website_url=website_url,
            user_id=user_id,
            db=db,
            progress_callback=send_progress
        )

        # Final result bhejo
        await websocket.send_json({
            "stage": "Profile Ready",
            "percent": 100,
            "completed": True,
            "data": result
        })

    except Exception as e:
        # RateLimitedError ka str() already user-facing message hai. Flag se
        # frontend ise generic failure ke bajaye 'wait karo' ki tarah dikha sakta hai.
        await websocket.send_json({
            "error": str(e),
            "rate_limited": isinstance(e, RateLimitedError),
            "completed": False
        })
    finally:
        await websocket.close()


# ── List All Brands For A User ────────────────
@router.get("/my-brands/{user_id}")
def get_my_brands(user_id: str, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    User ke saare scraped brands — brand switcher ke liye.
    """
    require_owner(caller, user_id)
    # product_count Postgres mein compute hota hai — pehle poora products column
    # (5 brands = 2.22 MB) khinch kar Python mein len() kiya jata tha, jo 1,355 ms
    # legta tha. jsonb_array_length se sirf ek integer aata hai: ~267 ms, yani
    # Neon ke 240 ms round-trip floor ke barabar.
    rows = db.execute(text("""
        SELECT id, business_name, website_url, platform, logo_url, created_at,
               COALESCE(jsonb_array_length(products::jsonb), 0) AS product_count
        FROM brand_profiles
        WHERE user_id = :uid
        ORDER BY created_at DESC
    """), {"uid": user_id}).mappings().all()

    return {
        "success": True,
        "total": len(rows),
        "data": [
            {
                "id": r["id"],
                "business_name": r["business_name"],
                "website_url": r["website_url"],
                "platform": r["platform"],
                "logo_url": r["logo_url"],
                "product_count": r["product_count"],
                "created_at": str(r["created_at"]) if r["created_at"] else None,
            }
            for r in rows
        ],
    }


# ── Country List (override dropdown ke liye) ──
@router.get("/countries")
def list_countries():
    """
    Wo saare countries jo store_country ke tor par set ho sakte hain.

    Frontend dropdown yahin se bharti hai taake list backend ki
    ISO_COUNTRY_NAMES ke saath hamesha sync rahe — dono jagah alag alag
    hardcode karna dheere dheere diverge ho jata.
    """
    from modules.store_locale import ISO_COUNTRY_NAMES, UNKNOWN_COUNTRY

    countries = sorted(
        ({"iso": iso, "name": name} for iso, name in ISO_COUNTRY_NAMES.items()),
        key=lambda c: c["name"].replace("the ", "").lower(),
    )
    return {
        "success": True,
        "unknown_value": UNKNOWN_COUNTRY,
        "data": countries,
    }


# ── Get Brand Profile ─────────────────────────
@router.get("/profile/{user_id}")
def get_brand_profile(
    user_id: str,
    caller: str = Depends(get_current_user),
    url: str = None,
    offset: int = Query(0, ge=0, description="Products list mein kahan se shuru karna hai"),
    limit: int = Query(20, ge=1, le=100, description="Ek page mein kitne products (max 100)"),
    category: str | None = Query(None, description="Sirf is category ke products (chip filter)"),
    brand_profile_id: int | None = Query(None, description="Kaunsa brand — multi-brand accounts ke liye"),
    db: Session = Depends(get_db),
):
    """
    Brand profile deta hai — products PAGINATED hote hain.

    Pagination fix ke baad catalogs 7,000-10,000 products ke ho gaye hain
    (~5 MB JSON). Poori list har request par bhejna 3G par ~15s legta tha jab
    UI sirf 20 products dikhata hai. Ab sirf ek page jata hai; baaki profile
    fields har response mein poore aate hain.
    """
    require_owner(caller, user_id)
    # defer(products) — ye ek line hi "Next" button ki sust raftaari ki asli
    # wajah thi.
    #
    # `products` ek plain JSON column hai, yani ORM usay har SELECT mein saath
    # laata tha: 7,000 products = ~0.8 MB TOASTed (raw 9 MB) Neon se transfer
    # aur phir Python mein parse — HAR request par, chahe user ne sirf "Next"
    # daba kar 20 products maange hon. Aur wo poori list use bhi nahi hoti thi:
    # neeche _serialize_profile ka fast path page/count sab Postgres mein
    # nikalta hai (_products_page_sql).
    #
    # defer lazy hai, hataya nahi gaya — fallback path (limit=None, ya db=None
    # wale internal callers) `profile.products` chhoote hi usay load kar leta
    # hai, bilkul pehle ki tarah.
    query = (
        db.query(BrandProfile)
        .options(defer(BrandProfile.products))
        .filter(BrandProfile.user_id == user_id)
    )
    if brand_profile_id is not None:
        # Explicit brand — ownership filter upar lag chuka hai, to doosre user ka
        # profile kabhi return nahi hoga.
        query = query.filter(BrandProfile.id == brand_profile_id)
    elif url:
        query = query.filter(BrandProfile.website_url == url)
    profile = query.order_by(BrandProfile.created_at.desc()).first()

    if not profile:
        if brand_profile_id is not None:
            raise HTTPException(
                status_code=404,
                detail=f"Brand profile {brand_profile_id} not found for this account.",
            )
        raise HTTPException(status_code=404, detail="Brand profile not found")

    return _serialize_profile(profile, offset=offset, limit=limit, category=category, db=db)


@router.get("/products/{user_id}")
def get_brand_products(
    user_id: str,
    caller: str = Depends(get_current_user),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    category: str | None = Query(None, description="Sirf is category ke products"),
    brand_profile_id: int | None = Query(None),
    with_counts: bool = Query(False, description="category_counts bhi chahiye?"),
    db: Session = Depends(get_db),
):
    """
    Sirf products ka ek page — profile page ke pagination ("Next"/"Previous")
    ke liye.

    /profile/{user_id} poora brand profile deta hai: description, social links,
    markets, category counts, sab kuch. Page badalne par un mein se kuch bhi
    nahi badalta, lekin har click par wo sab dobara compute aur serialize hota
    tha. Ye endpoint sirf wahi bhejta hai jo asal mein badla hai — 20 products
    aur filtered total.
    """
    require_owner(caller, user_id)

    # Sirf id chahiye — poora row (jis mein products column hai) load karne ki
    # koi zaroorat nahi.
    q = db.query(BrandProfile.id).filter(BrandProfile.user_id == user_id)
    if brand_profile_id is not None:
        q = q.filter(BrandProfile.id == brand_profile_id)
    row = q.order_by(BrandProfile.created_at.desc()).first()
    if not row:
        raise HTTPException(status_code=404, detail="Brand profile not found")

    active_category = (category or "").strip() or None
    page, total_filtered, total_all, counts = _products_page_sql(
        db, row.id, offset, limit, active_category, with_counts=with_counts
    )

    return {
        "products": page,
        "total_products": total_filtered,
        "total_all_products": total_all,
        "category": active_category,
        "category_counts": counts,
        "offset": min(offset, total_filtered),
        "limit": limit,
    }


# ── Edit Brand Profile — FR5.4 ───────────────
@router.patch("/profile/{user_id}")
def edit_brand_profile(
    user_id: str,
    request: EditProfileRequest,
    caller: str = Depends(get_current_user),
    brand_profile_id: int | None = Query(None, description="Kaunsa brand edit karna hai"),
    db: Session = Depends(get_db),
):
    """User brand profile edit kar sake"""
    require_owner(caller, user_id)
    from models.brand_profile import BrandProfile
    from modules.store_locale import ISO_COUNTRY_NAMES, UNKNOWN_COUNTRY

    # brand_profile_id ke baghair ye .first() par gir jata tha — yani
    # multi-brand account par user Maria.B edit karta aur chup-chaap koi
    # doosra brand badal jata. Ownership filter dono soorton mein lagta hai.
    query = db.query(BrandProfile).filter(BrandProfile.user_id == user_id)
    if brand_profile_id is not None:
        query = query.filter(BrandProfile.id == brand_profile_id)
    profile = query.order_by(BrandProfile.created_at.desc()).first()

    if not profile:
        raise HTTPException(status_code=404, detail="Brand profile not found")

    update_data = request.model_dump(exclude_none=True)

    # ── Social links: validate + "manual" nishani ────────────────────────
    #
    # Nishani zaroori hai: save_brand_profile har rescrape par social_links
    # overwrite karta hai, to us ke baghair user ka bhara hua data agle
    # rescrape par chup-chaap ud jata (bilkul wahi masla jo store_country par
    # tha).
    if "social_links" in update_data:
        from modules.scraping.extractor import clean_social_links

        try:
            update_data["social_links"] = clean_social_links(update_data["social_links"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        profile.social_links_source = "manual"

    # Country correction ko validate karo — koi bhi free text qubool karna
    # matlab har prompt mein kachra chala jana.
    if "store_country" in update_data:
        value = (update_data["store_country"] or "").strip()
        valid = set(ISO_COUNTRY_NAMES.values()) | {UNKNOWN_COUNTRY}
        if value not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown country '{value}'. Use GET /api/scraping/countries for the list.",
            )
        update_data["store_country"] = value
        # Ye nishani rescrape ko batati hai ke is field ko haath nahi lagana.
        profile.store_country_source = "manual"

    for field, value in update_data.items():
        setattr(profile, field, value)

    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)

    return {
        "success": True,
        "message": "Brand profile updated successfully!",
        "data": _serialize_profile(profile)
    }


# ── Re-scrape Website — FR5.5 ────────────────
@router.post("/rescrape")
async def rescrape_website(request: ScrapeRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        brand_profile = await scrape_website(
            website_url=request.website_url,
            user_id=caller,
            db=db
        )
        return {
            "success": True,
            "message": "Shopify store re-scraped successfully!",
            "data": brand_profile
        }
    except RateLimitedError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Confirm & Save — FR5.6 ───────────────────
@router.post("/confirm/{user_id}")
def confirm_profile(
    user_id: str,
    caller: str = Depends(get_current_user),
    brand_profile_id: int | None = Query(
        None, description="Kaunsa brand confirm karna hai — multi-brand accounts ke liye"
    ),
    db: Session = Depends(get_db),
):
    """
    User profile confirm kare — is_verified = True

    brand_profile_id ab lazmi hai jab account par ek se zyada brand hon.
    Pehle ye bina ORDER BY ke `.first()` karta tha, yani multi-brand account
    par KOI BHI brand confirm ho jata tha — user Asim Jofa ka profile dekh
    raha hota aur verify kisi aur brand par lag jata. Baaqi har route
    (SEO, dashboard, ads) ye multi-brand fix pehle hi le chuki thi; sirf
    ye ek reh gayi thi.
    """
    require_owner(caller, user_id)
    from models.brand_profile import BrandProfile

    if brand_profile_id is not None:
        profile = db.query(BrandProfile).filter(
            BrandProfile.id == brand_profile_id,
            BrandProfile.user_id == user_id,     # ownership
        ).first()
        if not profile:
            raise HTTPException(
                status_code=404,
                detail=f"Brand profile {brand_profile_id} not found for this account.",
            )
    else:
        owned = db.query(BrandProfile).filter(
            BrandProfile.user_id == user_id
        ).order_by(BrandProfile.created_at.desc()).all()

        if not owned:
            raise HTTPException(status_code=404, detail="Brand profile not found")

        # Guess karne se saaf error behtar hai — wahi usool jo seo.py mein hai.
        if len(owned) > 1:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"This account has {len(owned)} brands. "
                    "Specify brand_profile_id — the server will not guess which brand you meant."
                ),
            )
        profile = owned[0]

    profile.is_verified = True
    db.commit()

    return {
        "success": True,
        "message": "Brand profile confirmed and saved to knowledge base!",
        "profile_id": profile.id
    }


# ── Helper ────────────────────────────────────
# Har product ki category detect_product_category() se aati hai, jo hamesha
# PRODUCT_CATEGORIES mein se ek value ya "other" deti hai. Defensive taur par
# null/khali ko bhi "other" mein daalte hain — taake koi product filter ke
# through invisible na ho jaye.
UNCATEGORISED = "other"


def _product_category(product: dict) -> str:
    return (product.get("category") or "").strip() or UNCATEGORISED


def _products_page_sql(
    db: Session,
    profile_id: int,
    offset: int,
    limit: int,
    category: str | None,
    with_counts: bool = True,
):
    """
    Products ka ek page, filtered total, aur category counts — sab Postgres mein.

    Pehle poora products column (7,157 products = 9 MB raw / 0.8 MB TOASTed)
    khinch kar Python mein slice hota tha. Ab sirf page wire par aata hai:
    0.80 MB -> 15.7 KB, aur query 530 ms -> 264 ms (Neon floor 240 ms).

    with_counts=False -> category_counts aur total_all skip.
    Ye sirf pagination ("Next"/"Previous") ke liye hai: chips ke counts poore
    catalogue par bante hain aur page badalne se badalte NAHI, is liye har click
    par 7,000 rows par GROUP BY dobara chalana fazool tha. Un dono ki jagah
    None/{} aata hai — caller ke paas pehli load wali values pehle se hoti hain.
    """
    counts_sql = """
            COALESCE((
                SELECT jsonb_object_agg(cat, n)
                FROM (SELECT cat, count(*) AS n FROM elems GROUP BY cat) g
            ), '{}'::jsonb)                                    AS counts
    """ if with_counts else "NULL::jsonb AS counts"

    row = db.execute(text(f"""
        WITH elems AS (
            SELECT elem, ord,
                   COALESCE(NULLIF(TRIM(elem->>'category'), ''), 'other') AS cat
            FROM brand_profiles b,
                 LATERAL jsonb_array_elements(b.products::jsonb) WITH ORDINALITY AS t(elem, ord)
            WHERE b.id = :pid
        ),
        filtered AS (
            SELECT * FROM elems
            -- NOTE: `:cat::text` mat likhna — SQLAlchemy text() ka param parser
            -- `::` cast ko bind param samajh kar syntax error deta hai.
            WHERE CAST(:cat AS text) IS NULL OR cat = CAST(:cat AS text)
        )
        SELECT
            (SELECT count(*) FROM elems)                       AS total_all,
            (SELECT count(*) FROM filtered)                    AS total_filtered,
            COALESCE((
                SELECT jsonb_agg(elem ORDER BY ord)
                FROM (SELECT elem, ord FROM filtered ORDER BY ord
                      OFFSET :off LIMIT :lim) p
            ), '[]'::jsonb)                                    AS page,
            {counts_sql}
    """), {"pid": profile_id, "cat": category, "off": offset, "lim": limit}).mappings().first()

    # NOTE: f-string sirf `counts_sql` ke liye hai, jo is module ka apna literal
    # hai — koi user input yahan interpolate NAHI hota. Har value abhi bhi bind
    # param se jati hai.
    return row["page"], row["total_filtered"], row["total_all"], row["counts"]


def _serialize_profile(
    profile,
    offset: int = 0,
    limit: int | None = None,
    category: str | None = None,
    db: Session | None = None,
) -> dict:
    """
    limit=None -> saare products (internal use).
    warna sirf requested page, plus pagination metadata.

    category diya ho to sirf usi category ke products return hote hain aur
    total_products bhi FILTERED count hota hai (warna pagination toot jati).

    category_counts hamesha POORE catalogue se banti hai, current page ya
    filter se nahi — chips ko sahi totals chahiye.

    NOTE: counts asli products se aati hain, profile.product_categories se
    nahi. product_categories LLM se aati hai aur usme aisi categories hoti
    hain jinka koi product hi nahi (real data mein 9 mein se 6 profiles par
    "accessories"/"footwear" ghost the) — un se chips banate to (0) dikhta.
    """
    active_category = (category or "").strip() or None

    if db is not None and limit is not None:
        # Fast path — slice/count/aggregate sab Postgres karta hai
        page_products, total_products, total_all, category_counts = _products_page_sql(
            db, profile.id, offset, limit, active_category
        )
        page_offset = min(offset, total_products)
    else:
        # Fallback — poora column Python mein (internal callers / limit=None)
        all_products = profile.products or []
        total_all = len(all_products)

        category_counts = {}
        for prod in all_products:
            cat = _product_category(prod)
            category_counts[cat] = category_counts.get(cat, 0) + 1

        filtered = (
            [p for p in all_products if _product_category(p) == active_category]
            if active_category else all_products
        )
        total_products = len(filtered)

        if limit is None:
            page_products = filtered
            page_offset = 0
        else:
            page_offset = min(offset, total_products)
            page_products = filtered[page_offset:page_offset + limit]

    return {
        "id": profile.id,
        "business_name": profile.business_name,
        "description": profile.description,
        "logo_url": profile.logo_url,
        "brand_colors": profile.brand_colors,
        "social_links": profile.social_links,
        # UI ko batata hai ke ye links khud nikle the ya user ne bhare —
        # aur us hisaab se "rescrape inhe nahi badlega" wali baat dikhati hai.
        "social_links_source": profile.social_links_source or "auto",
        "contact_email": profile.contact_email,
        "contact_phone": profile.contact_phone,
        "target_audience": profile.target_audience,
        "website_url": profile.website_url,
        "platform": profile.platform,
        "is_verified": profile.is_verified,
        "product_categories": profile.product_categories,
        "business_type": profile.business_type,
        "price_range": profile.price_range,
        # Market — profile page yahi dikhata hai, aur har LLM prompt ka
        # location context isi par chalta hai.
        "store_country": profile.store_country,
        "store_currency": profile.store_currency,
        "store_currencies": profile.store_currencies,
        "store_markets": profile.store_markets,
        "store_ships_worldwide": bool(profile.store_ships_worldwide),
        "store_country_source": profile.store_country_source or "auto",
        "products": page_products,
        # total_products = current filter ke hisaab se count (pagination isi par chalti hai)
        "total_products": total_products,
        # poora catalogue, filter se azad — "All" chip ke liye
        "total_all_products": total_all,
        "category": active_category,
        "category_counts": category_counts,
        "offset": page_offset,
        "limit": limit if limit is not None else total_products,
        "created_at": str(profile.created_at) if profile.created_at else None,
        "updated_at": str(profile.updated_at) if profile.updated_at else None,
    }