from pydantic import BaseModel, Field
from typing import Optional, List


class ProductOut(BaseModel):
    # `id` Shopify ka product id hai — ad generate karte waqt yehi authoritative
    # selector hai. `index` sirf legacy/display ke liye reh gaya hai: rescrape par
    # catalogue ka size badal jata hai to index doosre product par chala jata hai.
    id: Optional[int] = None
    index: int
    name: str
    price: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    category: Optional[str] = None


class ProductListOut(BaseModel):
    products: List[ProductOut]
    total_products: int
    offset: int
    limit: int


class BrandOut(BaseModel):
    id: int
    business_name: Optional[str] = None
    website_url: str


# ---- Aspect ratio mapping (frontend se label bhejenge, backend dimensions nikalega) ----
ASPECT_RATIO_MAP = {
    "instagram_square": (1024, 1024),
    "story": (1024, 1792),
    "banner": (1792, 1024),
}


# ---- Generation modes (base image kaun banata hai) ----
# "scene"    -> Bria  : product/model photo mein pehle se hai, sirf background badlo
# "on_model" -> Claid : flat/mannequin garment ko generated model par pehnao
#
# Asal registry modules/ads_generation/services/dispatch.py mein hai; yahan sirf
# request validate hoti hai. Naya mode add karo to dono jagah entry chahiye.
GENERATION_MODES = ("scene", "on_model")
DEFAULT_GENERATION_MODE = "scene"


class GenerateImageAdRequest(BaseModel):
    brand_id: int
    # product_id authoritative hai. product_index sirf un purane profiles ke liye
    # hai jo product ids se pehle scrape hue the — dono mein se ek zaroori hai.
    product_id: Optional[int] = None
    product_index: Optional[int] = None
    # Purane clients ye field nahi bhejte — default "scene" un ke liye hai,
    # aur woh sab se mehfooz chunav bhi hai (product bilkul nahi badalta).
    generation_mode: str = DEFAULT_GENERATION_MODE
    aspect_ratio: str = "instagram_square"     # "instagram_square" | "story" | "banner"
    platform: Optional[str] = None              # "Instagram Post", "Facebook Ad", etc.
    cta_goal: Optional[str] = None               # "Shop Now", "Limited Time Offer", etc.
    mood: Optional[str] = None                   # "Festive & Warm", "Minimal & Elegant", etc.
    occasion: Optional[str] = None                # "Wedding", "Eid", "None"
    # max_length yahan bhi: 50,000-harf ka payload handler tak pohanchne se
    # PEHLE ruk jata hai. Asal (saaf message wali) safai route mein hai.
    custom_prompt: Optional[str] = Field(default=None, max_length=2000)

    # ── User ka apna text jo IMAGE PAR chhapta hai ────────────────────────
    #
    # Khali chhoro to AI ka banaya hua headline lagta hai (purana behaviour).
    # Bharo to bilkul wahi lafz chhapte hain jo user ne likhe — misal
    # "Shop the best lawn dresses from Asim Jofa".
    #
    # Ye do fields SEEDHA image par jati hain, is liye inhein input_guard se
    # guzarna lazmi hai (length, control chars, profanity). Pydantic yahan
    # sirf pehli, moti chhalni hai — asal safai route mein hoti hai, taake
    # error message wahi ho jo UI dikha sake.
    ad_text: Optional[str] = Field(default=None, max_length=400)
    ad_cta: Optional[str] = Field(default=None, max_length=120)

    user_id: str


class GenerateImageAdResponse(BaseModel):
    success: bool
    ad_id: int
    ad_image_url: str
    product_name: str
    headline: str
    caption: str
    hashtags: List[str]


class GenerateVideoAdRequest(BaseModel):
    ad_id: int


class GenerateVideoAdResponse(BaseModel):
    success: bool
    ad_video_url: str


class GalleryItem(BaseModel):
    ad_id: int
    product_name: str
    image_path: str
    video_path: Optional[str] = None
    created_at: str


class GalleryDetail(BaseModel):
    ad_id: int
    product_name: str
    image_path: str
    video_path: Optional[str] = None
    headline: Optional[str] = None
    caption: Optional[str] = None
    hashtags: Optional[str] = None
    aspect_ratio: Optional[str] = None
    platform: Optional[str] = None
    mood: Optional[str] = None
    created_at: str