"""
Video ke frames aur segments par local kaam — moviepy/Pillow se, koi API call
nahi.

Do kaam hain, dono extension chain ke liye zaroori:
  1. `extract_last_frame` — pichli clip ka aakhri frame, jo agli generation ka
     start image banta hai. Kling ki apni "extend" bhi andar se yehi karti hai.
  2. `join_segments`     — frame-continuous segments ko EK file bana dena.

Nuqta: yeh alag alag clips ka "stitch" NAHI hai. Har segment ka pehla frame
pichle segment ka aakhri frame hai, is liye jorr par koi cut nazar nahi aata —
join sirf is liye chahiye ke user ko ek hi mp4 mile.
"""
import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

# Aakhri frame par bilkul `duration` par seek karne se moviepy kabhi kabhi
# khali/black frame deta hai (clip us waqt khatam ho chuki hoti hai). Ek frame
# peechay hat jao.
_LAST_FRAME_EPSILON = 0.05


def extract_last_frame(video_path: str | Path, dest: str | Path) -> Path:
    """
    `video_path` ka aakhri frame PNG bana kar `dest` par likh do.

    PNG (JPEG nahi) taake compression artifacts agli generation ke start frame
    mein na jayen — wahi frame product ka reference hai.
    """
    from moviepy import VideoFileClip

    video_path, dest = Path(video_path), Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    clip = VideoFileClip(str(video_path))
    try:
        t = max(0.0, (clip.duration or 0.0) - _LAST_FRAME_EPSILON)
        frame = clip.get_frame(t)
    finally:
        clip.close()

    Image.fromarray(frame).save(dest, format="PNG")
    logger.info("video_ads: last frame @%.2fs -> %s", t, dest)
    return dest


def join_segments(segment_paths: list[str | Path], dest: str | Path) -> Path:
    """
    Frame-continuous segments ko ek mp4 bana do.

    Ek hi segment ho (10s wali soorat) to re-encode ka koi faida nahi — file
    seedha move kar dete hain. Re-encode har baar quality thoRi kharab karta hai
    aur waqt bhi leta hai.
    """
    from moviepy import VideoFileClip, concatenate_videoclips

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    paths = [Path(p) for p in segment_paths]

    if len(paths) == 1:
        paths[0].replace(dest)
        return dest

    clips = [VideoFileClip(str(p)) for p in paths]
    try:
        # method="chain" — sab segments ka size/fps ek jaisa hai (ek hi model,
        # ek hi source frame), is liye "compose" ka overhead be-faida hai.
        final = concatenate_videoclips(clips, method="chain")
        final.write_videofile(
            str(dest),
            codec="libx264",
            # audio=False: is module ki har generation audio ke baghair hoti hai
            # (sasta), aur music baad mein alag layer ke tor par lagega.
            audio=False,
            logger=None,
        )
        final.close()
    finally:
        for clip in clips:
            try:
                clip.close()
            except Exception:  # noqa: BLE001 - cleanup kabhi asal error na chhupaye
                pass

    logger.info("video_ads: joined %d segments -> %s", len(paths), dest)
    return dest


def clip_duration(video_path: str | Path) -> float:
    """
    Clip ki asal lambai (seconds).

    Native extend ke baad yeh JAANNA zaroori hai: fal ke docs yeh nahi batate
    ke extend ka output sirf naya hissa hai ya poori (source + extension)
    video. Andaza lagane ke bajaye file naap lete hain — dekho
    engine._absorbs_previous().
    """
    from moviepy import VideoFileClip

    clip = VideoFileClip(str(video_path))
    try:
        return float(clip.duration or 0.0)
    finally:
        clip.close()


def trim_to(video_path: str | Path, seconds: float, dest: str | Path) -> Path:
    """
    Video ka aakhri hissa kaat kar theek `seconds` par le aao.

    Kis liye: Veo ke clip durations sirf 4/6/8 hain — sab JUFT (even). Un ka
    koi bhi jorr taaq (odd) nahi ban sakta, is liye 15s seedha nahi banta.
    16s bana kar 1s tail trim kar dete hain. Yeh JORR par cut nahi hai —
    sirf aakhir se thoRa kam — is liye dekhne mein bilkul mehsoos nahi hota.
    """
    from moviepy import VideoFileClip

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    clip = VideoFileClip(str(video_path))
    try:
        trimmed = clip.subclipped(0, min(seconds, clip.duration or seconds))
        trimmed.write_videofile(str(dest), codec="libx264", audio=False, logger=None)
        trimmed.close()
    finally:
        clip.close()

    logger.info("video_ads: trimmed %s -> %s (%.1fs)", video_path, dest, seconds)
    return dest


def cleanup(paths) -> None:
    """Temp segments/frames hata do. Nakami par khamoshi — yeh best-effort hai."""
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
        except OSError:
            logger.debug("video_ads: could not remove temp file %s", p)
