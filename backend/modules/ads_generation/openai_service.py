import os
import base64
import uuid
import requests
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

OUTPUT_DIR = Path("generated_ads/images")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Base ad direction (HAR image par lagti hai) ───────────────────────────────
# Pehle caller ka prompt SEEDHA images.edit ko jata tha — us mein sirf creative
# direction (mood/occasion/country) hoti thi, koi guardrail nahi. Do masle hote the:
#
#   1. Model apna text khud image mein bana deta tha (aksar toota hua/ghalat
#      spelling), aur uske ooper image_polish.py Pillow se saaf text stamp karta
#      tha — yani ek hi ad par text ki DO layers.
#   2. Model product ko hi repaint kar deta tha — shape, rang, kapre ka texture
#      badal jate the, to ad us product ka reh hi nahi jata jo user bech raha hai.
#
# Ye rules constant hain, is liye yahan rakhe gaye hain — images.edit se foran
# pehle. build_image_prompt() sirf creative direction deta hai (optional, har
# request par badalti hai); guardrails us par depend nahi karte, warna jo caller
# builder use na kare wo chup-chaap guardrails ke baghair chala jata.
AD_INTRO = (
    "Transform this product photo into a professional advertisement "
    "for this exact product."
)

AD_HARD_RULES = """Hard rules — these override anything above:
- Keep the product itself EXACTLY as it is. Its shape, proportions, colours,
  materials, patterns and details must not change. Any text, label or logo that
  is physically printed on the product must stay exactly as it is — do not
  redraw, restyle or remove it, and do not add anything to the product.
- Do NOT add any text, letters, words, numbers, captions, watermarks, logos,
  labels or badges anywhere in the image. The rendered image must contain no
  typography of any kind. Headline, price and call-to-action text are added
  separately afterwards.
- Leave the bottom third of the image relatively clean and uncluttered so that
  text can be overlaid there later.
- Professional advertising photography: cinematic lighting, high quality, with a
  background and styling that suit this product and its market."""


def build_final_prompt(creative_direction: str) -> str:
    """
    Caller ki creative direction + hamesha lagne wale guardrails.

    Tarteeb ahem hai: creative direction PEHLE (wo context set karti hai), hard
    rules AAKHIR mein — "these override anything above" isi par depend karta hai,
    aur aakhri instructions par model behtar amal karta hai. Creative direction
    khali bhi ho sakti hai (na mood, na occasion, na country) — us surat mein
    sirf intro + rules jate hain, koi khali section nahi banta.
    """
    sections = [AD_INTRO]

    creative_direction = (creative_direction or "").strip()
    if creative_direction:
        sections.append(f"Creative direction:\n{creative_direction}")

    sections.append(AD_HARD_RULES)
    return "\n\n".join(sections)


def download_product_image(image_url: str) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(image_url, headers=headers, timeout=15)
    response.raise_for_status()
    return response.content


def generate_ad_image(image_bytes: bytes, prompt: str, width: int, height: int) -> str:
    """
    Asli product photo ko ad image banata hai (gpt-image-1, image edit mode).

    `prompt` = caller ki creative direction (build_image_prompt se: mood,
    occasion, custom prompt, market context). build_final_prompt() us ke saath
    AD_HARD_RULES ke guardrails hamesha lagata hai — product na badle, aur image
    mein koi text na aaye.
    """

    if height > width:
        size = "1024x1792"
    elif width > height:
        size = "1792x1024"
    else:
        size = "1024x1024"

    result = client.images.edit(
        model="gpt-image-1",
        image=("product.jpg", image_bytes, "image/jpeg"),
        prompt=build_final_prompt(prompt),
        size=size,
    )

    image_data = result.data[0].b64_json
    image_bytes_out = base64.b64decode(image_data)

    filename = f"{uuid.uuid4().hex}.png"
    filepath = OUTPUT_DIR / filename

    with open(filepath, "wb") as f:
        f.write(image_bytes_out)

    return str(filepath)