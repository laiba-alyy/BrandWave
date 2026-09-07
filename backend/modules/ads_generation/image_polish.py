"""
Generated (text-free) ad image par Pillow se crisp text lagana.

Yahan teen cheezein theek ki gayi hain jo demo mein page giradeti thin:

 1. FONT PATH — pehle "C:/Windows/Fonts/arialbd.ttf" HARDCODED tha. Windows par
    bhi ye file har machine par ho, zaroori nahi (N-editions mein nahi hoti),
    aur Linux/Docker par to kabhi nahi. Font na mile to ImageFont.truetype
    OSError phenkta hai — yani poori ad generation 500 par khatam, us image ke
    baad jo pehle hi provider se ban chuki aur credit kharch kar chuki thi.
    Ab candidates ki list hai aur aakhri chara Pillow ka built-in font.

 2. WRAPPING — headline seedha draw.text() ko jata tha. AI ka headline (ya ab
    user ka apna text) image se BAHAR nikal jata tha; sirf pehle chand lafz
    dikhte the. Ab text image ki chaudai mein wrap hota hai aur zaroorat par
    font chhota hota hai.

 3. KHALI TEXT — khali headline par sirf gradient chhapta tha aur image
    "adhoori" lagti thi. Ab jo hissa khali hai wo draw hi nahi hota.
"""
import logging
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("generated_ads/images")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Pehla font jo mile wahi. Windows, macOS aur aam Linux images — teenon ko
# cover karta hai. DejaVu Pillow ke saath hi aata hai, is liye wo taqreeban
# hamesha maujood hota hai.
_BOLD_CANDIDATES = (
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """
    Bold font is size par. Koi bhi TTF na mile to Pillow ka default.

    Default bitmap font size ko ignore karta hai (chhota rehta hai), is liye
    natija khoobsurat nahi hota — magar ad BAN jati hai, aur ye 500 se behtar
    hai. Wo soorat log mein saaf nazar aati hai.
    """
    for path in _BOLD_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, ValueError):
            continue
    logger.warning(
        "[ads] koi bundled TTF nahi mila — Pillow ka default font use ho raha "
        "hai, text chhota dikhega. Server par DejaVu/Liberation install karein."
    )
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """
    Lafz-ba-lafz wrapping.

    Ek hi lafz agar poori line se lamba ho (misal "aaaaaaaa...") to usay harf
    par tor dete hain — warna wo line hamesha overflow karti rehti.
    """
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words, line = paragraph.split(), ""
        for word in words:
            trial = f"{line} {word}".strip()
            if _text_size(draw, trial, font)[0] <= max_width:
                line = trial
                continue
            if line:
                lines.append(line)
            # Ek lafz jo akela hi na sama sake
            while _text_size(draw, word, font)[0] > max_width and len(word) > 1:
                cut = len(word) - 1
                while cut > 1 and _text_size(draw, word[:cut], font)[0] > max_width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        if line:
            lines.append(line)
    return lines or [""]


def _fit_lines(draw, text: str, base_size: int, max_width: int, max_lines: int):
    """
    Font chhota karte jao jab tak text `max_lines` mein na sama jaye.

    Return: (font, lines). Sab se chhote size par bhi na samaye to utni hi
    lines rakh lete hain jitni jagah hai — kaat kar, taake product ki tasveer
    text ke neeche na dab jaye.
    """
    size = base_size
    while size > 10:
        font = _load_font(size)
        lines = _wrap(draw, text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
        size = int(size * 0.88)
    font = _load_font(size)
    return font, _wrap(draw, text, font, max_width)[:max_lines]


def add_text_overlay(
    image_path: str,
    headline: str,
    cta_text: str,
    discount_text: str = None,
) -> str:
    """
    Text-free base image par headline + CTA (+ optional badge) lagata hai.

    `headline` ab user ka apna likha hua bhi ho sakta hai — dekho route ka
    `ad_text`. Dono soorton mein wo input_guard se saaf ho kar aata hai.
    """
    image = Image.open(image_path).convert("RGBA")
    W, H = image.size
    draw = ImageDraw.Draw(image, "RGBA")

    headline = (headline or "").strip()
    cta_text = (cta_text or "").strip()
    discount_text = (discount_text or "").strip()

    margin_x = int(W * 0.045)
    max_text_width = W - margin_x * 2

    # --- Bottom gradient, taake text har tasveer par parha ja sake ---
    gradient_height = int(H * 0.32)
    gradient = Image.new("RGBA", (W, gradient_height), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient)
    for y in range(gradient_height):
        grad_draw.line([(0, y), (W, y)], fill=(0, 0, 0, int(190 * (y / gradient_height))))
    image.paste(gradient, (0, H - gradient_height), gradient)
    draw = ImageDraw.Draw(image, "RGBA")

    # --- Discount badge (top-left, optional) ---
    if discount_text:
        badge_font = _load_font(int(W * 0.032))
        padding = int(W * 0.02)
        bw, bh = _text_size(draw, discount_text, badge_font)
        bw, bh = bw + padding * 2, bh + padding * 2
        margin = int(W * 0.035)
        draw.rounded_rectangle(
            [margin, margin, margin + bw, margin + bh],
            radius=bh // 2, fill=(212, 175, 55, 255),
        )
        draw.text((margin + padding, margin + padding - 4), discount_text,
                  font=badge_font, fill=(30, 20, 15))

    # --- CTA pill (bottom-left) — pehle iski jagah nikalte hain taake
    #     headline uske upar baithe, us par nahi ---
    cta_y = H - int(H * 0.10)
    if cta_text:
        cta_font = _load_font(int(W * 0.032))
        cta_upper = cta_text.upper()
        # CTA wrap nahi hoti — pill ek line ka hota hai. Na samaye to font
        # chhota karo, kaato nahi (aadha lafz button par bura lagta hai).
        while _text_size(draw, cta_upper, cta_font)[0] > max_text_width * 0.6 \
                and cta_font.size > 12:
            cta_font = _load_font(int(cta_font.size * 0.9))
        cw, ch = _text_size(draw, cta_upper, cta_font)
        cw, ch = cw + int(W * 0.06), ch + int(W * 0.035)
        draw.rounded_rectangle(
            [margin_x, cta_y, margin_x + cw, cta_y + ch],
            radius=ch // 2, fill=(255, 255, 255, 255),
        )
        draw.text((margin_x + int(W * 0.03), cta_y + int(W * 0.015)), cta_upper,
                  font=cta_font, fill=(20, 20, 20))

    # --- Headline: wrap + auto-shrink, CTA ke bilkul upar se uthta hua ---
    if headline:
        font, lines = _fit_lines(draw, headline, int(W * 0.058), max_text_width, max_lines=3)
        line_h = _text_size(draw, "Ag", font)[1]
        gap = int(line_h * 0.42)
        block_h = len(lines) * line_h + (len(lines) - 1) * gap
        # CTA ke upar se shuru — pehle ye fixed H*0.22 par tha, is liye do-line
        # headline seedhi CTA button ke oopar chhap jati thi.
        y = cta_y - int(H * 0.035) - block_h
        for line in lines:
            # Halka sa shadow: safed text kabhi kabhi halke background par
            # ghayab ho jata tha, chahe gradient ho.
            draw.text((margin_x + 2, y + 2), line, font=font, fill=(0, 0, 0, 130))
            draw.text((margin_x, y), line, font=font, fill=(255, 255, 255))
            y += line_h + gap

    final = image.convert("RGB")
    filepath = OUTPUT_DIR / f"{uuid.uuid4().hex}.jpg"
    final.save(filepath, quality=92)
    return str(filepath)
