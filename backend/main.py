# ── Console output stream — SAB SE PEHLE ────────────────────────────────
#
# (Is heading mein lafz "encoding" ke baad colon mat lagana: Python pehli
#  DO lines mein `coding:` dhoondta hai aur usay source encoding samajh kar
#  "SyntaxError: unknown encoding" de deta hai. PEP 263.)
#
# Windows par Python ka stdout cp1252 hota hai, aur is codebase mein darjano
# print() emoji use karte hain ("✅ Blog generated"). cp1252 un ko encode nahi
# kar sakta, to print() khud UnicodeEncodeError phenk deta hai.
#
# Ye sirf badsurat log ka masla nahi tha — seo_blog.py mein wo print try block
# ke ANDAR hai, is liye ek KAAMYAB blog generation exception ban kar
# "Failed to generate blog post: 'charmap' codec can't encode character" ke
# tor par user tak pahunchti thi. Article ban chuka hota tha, phir bhi.
#
# errors="replace" is liye ke encoding ka masla dobara kabhi FEATURE ko na
# giraye — hadd se hadd ek emoji "?" ban jayega.
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass    # already UTF-8, ya redirected stream jo reconfigure nahi hota

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.gzip import GZipMiddleware
from datetime import datetime
from dotenv import load_dotenv
import os
import logging
from api.routes import ai_assistant
from modules.llm_config import RateLimitedError, retry_status
from models import chat_history
from models import ads_generated
from models import video_ads_generated
from fastapi.staticfiles import StaticFiles
from api.routes.profile import router as profile_router

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== IMPORT ROUTES =====
from api.routes import auth as auth_routes
from api.routes import scraping
from api.routes import seo
from api.routes import ads_generation
from api.routes import video_ads
from api.routes import chatbot
from api.routes import brand_improvement
from api.routes import dashboard

# ===== IMPORT YOUR SENTIMENT ROUTES =====
try:
    from modules.sentiment.api.routes import router as sentiment_router
    logger.info("✅ Sentiment module loaded")
except ImportError as e:
    logger.warning(f"⚠️ Sentiment module not found: {e}")
    sentiment_router = None

# ===== IMPORT DATABASES & MODELS =====
from database.connection import Base, engine
from models import brand_profile          # noqa: F401 — import = table register
from models import seo_result             # noqa: F401
from models import chatbot as chatbot_models   # noqa: F401
from modules.sentiment.database import models as sentiment_models  # noqa: F401

# Ek create_all, saat nahi.
#
# Har model module `database.connection.Base` hi use karta hai (sentiment ab
# bhi — pehle uska apna alag Base tha). Table us waqt register hoti hai jab
# uska module IMPORT hota hai, create_all() par nahi — is liye upar ke imports
# hi asli kaam hain, aur unhein hatana nahi (isi liye noqa lagaya hai).
#
# Pehle wali saat lines dar-asal ek hi call thi jo saat dafa likhi hui thi:
# chha modules ka Base same object tha. Sirf sentiment alag tha, aur wahi is
# module ke "alag backend" hone ka ehsaas deta tha.
Base.metadata.create_all(bind=engine)


# create_all() existing tables mein naye columns add nahi karta — har module ke
# naye fields ke liye additive migration chalao.

# store_country/store_currency purani brand_profiles tables mein nahi hain, aur
# har LLM prompt ka location context inhi par chalta hai.
try:
    brand_profile.ensure_brand_profile_schema(engine)
    logger.info(" Brand profile schema up to date")
except Exception as e:
    logger.warning(f"⚠️ Brand profile schema migration skipped: {e}")

# chatbot ke naye fields (status, tone, vector_ids, ...)
try:
    chatbot_models.ensure_chatbot_schema(engine)
    logger.info(" Chatbot schema up to date")
except Exception as e:
    logger.warning(f"⚠️ Chatbot schema migration skipped: {e}")

try:
    seo_result.ensure_seo_schema(engine)
    logger.info(" SEO schema up to date")
except Exception as e:
    logger.warning(f"⚠️ SEO schema migration skipped: {e}")

try:
    ads_generated.ensure_ads_schema(engine)
    logger.info("Ads schema up to date")
except Exception as e:
    logger.warning(f"⚠️ Ads schema migration skipped: {e}")

try:
    video_ads_generated.ensure_video_ads_schema(engine)
    logger.info("Video ads schema up to date")
except Exception as e:
    logger.warning(f"⚠️ Video ads schema migration skipped: {e}")

# ===== CREATE FASTAPI APP =====
app = FastAPI(
    title="BrandWave API",
    description="AI Powered Marketing Platform",
    version="1.0.0"
)

app.mount("/static", StaticFiles(directory="generated_ads"), name="static")
app.mount("/chatbot-widget", StaticFiles(directory="static"), name="chatbot_widget")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ===== RESPONSE COMPRESSION =====
# Brand profile responses bohat bare hain (asimjofa: 7,157 products = 9.12 MB
# uncompressed). JSON ~6x compress hota hai, to ye 3G par ~51s ko ~8s kar deta
# hai. minimum_size se chhoti responses par compression ka overhead nahi lagta —
# 500 bytes se kam mein compression ka fayda nahi hota.
app.add_middleware(GZipMiddleware, minimum_size=500)

# ===== UNHANDLED ERRORS PAR BHI CORS HEADERS =====
#
# Ye middleware CORSMiddleware se PEHLE add hota hai, yani stack mein us ke
# ANDAR chalta hai. Wajah ahem hai:
#
# Starlette mein agar route se koi ghair-mutawaqqa exception uthe to woh
# CORSMiddleware ke UPAR se guzar kar ServerErrorMiddleware tak jati hai.
# Us soorat mein 500 ka jawab CORS headers ke BAGHAIR banta hai — aur browser
# usay parhne se pehle hi block kar deta hai. JS ko sirf
# `TypeError: Failed to fetch` milta hai: na status, na message.
#
# Isi ne ek asli bug ko ghante chhupaye rakha: `generated_ads.product_id`
# INTEGER tha aur Shopify ki 64-bit id par INSERT "integer out of range"
# phenkta tha. Server par saaf traceback tha, magar UI par sirf
# "failed to fetch" — jis se lagta raha ke masla network/CORS ka hai.
#
# Exception ko yahan pakar ke JSONResponse banane se jawab WAPSI par
# CORSMiddleware se guzarta hai aur headers lag jate hain. Ab aisi har nakami
# browser mein asli 500 ban kar nazar aati hai.
@app.middleware("http")
async def _errors_keep_cors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        # Poora traceback server ke log mein — client ko kabhi nahi.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. Check the server logs for details."},
        )


# ===== CORS CONFIGURATION =====
#
# Pehle yahan `allow_origin_regex=".*"` tha, `allow_credentials=True` ke saath.
# Us jori ka matlab ye tha ke upar wali allow_origins list BE-MAANI thi: regex
# har origin ko qubool kar leta tha aur caller ka Origin wapas echo ho jata tha.
# Yani duniya ki koi bhi website is API ko browser se call kar sakti thi.
#
# Wo wildcard ek ASLI zaroorat ke liye tha — embeddable chatbot widget kisi bhi
# Shopify store par chalta hai aur us store ka origin pehle se maloom nahi ho
# sakta. Magar wo zaroorat SIRF widget ki hai, poori API ki nahi.
#
# Ab do alag rules hain:
#   * Dashboard/API  -> sirf maloom origins (neeche wali list)
#   * Widget ka route -> `*`, magar credentials ke BAGHAIR (dekho _widget_cors)
#
# Backend ki auth `Authorization: Bearer <supabase jwt>` HEADER se aati hai,
# cookie se nahi — is liye widget par `*` dena mehfooz hai: browser wahan koi
# cookie bhejta hi nahi.


def _allowed_origins() -> list[str]:
    """
    Dashboard ke liye jaiz origins.

    CORS_ALLOWED_ORIGINS (comma-separated) se aur FRONTEND_URL se banti hai.
    Deploy par FRONTEND_URL zaroor set karein — warna sirf localhost bachta hai
    aur deployed frontend ki har request CORS par ruk jayegi.
    """
    origins = {
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    }
    for name in ("FRONTEND_URL", "CORS_ALLOWED_ORIGINS"):
        raw = (os.getenv(name) or "").strip()
        for item in raw.split(","):
            item = item.strip().rstrip("/")
            if item:
                origins.add(item)
    return sorted(origins)


# Widget ka public surface — sirf yahan `*` chalta hai.
WIDGET_CORS_PREFIXES = ("/api/chatbot/chat", "/chatbot-widget")


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _widget_cors(request: Request, call_next):
    """
    Widget ke routes par khula CORS — baqi API par nahi.

    TARTEEB AHEM HAI: ye CORSMiddleware ke BAAD register hota hai. Starlette
    `add_middleware` ko index 0 par daalta hai, yani AAKHRI add hone wala sab
    se BAHAR hota hai aur request par PEHLE chalta hai. Isi liye preflight ka
    jawab yahan se de kar rokna kaam karta hai — CORSMiddleware ko anjaan
    origin dekhne ka mauqa hi nahi milta.

    (Pehle ye CORSMiddleware se OOPAR likha tha aur widget ka preflight 400
    kha raha tha — test se pakra gaya.)

    `Access-Control-Allow-Credentials` jaan boojh kar NAHI bhejte — `*` ke saath
    wo combination browser bhi rad kar deta hai, aur widget ko cookie chahiye
    bhi nahi.
    """
    is_widget = request.url.path.startswith(WIDGET_CORS_PREFIXES)

    if is_widget and request.method == "OPTIONS":
        requested = request.headers.get("access-control-request-headers", "content-type")
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": requested,
                "Access-Control-Max-Age": "600",
                "Vary": "Origin",
            },
        )

    response = await call_next(request)

    if is_widget:
        response.headers["Access-Control-Allow-Origin"] = "*"
        # `del` istemal karo, `.pop()` nahi — MutableHeaders `typing.Mapping` se
        # banta hai, us par `pop` hai hi nahi. Pehle yahan `.pop()` tha aur har
        # widget response AttributeError se 500 ho jata tha (script hi load nahi
        # hota tha). `__delitem__` header ghair-maujood ho to chup-chaap guzar
        # jata hai, is liye guard ki zaroorat nahi.
        del response.headers["Access-Control-Allow-Credentials"]
        response.headers["Vary"] = "Origin"
    return response


# ===== INCLUDE PARTNER'S ROUTERS =====
app.include_router(
    auth_routes.router,
    prefix="/api/auth",
    tags=["Account"]
)

app.include_router(
    scraping.router,
    prefix="/api/scraping",
    tags=["Scraping"]
)

app.include_router(
    seo.router,
    prefix="/api/seo",
    tags=["SEO"]
)

# ===== AD ROUTES: PREFIX MEIN "ads" NAHI HO SAKTA =====
#
# Pehle ye sirf "/api/ads-generation" aur "/api/video-ads" par thay. Masla ye
# hai ke uBlock/AdBlock/Brave Shields ki generic filter lists URL ke andar
# "ads-" jaisa tukra dekh kar request ko CHUP-CHAAP gira deti hain
# (net::ERR_BLOCKED_BY_CLIENT). Browser mein wo `TypeError: Failed to fetch`
# banta hai — na status code, na server log entry, kyunke request browser se
# nikalti hi nahi. Backend bilkul sehatmand hota hai aur debugging ghalat
# taraf jati hai.
#
# Is liye asli (canonical) prefix ab neutral hai. Purane prefixes bhi mounted
# rehte hain taake koi bhi purana client ya bookmark na toote — magar
# include_in_schema=False se wo /docs mein dobara nazar nahi aate.
#
# QAEDA: aage koi bhi naya public route banate waqt uske path mein "ads",
# "banner", "promo", "sponsor" jaise alfaz mat daalo.
ADS_PREFIX = "/api/image-studio"
VIDEO_ADS_PREFIX = "/api/video-studio"

# Deprecated — sirf backward compatibility ke liye. Naya code inhe na use kare.
LEGACY_ADS_PREFIX = "/api/ads-generation"
LEGACY_VIDEO_ADS_PREFIX = "/api/video-ads"

app.include_router(
    ads_generation.router,
    prefix=ADS_PREFIX,
    tags=["Ads Generation"]
)
app.include_router(
    ads_generation.router,
    prefix=LEGACY_ADS_PREFIX,
    tags=["Ads Generation"],
    include_in_schema=False,
)

# Video ads ka apna router — image ad module se bilkul alag.
app.include_router(
    video_ads.router,
    prefix=VIDEO_ADS_PREFIX,
    tags=["Video Ads"]
)
app.include_router(
    video_ads.router,
    prefix=LEGACY_VIDEO_ADS_PREFIX,
    tags=["Video Ads"],
    include_in_schema=False,
)

app.include_router(
    ai_assistant.router,
    prefix="/api/assistant",
    tags=["AI Assistant"]
)

app.include_router(
    chatbot.router,
    prefix="/api/chatbot",
    tags=["Chatbot Automation"]
)

app.include_router(
    brand_improvement.router,
    prefix="/api/brand-improvement",
    tags=["Brand Improvement"]
)
app.include_router(
profile_router, prefix="/api/profile", 
tags=["Profile"])

# Dashboard summary — har module ka ek chhota stat, EK request mein.
app.include_router(
    dashboard.router,
    prefix="/api/dashboard",
    tags=["Dashboard"]
)

# ===== INCLUDE YOUR SENTIMENT ROUTER =====
if sentiment_router:
    app.include_router(
        sentiment_router,
        prefix="/api/sentiment",
        tags=["Sentiment Analysis"]
    )
    logger.info(" Sentiment routes included")


# ===== SENTIMENT MODEL WARM-UP =====
# XLM-RoBERTa ~1.04 GB ka hai aur CPU par load hone mein ~14s lagte hain.
# Startup par ek dafa load kar lo, warna PEHLI user request 14s slow hoti hai.
# Ye blocking hai (jaan boojh kar) — server "ready" tab kahe jab model bhi tayar ho.
@app.on_event("startup")
def _check_deployment_config():
    """
    Boot par batao ke konsi config abhi tak "local dev" par hai.

    Ye cheezein deploy ke baad chup-chaap toot ti hain, is liye chup nahi
    rehna chahiye:
      * BACKEND_PUBLIC_URL — chatbot ka embed snippet aur avatar URLs isi se
        bante hain. localhost reh gaya to merchant ko aisa script tag milta
        hai jo uski site par kabhi nahi chalega.
      * Groq keys — do keys ka matlab hai dugna rate-limit budget aur 429 par
        foran failover. Ek hi ho to sab kuch usi par chalta hai.
    """
    public_url = (os.getenv("BACKEND_PUBLIC_URL") or "").strip()
    if not public_url:
        logger.warning(
            "⚠️ BACKEND_PUBLIC_URL not set — chatbot embed snippets will fall "
            "back to the request's own origin. Set it to your public API URL "
            "before sharing embed codes."
        )
    elif "localhost" in public_url or "127.0.0.1" in public_url:
        logger.warning(
            "⚠️ BACKEND_PUBLIC_URL is %s — fine for local testing, but embed "
            "snippets and avatar URLs built from it will not work anywhere "
            "else.", public_url,
        )

    try:
        from modules.llm_config import (
            OPENAI_SPEND_CAP_USD, SLOT_OPENAI, configured_key_envs,
            configured_lanes, openai_spend_usd, slot_env,
        )
        keys = configured_key_envs()
        if not keys:
            logger.error("❌ No Groq API key configured — every AI feature will fail.")
        elif len(keys) == 1:
            logger.warning(
                "⚠️ Only one Groq key (%s). Add a second (GROKAPIKEY2) to double "
                "the rate-limit budget and enable instant failover.", keys[0],
            )
        else:
            logger.info("✅ Groq keys active: %s", ", ".join(keys))

        # OpenAI lane — SEO ke teeno step iske upar chalte hain.
        if slot_env(SLOT_OPENAI):
            spent = openai_spend_usd()
            if spent >= OPENAI_SPEND_CAP_USD:
                logger.warning(
                    "⚠️ OpenAI spend cap reached ($%.4f / $%.2f) — SEO wapas Groq "
                    "par chalega. Cap barhane ke liye OPENAI_SPEND_CAP_USD set karo.",
                    spent, OPENAI_SPEND_CAP_USD,
                )
            else:
                logger.info(
                    "✅ OpenAI lane active (SEO keywords/content/blog) — "
                    "$%.4f of $%.2f used.", spent, OPENAI_SPEND_CAP_USD,
                )
        else:
            logger.warning(
                "⚠️ OPENAI_API_KEY not set — SEO will fall back to Groq and the "
                "8,000 TPM limit that motivated the OpenAI lane."
            )
        logger.info("   LLM lanes: %s", " → ".join(configured_lanes()) or "(none)")
    except Exception as e:
        logger.warning("Groq key check skipped: %s", e)


@app.on_event("startup")
def _warm_sentiment_model():
    if not sentiment_router:
        return
    try:
        from modules.sentiment.services.model_loader import warmup, get_model_dir
        if warmup():
            logger.info(f"✅ Sentiment model loaded once from {get_model_dir()}")
        else:
            logger.warning(
                f"⚠️ Sentiment model NOT loaded (looked in {get_model_dir()}). "
                f"/analyze-from-dropdown will return 503 until this is fixed."
            )
    except Exception as e:
        logger.warning(f"⚠️ Sentiment model warm-up skipped: {e}")

# ===== 5xx DETAILS LEAK NAHI HONI CHAHIYEN =====
# Bohat si routes `raise HTTPException(500, detail=str(e))` karti hain. Us se
# asli exception ka poora text browser tak chala jata tha — sentiment ke
# /results/{id} par ek ghalat id poori SQL query (har column, table ka naam,
# bound parameters) return kar deti thi.
#
# Ye handler SIRF 5xx ka detail generic karta hai; 4xx ke messages waise ke
# waise jate hain kyunke wo jaan boojh kar user ke liye likhe gaye hain aur
# frontend unhein dikhata hai. Asli wajah server log mein poori jati hai.
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code >= 500:
        logger.error(
            "%s %s -> %s: %s",
            request.method, request.url.path, exc.status_code, exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": (
                    "Something went wrong on our side. Please try again — "
                    "if it keeps happening, check the server logs."
                )
            },
            headers=getattr(exc, "headers", None),
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


# ===== GROQ RATE LIMIT -> 429 =====
# llm_config apne aap ek retry kar chuka hota hai (Groq ka bataya wait kar ke).
# Yahan tak error tab pahunchti hai jab wo retry bhi na chali ho ya na chal saki
# ho. Frontend ko generic 500 ke bajaye saaf 429 + message chahiye.
@app.exception_handler(RateLimitedError)
async def rate_limited_handler(request: Request, exc: RateLimitedError):
    headers = {}
    if exc.retry_after:
        headers["Retry-After"] = str(int(exc.retry_after) + 1)
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "error": "rate_limit",
            "detail": exc.message,
            "retry_after": exc.retry_after,
        },
        headers=headers,
    )


# ===== LLM RETRY STATUS (frontend polls this) =====
# Retry ka wait SERVER par hota hai, to browser ko sirf ek lambi pending request
# nazar aati hai. Waqt dekh kar andaza lagana kaam nahi karta - blog generation
# waise hi 30s+ leti hai. Is liye asli signal yahan se milta hai.
@app.get("/api/llm/status")
def llm_status():
    """Abhi koi rate-limit wait chal raha hai ya nahi + OpenAI credit ki halat."""
    from modules.llm_config import (
        OPENAI_SPEND_CAP_USD, configured_lanes, openai_spend_usd,
    )

    status = dict(retry_status())
    spent = openai_spend_usd()
    status["lanes"] = configured_lanes()
    status["openai"] = {
        "spent_usd": spent,
        "cap_usd": OPENAI_SPEND_CAP_USD,
        "remaining_usd": round(max(0.0, OPENAI_SPEND_CAP_USD - spent), 4),
        "enabled": spent < OPENAI_SPEND_CAP_USD,
    }
    return status


# ===== HEALTH CHECK ENDPOINT =====
@app.get("/health")
def health_check():
    """Check if all modules are running"""
    return {
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "modules": {
            "scraping": " Active",
            "seo": " Active",
            "sentiment": " Active" if sentiment_router else "⚠️ Not loaded",
  	    "ads_generation": " Active",
            "video_ads": " Active",
            "chatbot_automation": " Active"
        }
    }

# ===== ROOT ENDPOINT =====
@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "BrandWave API is running ",
        "version": "1.0.0",
        "description": "AI Powered Marketing Platform",
        "endpoints": {
            "scraping": "/api/scraping",
            "seo": "/api/seo",
            "sentiment": "/api/sentiment",
            "chatbot": "/api/chatbot",
            "health": "/health",
            "docs": "/docs"
        }
    }

# ===== RUN SERVER =====
if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "="*60)
    print(" BrandWave API Server Starting")
    print("="*60)
    print(" Scraping Module:   Ready")
    print(" SEO Module:        Ready")
    print(" Sentiment Module: " + (" Ready" if sentiment_router else "⚠️ Not found"))
    print("="*60)
    print("\n API Docs: http://localhost:8000/docs")
    print(" API Base: http://localhost:8000")
    print(" Health: http://localhost:8000/health\n")
    
    # reload ab OPT-IN hai (API_RELOAD=true), pehle hamesha on tha.
    #
    # Do wajahein:
    #   1. Reload mode do process chalata hai aur sentiment model (~1 GB) DO
    #      DAFA load hota hai — RAM dugni, startup dugna.
    #   2. Demo ke doran kisi file ko galti se save karne par server restart ho
    #      jata tha, aur agli request 14s model load ka intezar karti.
    #
    # Development mein chahiye to:  API_RELOAD=true python main.py
    reload = (os.getenv("API_RELOAD") or "").strip().lower() in {"1", "true", "yes"}
    if reload:
        print(" Auto-reload: ON (API_RELOAD set) — model will load twice\n")

    uvicorn.run(
        "main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", 8000)),
        reload=reload,
    )