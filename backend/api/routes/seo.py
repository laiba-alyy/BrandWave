from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import cast, String
from database.connection import get_db
from models.brand_profile import BrandProfile
from models.seo_result import SEOAuditResult, SEOBlogPost, SEOKeywordSuggestion
from modules.seo.seo_auditor import run_seo_audit
from modules.seo.seo_llm import generate_keyword_suggestions, generate_optimized_content
from modules.seo.dataforseo import DataForSEOError
from modules.seo.seo_blog import generate_blog_post, get_blog_history, get_blog_post, delete_blog_post, _serialize_blog
from modules.seo.seo_pdf import generate_audit_pdf, generate_blog_pdf
from modules.llm_config import RateLimitedError
from modules.auth import get_current_user, require_owner
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter()


# ── Request Models ────────────────────────────

# brand_profile_id har request par optional hai taake purane clients na toote.
# Diya ho to us brand par scope hota hai; na ho to most-recent fallback.
class AuditRequest(BaseModel):
    user_id: str
    brand_profile_id: Optional[int] = None

class KeywordRequest(BaseModel):
    user_id: str
    brand_profile_id: Optional[int] = None
    market: Optional[str] = None
    language: str = Field(default="en", pattern=r"^[a-zA-Z]{2}$")

class ContentRequest(BaseModel):
    user_id: str
    brand_profile_id: Optional[int] = None

class BlogRequest(BaseModel):
    user_id: str
    topic: Optional[str] = None
    brand_profile_id: Optional[int] = None

class BlogDeleteRequest(BaseModel):
    user_id: str
    brand_profile_id: Optional[int] = None


# ── Helpers ───────────────────────────────────

def _get_brand_profile(
    user_id: str,
    db: Session,
    brand_profile_id: int | None = None,
) -> BrandProfile:
    """
    Brand profile resolve karta hai.

    brand_profile_id diya ho to WAHI profile milta hai (ownership verify karke).
    Ye multi-brand accounts ke liye zaroori hai: pehle ye function hamesha
    "most recent" profile uthata tha, is liye do stores wale user ko doosre
    brand ka SEO data dikh jata tha — bina kisi error ke.

    Id na ho to backward-compatible fallback: most recent profile.
    """
    if brand_profile_id is not None:
        profile = db.query(BrandProfile).filter(
            BrandProfile.id == brand_profile_id,
            BrandProfile.user_id == user_id,     # ownership — doosre user ka profile kabhi nahi
        ).first()
        if not profile:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Brand profile {brand_profile_id} not found for this account. "
                    "Pick a different brand from the switcher."
                ),
            )
        return profile

    owned = db.query(BrandProfile).filter(
        BrandProfile.user_id == user_id
    ).order_by(BrandProfile.created_at.desc()).all()

    if not owned:
        raise HTTPException(
            status_code=404,
            detail="Brand profile not found. Please complete web scraping first."
        )

    # Ek hi brand ho to fallback bilkul unambiguous hai.
    # Multiple brands hon aur caller ne id na bheji ho to GUESS karna wahi
    # purana bug hai (user ko doosre brand ka data dikhta tha). Ab guess ke
    # bajaye saaf error dete hain.
    if len(owned) > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                f"This account has {len(owned)} brands. "
                "Specify brand_profile_id — the server will not guess which brand you meant."
            ),
        )

    return owned[0]


def _get_audit_result(user_id: str, brand_profile_id: int, db: Session) -> SEOAuditResult:
    """Audit result fetch karo — most recent — 404 if not found"""
    result = db.query(SEOAuditResult).filter(
        SEOAuditResult.user_id == user_id,
        SEOAuditResult.brand_profile_id == brand_profile_id,
    ).order_by(SEOAuditResult.created_at.desc()).first()
    if not result:
        raise HTTPException(
            status_code=404,
            detail="SEO audit not found. Please run the audit first."
        )
    return result


def _serialize_audit(audit: SEOAuditResult) -> dict:
    return {
        "id": audit.id,
        "seo_score": audit.seo_score,
        "title_score": audit.title_score,
        "description_score": audit.description_score,
        "image_alt_score": audit.image_alt_score,
        # False = is store ki Shopify feed alt text deti hi nahi. UI ko 0/100
        # ke bajaye wajah dikhani chahiye, aur ye factor overall score mein
        # shamil nahi hota. Purane audits (column se pehle wale) ke liye None
        # aata hai — usay True samjho, purana behaviour.
        "image_alt_measurable": (
            True if audit.image_alt_measurable is None else audit.image_alt_measurable
        ),
        "keyword_score": audit.keyword_score,
        "tags_score": audit.tags_score,
        "title_issues": audit.title_issues,
        "description_issues": audit.description_issues,
        "image_alt_issues": audit.image_alt_issues,
        "keyword_issues": audit.keyword_issues,
        "tags_issues": audit.tags_issues,
        "total_products_audited": audit.total_products_audited,
        "total_catalogue_products": audit.total_catalogue_products,
        "good_count": audit.good_count,
        "warning_count": audit.warning_count,
        "needs_work_count": audit.needs_work_count,
        "ai_recommendations": audit.ai_recommendations,
        "suggested_keywords": audit.suggested_keywords,
        "created_at": str(audit.created_at) if audit.created_at else None,
        "updated_at": str(audit.updated_at) if audit.updated_at else None,
    }


# ── Health Check ──────────────────────────────

@router.get("/health")
def health_check():
    return {"status": "SEO module is running ✅"}


# ── Step 1: Generate Keywords ─────────────────

@router.post("/keywords/generate")
def generate_keywords(request: KeywordRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    LLM se target keywords generate karo.
    Audit se pehle keywords generate karna zaroori hai.
    """
    try:
        profile = _get_brand_profile(caller, db, request.brand_profile_id)
        suggestion = generate_keyword_suggestions(profile, db, request.market, request.language)
        return {
            "success": True,
            "message": f"Generated {len(suggestion.keywords)} keywords",
            "data": {
                "id": suggestion.id,
                "keywords": suggestion.keywords,
                "created_at": str(suggestion.created_at) if suggestion.created_at else None,
            }
        }
    except HTTPException:
        raise
    # Rate limit ko 500 mein badalne na do - main.py ka handler ise 429 banata hai
    except RateLimitedError:
        raise
    except DataForSEOError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/keywords/{user_id}")
def get_keywords(user_id: str, caller: str = Depends(get_current_user), brand_profile_id: int | None = Query(None), db: Session = Depends(get_db)):
    """Get saved keyword suggestions"""
    require_owner(caller, user_id)
    profile = _get_brand_profile(user_id, db, brand_profile_id)
    suggestion = db.query(SEOKeywordSuggestion).filter(
        SEOKeywordSuggestion.user_id == user_id,
        SEOKeywordSuggestion.brand_profile_id == profile.id,
    ).first()

    if not suggestion:
        raise HTTPException(
            status_code=404,
            detail="No keywords found. Please generate keywords first."
        )

    return {
        "success": True,
        "data": {
            "id": suggestion.id,
            "keywords": suggestion.keywords,
            "created_at": str(suggestion.created_at) if suggestion.created_at else None,
        }
    }


# ── Step 2: Run SEO Audit ─────────────────────

@router.post("/audit/run")
def run_audit(request: AuditRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Full SEO audit run karo on scraped product data.
    Keywords generate karo pehle — agar nahi hain toh empty list use hogi.
    """
    try:
        profile = _get_brand_profile(caller, db, request.brand_profile_id)

        # Get keywords if available
        suggestion = db.query(SEOKeywordSuggestion).filter(
            SEOKeywordSuggestion.user_id == caller,
            SEOKeywordSuggestion.brand_profile_id == profile.id,
        ).first()

        keywords = []
        if suggestion and suggestion.keywords:
            keywords = [k["keyword"] for k in suggestion.keywords]

        audit_result = run_seo_audit(profile, keywords, db)

        return {
            "success": True,
            "message": (
                f"SEO audit completed for {audit_result.total_products_audited} "
                f"of {audit_result.total_catalogue_products} products"
            ),
            "data": _serialize_audit(audit_result)
        }
    except HTTPException:
        raise
    # Rate limit ko 500 mein badalne na do - main.py ka handler ise 429 banata hai
    except RateLimitedError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit/{user_id}")
def get_audit(user_id: str, caller: str = Depends(get_current_user), brand_profile_id: int | None = Query(None), db: Session = Depends(get_db)):
    """Get last saved audit result"""
    require_owner(caller, user_id)
    profile = _get_brand_profile(user_id, db, brand_profile_id)
    audit = _get_audit_result(user_id, profile.id, db)
    return {
        "success": True,
        "data": _serialize_audit(audit)
    }


# ── Step 3: Generate AI Content ───────────────

def _content_keywords(profile: BrandProfile, audit: SEOAuditResult, db: Session) -> list:
    """
    Content prompt ke liye keywords — pehle brand ke saved suggestions,
    warna audit ke suggested_keywords.
    """
    row = db.query(SEOKeywordSuggestion).filter(
        SEOKeywordSuggestion.brand_profile_id == profile.id,
        SEOKeywordSuggestion.user_id == profile.user_id,
    ).order_by(SEOKeywordSuggestion.id.desc()).first()
    if row and row.keywords:
        return row.keywords
    return audit.suggested_keywords or []


@router.post("/content/generate")
def generate_content(request: ContentRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    AI optimized meta titles and descriptions generate karo.
    Audit pehle run honi chahiye.
    """
    try:
        profile = _get_brand_profile(caller, db, request.brand_profile_id)
        audit = _get_audit_result(caller, profile.id, db)

        # Pehle yahan generate_optimized_content(profile, audit, db) tha, jo
        # signature (products, keywords, brand_name, store_country) se match
        # nahi karta tha — keywords[:10] ORM object par chalta tha aur har
        # request TypeError se 500 hoti thi. Is liye purana content kabhi
        # overwrite nahi hota tha.
        recommendations = generate_optimized_content(
            products=profile.products or [],
            keywords=_content_keywords(profile, audit, db),
            brand_name=profile.business_name or "",
            store_country=profile.store_country,
        )

        # Khali natija = LLM fail hui (truncation/parse error). Ise "success"
        # keh kar save karna do tarah se ghalat tha: user ka pehle ka mehfooz
        # content mit jata tha, aur UI "0 products" ke sath kamyabi dikhata tha.
        if not recommendations:
            raise HTTPException(
                status_code=503,
                detail="AI content generation failed. Please try again.",
            )

        # Save karna zaroori hai: UI mount par audit.ai_recommendations se
        # parhta hai. Save na karein to page reload par purana (stale) content
        # wapas dikhne lagta hai.
        audit.ai_recommendations = recommendations
        db.commit()

        return {
            "success": True,
            "message": f"Generated optimized content for {len(recommendations)} products",
            "data": recommendations
        }
    except HTTPException:
        raise
    # Rate limit ko 500 mein badalne na do - main.py ka handler ise 429 banata hai
    except RateLimitedError:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ── Blog Endpoints ────────────────────────────

@router.post("/blog/generate")
def create_blog(request: BlogRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    New SEO optimized blog article generate karo.
    Optional topic — agar nahi diya toh auto generate hoga.
    """
    try:
        profile = _get_brand_profile(caller, db, request.brand_profile_id)
        blog = generate_blog_post(profile, db, topic=request.topic)
        return {
            "success": True,
            "message": "Blog article generated successfully",
            "data": _serialize_blog(blog)
        }
    except HTTPException:
        raise
    # Rate limit ko 500 mein badalne na do - main.py ka handler ise 429 banata hai
    except RateLimitedError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/blog/history/{user_id}")
def get_blogs(user_id: str, caller: str = Depends(get_current_user), brand_profile_id: int | None = Query(None), db: Session = Depends(get_db)):
    """Get all generated blog posts for user"""
    require_owner(caller, user_id)
    profile = _get_brand_profile(user_id, db, brand_profile_id)
    blogs = get_blog_history(user_id, profile.id, db)
    return {
        "success": True,
        "total": len(blogs),
        "data": blogs
    }


@router.get("/blog/{blog_id}")
def get_single_blog(blog_id: int, caller: str = Depends(get_current_user), user_id: str = Query(...), brand_profile_id: int | None = Query(None), db: Session = Depends(get_db)):
    """Get single blog post by ID"""
    require_owner(caller, user_id)
    try:
        blog = get_blog_post(blog_id, user_id, db)
        return {
            "success": True,
            "data": _serialize_blog(blog)
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/blog/{blog_id}")
def remove_blog(blog_id: int, request: BlogDeleteRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete a blog post"""
    try:
        delete_blog_post(blog_id, caller, db)
        return {
            "success": True,
            "message": "Blog post deleted successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── PDF Export Endpoints ──────────────────────

@router.get("/audit/{user_id}/export/pdf")
def export_audit_pdf(user_id: str, caller: str = Depends(get_current_user), brand_profile_id: int | None = Query(None), db: Session = Depends(get_db)):
    """
    SEO audit report PDF download karo.
    AI content generate pehle karo for full report.
    """
    require_owner(caller, user_id)
    try:
        profile = _get_brand_profile(user_id, db, brand_profile_id)
        audit = _get_audit_result(user_id, profile.id, db)
        pdf_bytes = generate_audit_pdf(profile, audit)

        filename = f"seo_audit_{profile.business_name or 'report'}_{datetime.now().strftime('%Y%m%d')}.pdf"
        filename = filename.replace(" ", "_").lower()

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except HTTPException:
        raise
    # Rate limit ko 500 mein badalne na do - main.py ka handler ise 429 banata hai
    except RateLimitedError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/blog/{blog_id}/export/pdf")
def export_blog_pdf(blog_id: int, caller: str = Depends(get_current_user), user_id: str = Query(...), brand_profile_id: int | None = Query(None), db: Session = Depends(get_db)):
    """Blog post PDF download karo"""
    require_owner(caller, user_id)
    try:
        profile = _get_brand_profile(user_id, db, brand_profile_id)
        blog = get_blog_post(blog_id, user_id, db)
        pdf_bytes = generate_blog_pdf(profile, blog)

        filename = f"blog_{blog_id}_{datetime.now().strftime('%Y%m%d')}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except HTTPException:
        raise
    # Rate limit ko 500 mein badalne na do - main.py ka handler ise 429 banata hai
    except RateLimitedError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Missing import fix ────────────────────────
from datetime import datetime