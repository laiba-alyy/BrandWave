"""
Video ke aakhir mein ek text end-card jorna — moviepy se, LOCAL.

Ye feature do maslay ek saath hal karta hai:

  1. User apna paigham video par likhwa sakta hai ("Shop the new lawn
     collection - asimjofa.com"), jo generative model se karwana taqreeban
     namumkin hai: prompt mein text maangne par model bigda hua, aadha-adhoora
     text banata hai. Isi liye video prompt mein "NO TEXT ANYWHERE" likha hai
     (dekho prompt_builder.FIXED_INSTRUCTIONS) - text hamesha baad mein, aise
     hi lagta hai.

  2. Video LAMBA ho jata hai bina koi extra generation credit kharch kiye.
     Provider se 10s ka clip aaya, end card 3s ka - user ko 13s ka ad milta
     hai aur bill wahi 10s ka rehta hai. 20s wali generation ke muqable ye
     bilkul muft hai.

Animation: text fade-in -> theherta hai -> fade-out. Background video ke aakhri
frame ka gehra kiya hua roop hai, is liye card poori tarah alag "black slate"
nahi lagta - wohi rang, wohi mahaul.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# End card ki lambai. 3s: parhne ke liye kaafi, aur itna bhi nahi ke ad
# khinchi hui lage. Fade in/out isi ke andar se aate hain.
DEFAULT_SECONDS = 3.0
FADE_SECONDS = 0.6

MAX_END_CARD_CHARS = 90


def _load_font(size: int):
    """Wahi fallback chain jo image_polish mein hai - hardcoded path nahi."""
    from PIL import ImageFont

    candidates = (
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, ValueError):
            continue
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines or [text]


def render_card_image(text: str, size: tuple[int, int], base_frame=None):
    """
    End card ka ek PNG frame banata hai (numpy array ke tor par).

    `base_frame` (video ka aakhri frame) mile to usay gehra kar ke background
    banate hain, warna saada ink background.
    """
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter

    W, H = size

    if base_frame is not None:
        bg = Image.fromarray(base_frame).convert("RGB").resize((W, H))
        # Blur + dark: text parha jaye, magar scene ka rang baqi rahe.
        bg = bg.filter(ImageFilter.GaussianBlur(radius=max(2, W // 90)))
        overlay = Image.new("RGB", (W, H), (10, 10, 10))
        bg = Image.blend(bg, overlay, 0.72)
    else:
        bg = Image.new("RGB", (W, H), (10, 10, 10))

    draw = ImageDraw.Draw(bg)
    max_width = int(W * 0.82)

    # Font itna chhota karo ke text 3 lines mein aa jaye.
    size_px = int(W * 0.062)
    while size_px > 12:
        font = _load_font(size_px)
        lines = _wrap(draw, text, font, max_width)
        if len(lines) <= 3:
            break
        size_px = int(size_px * 0.88)
    else:
        font = _load_font(size_px)
        lines = _wrap(draw, text, font, max_width)[:3]

    line_h = int(size_px * 1.35)
    total_h = line_h * len(lines)
    y = (H - total_h) // 2

    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((W - w) / 2, y), line, font=font, fill=(255, 255, 255))
        y += line_h

    # Amber underline — brand accent, aur nazar text par tikti hai.
    rule_w = int(W * 0.10)
    rule_y = y + int(size_px * 0.45)
    draw.rounded_rectangle(
        [(W - rule_w) // 2, rule_y, (W + rule_w) // 2, rule_y + max(3, H // 300)],
        radius=3, fill=(240, 166, 60),
    )

    return np.array(bg)


def append_end_card(
    video_path: str | Path,
    text: str,
    dest: str | Path,
    seconds: float = DEFAULT_SECONDS,
) -> Path:
    """
    `video_path` ke baad text card jor kar `dest` par likh do.

    Nakami par exception upar jati hai — caller (engine/route) faisla karta hai
    ke video bina card ke rakhni hai. Video pehle hi ban chuki aur uska credit
    kharch ho chuka hota hai, is liye card ki nakami poori generation zaya
    nahi karni chahiye.
    """
    from moviepy import ColorClip, ImageClip, VideoFileClip, concatenate_videoclips

    video_path, dest = Path(video_path), Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    clip = VideoFileClip(str(video_path))
    try:
        W, H = clip.size
        fps = clip.fps or 24

        # Aakhri frame background ke liye. Bilkul `duration` par seek karne se
        # moviepy kabhi kabhi khali frame deta hai — thora peeche se lete hain
        # (wahi ehtiyat jo frame_utils.extract_last_frame mein hai).
        try:
            base = clip.get_frame(max(0.0, clip.duration - 0.05))
        except Exception:  # noqa: BLE001 - background optional hai
            base = None

        card = render_card_image(text, (W, H), base)

        # Fade in -> hold -> fade out. moviepy 2.x mein effects `with_effects`
        # se lagte hain; purane `fadein/fadeout` helpers hat chuke hain.
        card_clip = ImageClip(card).with_duration(seconds).with_fps(fps)
        try:
            from moviepy.video.fx import FadeIn, FadeOut
            card_clip = card_clip.with_effects([FadeIn(FADE_SECONDS), FadeOut(FADE_SECONDS)])
        except Exception as e:  # noqa: BLE001
            # Fade na lag sake to card phir bhi lagta hai — sirf animation
            # ke baghair. Ye poore feature ko girane se behtar hai.
            logger.warning("[video] end card fade skipped: %s: %s", type(e).__name__, e)

        final = concatenate_videoclips([clip, card_clip], method="compose")
        final.write_videofile(str(dest), codec="libx264", audio=False, logger=None)
        final.close()
        card_clip.close()
    finally:
        try:
            clip.close()
        except Exception:  # noqa: BLE001
            pass

    logger.info("[video] end card jora (%.1fs) -> %s", seconds, dest)
    return dest
