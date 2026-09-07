import uuid
from pathlib import Path
from moviepy import ImageClip, CompositeVideoClip

OUTPUT_DIR = Path("generated_ads/videos")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_video_ad(image_path: str, product_name: str, duration: int = 5) -> str:
    """
    Animates a static ad image into a short video ad (Ken Burns zoom effect).
    """
    clip = ImageClip(image_path).with_duration(duration)

    # Ken Burns zoom-in effect
    zoomed = clip.resized(lambda t: 1 + 0.04 * t)
    zoomed = zoomed.with_position("center")

    final = CompositeVideoClip([zoomed], size=clip.size)

    filename = f"{uuid.uuid4().hex}.mp4"
    filepath = OUTPUT_DIR / filename

    final.write_videofile(
        str(filepath),
        fps=24,
        codec="libx264",
        audio=False,
        logger=None
    )

    return str(filepath)