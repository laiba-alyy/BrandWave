"""
Video ad generation — image ad module se ALAG router.

Product search/list yahan DOBARA nahi likhi gayi. Frontend wahi maujooda
endpoints istemal karta hai:
    GET /api/ads-generation/products/search
    GET /api/ads-generation/products/{brand_id}
    GET /api/ads-generation/my-brands/{user_id}

Aur brand ownership + product resolution ke liye ads_generation ke wahi do
helpers import hote hain, taake "product_id gum ho gaya" / "doosre ka brand_id"
wali soorat-e-haal dono modules mein BILKUL ek jaisi handle ho. Un helpers ko
copy karne ka matlab hota ke aage koi bug sirf ek jagah theek hota.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database.connection import get_db
from models.ads_generated import GeneratedAd
from models.video_ads_generated import GeneratedVideoAd

# Reuse — dekho is file ka header.
from api.routes.ads_generation import _get_owned_brand, _resolve_product

from modules.video_ads import dispatch, fal_client
from modules.video_ads.fal_client import (
    VideoAdServiceError,
    VideoCreditsExhaustedError,
)
from modules.video_ads import end_card as end_card_mod
from modules.video_ads import frame_utils
from modules.video_ads.prompt_guard import InvalidAdInput, review_prompt
from modules.video_ads.prompt_drafter import PromptDraftError, draft_prompts
from modules.ads_generation.input_guard import clean_ad_text, clean_choice
from modules.video_ads.schemas import (
    DEFAULT_SOURCE, FREE_DURATIONS, MAX_END_CARD_CHARS, MAX_IDEA_CHARS,
    PROMPT_SOURCES, SUPPORTED_DURATIONS, VIDEO_SOURCES,
    DraftPromptRequest, DraftPromptResponse,
    GenerateVideoAdRequest, GenerateVideoAdResponse,
    VideoGalleryDetail, VideoGalleryItem,
    build_options_response, duration_requires_credits,
)
from modules.auth import get_current_user, require_owner

logger = logging.getLogger(__name__)


def _paid_duration_message(payload) -> str:
    """402 ka message — segment count asal plan se parh kar."""
    segments = None
    try:
        caps = dispatch.plan_capabilities().get(
            dispatch.normalise_plan(payload.user_plan), {})
        for d in caps.get("durations", []):
            if d["seconds"] == payload.duration_seconds:
                segments = d["segments"]
                break
    except Exception:  # noqa: BLE001 - message banane mein nakami 500 na bane
        pass

    cost = (f"it runs {segments} billable generations instead of one"
            if segments else "it runs several billable generations instead of one")
    return (
        f"{payload.duration_seconds}-second videos need paid credits — {cost}. "
        f"Please choose {' or '.join(f'{s}s' for s in FREE_DURATIONS)} instead."
    )

router = APIRouter(tags=["Video Ads"])


# ---------- 1. Form ke options ----------
@router.get("/options")
def get_video_ad_options():
    """
    Form ke saare presets + length plans.

    Frontend in ki labels render karta hai aur keys wapas bhejta hai. Registry
    backend par hai kyunki har option ke saath us ka prompt fragment bandha hai
    (modules/video_ads/schemas.py dekho).
    """
    return build_options_response()


# ---------- 2. Prompt likhwana ("Write the prompt for me") ----------
@router.post("/draft-prompt", response_model=DraftPromptResponse)
def draft_video_prompt(payload: DraftPromptRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Form ke jawabat + user ki ek line -> teen qabil-e-istemal prompt options.

    Yahan koi FAL CREDIT KHARCH NAHI hota — sirf ek chhoti text LLM call. Isi
    liye ye generate se bilkul alag rasta hai: user pehle prompt dekhta hai,
    chahe to edit karta hai, aur TAB video banata hai. Agar ye generate ke
    andar hota to har draft ek billable generation ban jata.

    Dekho modules/video_ads/prompt_drafter.py.
    """
    # User ka likha hua sab kuch pehle saaf — wahi guard jo generate par hai
    # (gaali + length), taake dono jagah ek hi list aur ek hi message rahe.
    try:
        idea = clean_ad_text(payload.idea, max_len=MAX_IDEA_CHARS, field="Your idea")
        form_data = {
            "ad_style": clean_choice(payload.ad_style, field="style"),
            "scene": clean_choice(payload.scene, field="scene"),
            "mood": clean_choice(payload.mood, field="mood"),
            "camera_motion": clean_choice(payload.camera_motion, field="camera motion"),
            "lighting": clean_choice(payload.lighting, field="lighting"),
            "pacing": clean_choice(payload.pacing, field="pacing"),
        }
    except InvalidAdInput as e:
        raise HTTPException(400, e.message)

    # Ownership har soorat mein — wahi usool jo generate par hai.
    brand = _get_owned_brand(payload.brand_id, caller, db)

    # ── Product ka context ───────────────────────────────────────────────
    #
    # Yahan product sirf CONTEXT hai (naam/category/description), video ka
    # input NAHI. Is liye us ka na milna error NAHI banta: purani tab ka stale
    # product_id sirf is wajah se prompt likhwane se nahi rok sakta. Bina
    # context ke draft thora aam hota hai, magar banta hai.
    product = None

    if payload.source == "image_ad":
        # image_ad wale raste par catalogue ka product_id request mein nahi
        # aata — wo us bane hue ad ke record mein hota hai. Pehle ye rasta
        # chhoot gaya tha, to "existing image ad" chunne par drafter ko pata
        # hi nahi chalta tha ke video kis cheez ka hai.
        ad = (
            db.query(GeneratedAd)
            .filter(
                GeneratedAd.id == payload.source_ad_id,
                GeneratedAd.user_id == caller,
            )
            .first()
        )
        if ad:
            # Pehle catalogue se poora product (category/description ke liye);
            # na mile to kam az kam ad ka mehfooz kiya hua naam.
            if ad.product_id is not None:
                try:
                    product, _ = _resolve_product(brand, ad.product_id, None)
                except HTTPException:
                    product = None
            if product is None:
                product = {"id": ad.product_id, "name": ad.product_name}

    elif payload.product_id is not None or payload.product_index is not None:
        try:
            product, _ = _resolve_product(
                brand, payload.product_id, payload.product_index
            )
        except HTTPException:
            logger.info(
                "[video] draft-prompt: product %s catalogue mein nahi — "
                "bina product ke context ke draft bana rahe hain",
                payload.product_id,
            )

    try:
        drafted = draft_prompts(form_data, idea, product, brand)
    except PromptDraftError as e:
        # 502 — user ki ghalti nahi, aur koi credit bhi kharch nahi hua, is
        # liye "dobara koshish karein" yahan sach hai.
        logger.error(
            "Video prompt drafting failed (brand=%s, idea=%r): %s",
            payload.brand_id, (idea or "")[:60], e.detail,
        )
        raise HTTPException(502, e.message)

    return DraftPromptResponse(**drafted)


# ---------- 3. Video Ad Generate Karna ----------
@router.post("/generate", response_model=GenerateVideoAdResponse)
def generate_video_ad(payload: GenerateVideoAdRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Product image (ya maujooda image ad) -> product video ad.

    Provider `user_plan` se tay hota hai: "free" -> Kling, "premium" -> Veo 3.1
    (dekho modules/video_ads/dispatch.py). Dono ek hi FAL_API_KEY par chalte
    hain aur dono ko wahi form, wahi guardrails aur wahi gallery milti hai.

    Yeh endpoint MINUTES le sakta hai: har length 1-3 billable generations
    chalati hai (kitni — yeh provider par munhasir hai, /options batata hai) aur
    har generation khud kai minute leti hai. Sync rakhi gayi hai taake image ad
    wale route se mail khaye; frontend cost pehle hi dikha deta hai.
    """
    if payload.source not in VIDEO_SOURCES:
        raise HTTPException(
            400,
            f"Unknown source '{payload.source}'. Choose one of: {', '.join(VIDEO_SOURCES)}.",
        )

    if payload.duration_seconds not in SUPPORTED_DURATIONS:
        raise HTTPException(
            400,
            f"Unsupported video length. Choose one of: "
            f"{', '.join(f'{s}s' for s in sorted(SUPPORTED_DURATIONS))}.",
        )

    # ── Paid length ka darwaza ───────────────────────────────────────────
    #
    # 20s teen billable segments chalata hai (10s sirf ek). Trial credits par
    # ye ek hi video mein poora balance kha sakta hai, is liye default par
    # band hai. Kholne ke liye VIDEO_PAID_DURATIONS env (dekho schemas.py).
    #
    # 402 jaan boojh kar — 400 nahi. Ye user ki ghalti nahi, billing ki hadd
    # hai, aur UI is code par apna alag panel dikhati hai.
    if duration_requires_credits(payload.duration_seconds):
        # Segment count PLAN se aata hai, kisi formula se nahi — har provider
        # ka jorr alag hai (Kling 20s = 10+5+5, Veo = 8+8+4), aur ghalat
        # number user ko cost ke baare mein jhooti baat batata.
        raise HTTPException(402, _paid_duration_message(payload))

    # ── User ka likha hua text: prompt + end card ────────────────────────
    #
    # Ye generation se PEHLE hota hai. Pehle prompt seedha provider ko jata
    # tha, is liye "123456kjhgfd" bhi poori creative direction ban kar 2-3
    # minute aur ek billable generation kharch kar deta tha.
    try:
        prompt_decision = review_prompt(payload.custom_prompt)
        end_card_text = clean_ad_text(
            payload.end_card_text, max_len=MAX_END_CARD_CHARS, field="End card text")
        ad_style = clean_choice(payload.ad_style, field="style")
        scene = clean_choice(payload.scene, field="scene")
        mood = clean_choice(payload.mood, field="mood")
        camera_motion = clean_choice(payload.camera_motion, field="camera motion")
        lighting = clean_choice(payload.lighting, field="lighting")
        pacing = clean_choice(payload.pacing, field="pacing")
    except InvalidAdInput as e:
        raise HTTPException(400, e.message)

    # ── Prompt kis raste se aaya ─────────────────────────────────────────
    #
    # Client ka bheja hua flag AKELA bharosay ke qabil nahi: agar prompt
    # na-qabil-e-istemal nikla to wo istemal hua hi nahi, chahe client ne
    # "ai" bheja ho. Is liye asal soorat-e-haal YAHAN tay hoti hai, us ke
    # baad jo record hota hai wo waqai wahi hai jo hua.
    if not prompt_decision.used:
        prompt_source = "form"
    elif payload.prompt_source in PROMPT_SOURCES and payload.prompt_source != "form":
        prompt_source = payload.prompt_source
    else:
        # Anjaan ya khali flag = purana client, jo sirf hath se likha hua
        # prompt bhejta tha.
        prompt_source = "manual"

    # Ownership har soorat mein — brand isi account ka hona chahiye.
    brand = _get_owned_brand(payload.brand_id, caller, db)

    product = None
    product_index = None
    product_name = None
    source_ad_id = None

    if payload.source == "image_ad":
        # Secondary rasta: pehle se bana hua image ad.
        ad = (
            db.query(GeneratedAd)
            .filter(
                GeneratedAd.id == payload.source_ad_id,
                GeneratedAd.user_id == caller,
            )
            .first()
        )
        if not ad:
            raise HTTPException(404, "That image ad was not found in your gallery.")

        source_ad_id = ad.id
        product_name = ad.product_name
        product_index = ad.product_index
        # Image ad ki file SIRF is server par hai — fal us tak nahi pahunch
        # sakta (dev par localhost hai). Data URI bana kar bhejte hain.
        try:
            image_ref = fal_client.file_to_data_uri(ad.image_path)
        except VideoAdServiceError as e:
            logger.error("Video ad source image unusable (ad=%s): %s", ad.id, e.detail)
            raise HTTPException(400, e.message)
        source_image_url = ad.image_path
        product = {"id": ad.product_id, "name": ad.product_name}

    else:
        # PRIMARY rasta: scraped catalogue ka product.
        if not brand.products:
            raise HTTPException(404, "No products found for this brand")

        product, product_index = _resolve_product(
            brand, payload.product_id, payload.product_index
        )
        product_name = product.get("name", "")

        image_ref = (product.get("image_url") or "").strip()
        if not image_ref:
            raise HTTPException(
                400,
                "This product has no image in the catalogue, so a video cannot be "
                "generated for it. Re-scrape the store or pick another product.",
            )
        source_image_url = image_ref

    form_data = {
        "ad_style": ad_style,
        "scene": scene,
        "mood": mood,
        "camera_motion": camera_motion,
        "lighting": lighting,
        "pacing": pacing,
        # Na-qabil-e-istemal prompt yahan None ban kar aata hai, is liye
        # build_video_prompt form ke fragments par wapas chala jata hai —
        # yani style/scene/mood/lighting/camera/pacing sab phir se lagte hain.
        "custom_prompt": prompt_decision.text,
        "duration_seconds": payload.duration_seconds,
    }

    try:
        # Provider ka intikhab plan flag se hota hai (free -> Kling,
        # premium -> Veo). Route ko providers ka farq nahi maloom.
        generated = dispatch.generate_video_ad(
            payload.user_plan, image_ref, form_data, product, brand
        )
    except VideoCreditsExhaustedError as e:
        # 402 alag se: "dobara koshish karein" is soorat mein jhoot hai, aur
        # UI is code par apna "out of credits" panel dikhati hai.
        logger.error(
            "Video credits exhausted (plan=%s, brand=%s): %s",
            payload.user_plan, payload.brand_id, e.detail,
        )
        raise HTTPException(402, e.message)
    except VideoAdServiceError as e:
        # Raw provider response SIRF log mein — wahi usool jo ads_generation
        # ke image route par hai.
        logger.error(
            "Video ad failed (plan=%s, provider=%s, brand=%s, source=%s, "
            "product=%s, duration=%s): %s",
            payload.user_plan, e.provider, payload.brand_id, payload.source,
            (product or {}).get("id"), payload.duration_seconds, e.detail,
        )
        raise HTTPException(502, e.message)

    # ── End card ─────────────────────────────────────────────────────────
    #
    # Provider ka video ban chuka hai aur uska credit kharch ho chuka hai, is
    # liye card ki koi bhi nakami poori generation zaya nahi karni chahiye —
    # us soorat mein bina card wala video hi rakh lete hain.
    final_duration = generated["duration_seconds"]
    end_card_applied = False
    if end_card_text:
        try:
            carded = end_card_mod.append_end_card(
                generated["video_path"],
                end_card_text,
                fal_client.new_video_path(),
            )
            generated["video_path"] = str(carded)
            # Asal file se maapo, DEFAULT_SECONDS jorne se nahi: provider ka
            # clip hamesha theek utna lamba nahi hota jitna maanga gaya tha,
            # aur gallery mein ghalat lambai dikhna bura lagta hai.
            try:
                final_duration = round(frame_utils.clip_duration(carded))
            except Exception:  # noqa: BLE001
                final_duration = round(final_duration + end_card_mod.DEFAULT_SECONDS)
            end_card_applied = True
        except Exception as e:  # noqa: BLE001 - card optional hai
            logger.error(
                "End card failed (video=%s) — keeping the video without it: %s: %s",
                generated["video_path"], type(e).__name__, e,
            )

    new_video = GeneratedVideoAd(
        user_id=caller,
        brand_id=payload.brand_id,
        source=payload.source,
        source_ad_id=source_ad_id,
        source_image_url=source_image_url,
        product_name=product_name,
        product_id=(product or {}).get("id"),
        product_index=product_index,
        ad_style=ad_style,
        scene=scene,
        mood=mood,
        camera_motion=camera_motion,
        lighting=lighting,
        pacing=pacing,
        custom_prompt=prompt_decision.text,
        prompt_source=prompt_source,
        duration_seconds=final_duration,
        segments=generated["segments"],
        model_id=generated["model_id"],
        provider=generated["provider"],
        user_plan=generated["user_plan"],
        final_prompt=generated["prompt"],
        video_path=generated["video_path"],
    )
    db.add(new_video)
    db.commit()
    db.refresh(new_video)

    return GenerateVideoAdResponse(
        success=True,
        video_id=new_video.id,
        video_url=new_video.video_path,
        product_name=product_name,
        duration_seconds=new_video.duration_seconds,
        segments=new_video.segments,
        model_id=new_video.model_id,
        provider=new_video.provider,
        user_plan=new_video.user_plan,
        prompt_notice=prompt_decision.notice or None,
        end_card=bool(end_card_applied),
    )


# ---------- 4. Video Gallery ----------
@router.get("/gallery/{user_id}", response_model=list[VideoGalleryItem])
def get_video_gallery(user_id: str, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(caller, user_id)
    videos = (
        db.query(GeneratedVideoAd)
        .filter(GeneratedVideoAd.user_id == user_id)
        .order_by(desc(GeneratedVideoAd.created_at))
        .all()
    )
    return [
        VideoGalleryItem(
            video_id=v.id,
            product_name=v.product_name,
            video_path=v.video_path,
            duration_seconds=v.duration_seconds,
            segments=v.segments,
            source=v.source,
            provider=v.provider,
            user_plan=v.user_plan,
            created_at=v.created_at.isoformat() if v.created_at else "",
        )
        for v in videos
    ]


# ---------- 5. Ek video ki poori detail ----------
@router.get("/gallery/detail/{video_id}", response_model=VideoGalleryDetail)
def get_video_detail(video_id: int, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    v = db.query(GeneratedVideoAd).filter(GeneratedVideoAd.id == video_id).first()
    if not v:
        raise HTTPException(404, "Video ad not found")
    if v.user_id != caller:
        raise HTTPException(403, "You can only view your own video ads.")

    return VideoGalleryDetail(
        video_id=v.id,
        product_name=v.product_name,
        video_path=v.video_path,
        duration_seconds=v.duration_seconds,
        segments=v.segments,
        source=v.source,
        provider=v.provider,
        user_plan=v.user_plan,
        created_at=v.created_at.isoformat() if v.created_at else "",
        source_image_url=v.source_image_url,
        ad_style=v.ad_style,
        scene=v.scene,
        mood=v.mood,
        camera_motion=v.camera_motion,
        lighting=v.lighting,
        pacing=v.pacing,
        custom_prompt=v.custom_prompt,
        prompt_source=v.prompt_source,
        model_id=v.model_id,
        final_prompt=v.final_prompt,
    )
