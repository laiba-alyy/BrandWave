import os
import uuid
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

OUTPUT_DIR = Path("generated_ads/images")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Windows built-in fonts
FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
FONT_REGULAR = "C:/Windows/Fonts/arial.ttf"

BRAND_ACCENT_COLOR = (196, 30, 58)     # deep red accent — change per brand later
BADGE_TEXT_COLOR = (255, 255, 255)


def download_product_image(image_url: str) -> Image.Image:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(image_url, headers=headers, timeout=15)
    response.raise_for_status()
    img_path = Path("temp_download.jpg")
    with open(img_path, "wb") as f:
        f.write(response.content)
    image = Image.open(img_path).convert("RGB")
    return image


def create_ad_image(product_image: Image.Image, ad_copy: dict) -> str:
    """
    Takes the REAL product image + Groq-generated copy,
    composites a professional ad banner on top of it.
    """
    # Standardize size for ad format (portrait, good for social media)
    target_size = (1080, 1350)
    image = product_image.copy()
    image = image.resize(target_size) if image.size != target_size else image

    # Slight darken so text is readable
    enhancer = ImageEnhance.Brightness(image)
    image = enhancer.enhance(0.95)

    draw = ImageDraw.Draw(image, "RGBA")
    W, H = image.size

    # --- Bottom gradient overlay (dark to transparent) for text readability ---
    gradient_height = 450
    gradient = Image.new("RGBA", (W, gradient_height), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient)
    for y in range(gradient_height):
        alpha = int(200 * (y / gradient_height))
        grad_draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    image.paste(gradient, (0, H - gradient_height), gradient)

    draw = ImageDraw.Draw(image, "RGBA")

    # --- Discount/Price badge (top-left) ---
    badge_font = ImageFont.truetype(FONT_BOLD, 34)
    badge_text = ad_copy.get("discount_text", "")
    padding = 20
    text_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_w = (text_bbox[2] - text_bbox[0]) + padding * 2
    badge_h = (text_bbox[3] - text_bbox[1]) + padding * 2
    draw.rounded_rectangle(
        [40, 40, 40 + badge_w, 40 + badge_h],
        radius=10,
        fill=BRAND_ACCENT_COLOR
    )
    draw.text((40 + padding, 40 + padding - 5), badge_text, font=badge_font, fill=BADGE_TEXT_COLOR)

    # --- Headline (bottom area) ---
    headline_font = ImageFont.truetype(FONT_BOLD, 56)
    headline = ad_copy.get("headline", "")
    draw.text((50, H - 380), headline, font=headline_font, fill=(255, 255, 255))

    # --- CTA button (bottom-right style) ---
    cta_font = ImageFont.truetype(FONT_BOLD, 30)
    cta_text = ad_copy.get("cta", "Shop Now").upper()
    cta_bbox = draw.textbbox((0, 0), cta_text, font=cta_font)
    cta_w = (cta_bbox[2] - cta_bbox[0]) + 50
    cta_h = (cta_bbox[3] - cta_bbox[1]) + 30
    draw.rounded_rectangle(
        [50, H - 100, 50 + cta_w, H - 100 + cta_h],
        radius=8,
        fill=(255, 255, 255)
    )
    draw.text((50 + 25, H - 100 + 12), cta_text, font=cta_font, fill=BRAND_ACCENT_COLOR)

    # Save
    filename = f"{uuid.uuid4().hex}.png"
    filepath = OUTPUT_DIR / filename
    image.save(filepath)

    return str(filepath)