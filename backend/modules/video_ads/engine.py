"""
Provider-agnostic plan executor.

Kling aur Veo dono ki generation ka DHANCHA ek hi hai — sirf model, payload ki
shakl, aur extension ka tareeqa alag hai. Woh saara farq provider spec mein
rehta hai (kling_service.py / veo_service.py), aur yahan ka code kisi provider
ka naam tak nahi jaanta.

── Ek "plan" kya hai ────────────────────────────────────────────────────────
Plan steps ki list hai; har step ek billable generation hai:

    {"seconds": 8, "mode": "base"}            pehla segment (source image se)
    {"seconds": 4, "mode": "last_frame"}      pichle segment ke AAKHRI FRAME se
    {"seconds": 7, "mode": "native_extend"}   provider ka apna extend endpoint

Plan ke saath `trim_to` bhi ho sakta hai (dekho neeche).

── Do extension mechanisms kyun ─────────────────────────────────────────────
"last_frame" har provider par chalta hai: pichli clip ka aakhri frame nikal kar
agli generation ka start image bana do. Segment ka pehla frame pichle ka aakhri
frame hota hai, is liye jorr nazar nahi aata.

"native_extend" sirf un providers par hai jin ka fal par apna extend endpoint
hai (Veo). Woh video ka URL leta hai, frame ka nahi — is liye us ke liye pichle
segment ka REMOTE fal URL sambhal kar rakha jata hai.
"""
import logging
import tempfile
from pathlib import Path

from modules.video_ads import fal_client, frame_utils, veo_watermark
from modules.video_ads.fal_client import VideoAdServiceError

logger = logging.getLogger(__name__)

# native_extend ke baad output source+extension dono par mushtamil ho sakta hai
# (ya sirf naya hissa). Faisla naap kar hota hai, aur naap mein encoding ki wajah
# se thoRa farq aata hai — is liye itni gunjaish.
_DURATION_TOLERANCE = 1.5


def _absorbs_previous(measured: float, previous_total: float, step_seconds: int) -> bool:
    """
    native_extend ke output ne pichle segments ko apne andar le liya ya nahi.

    fal ke docs yeh nahi likhte ke extend ka result sirf naya hissa hai ya
    poori jori hui video. Dono soortein mumkin hain, aur ghalat maan lene ka
    natija ya to aadhi video hai ya double. Is liye file ki asal lambai naap
    kar faisla karte hain: agar woh (pichla kul + is step) ke qareeb hai to
    output mein pichla sab kuch shamil hai.
    """
    combined = previous_total + step_seconds
    return abs(measured - combined) <= _DURATION_TOLERANCE and measured > step_seconds + _DURATION_TOLERANCE


def run_plan(
    spec: dict,
    plan: dict,
    image_ref: str,
    base_prompt: str,
    extension_prompt: str,
    api_key: str,
) -> dict:
    """
    Ek plan chala kar mukammal video ka local path do.

    `spec` mein provider ka farq rehta hai:
        provider            : log/error ke liye naam
        model_id            : base generation ka fal model
        build_payload       : (image_ref, prompt, seconds) -> dict
        extend_model_id     : native extend ka fal model (ya None)
        build_extend_payload: (video_url, prompt, seconds) -> dict (ya None)

    Return: {"video_path", "segments", "duration_seconds"}

    JAAN BOOJH KAR koi auto-retry nahi — har step par paisa lagta hai.
    """
    steps = plan["steps"]
    trim_target = plan.get("trim_to")

    work_dir = Path(tempfile.mkdtemp(prefix="video_ad_"))
    segment_paths: list[Path] = []
    temp_files: list[Path] = []

    try:
        current_image = image_ref     # last_frame / base ke liye
        last_remote_url: str | None = None   # native_extend ke liye
        produced_seconds = 0          # ab tak ki kul lambai (naap ke liye)

        for i, step in enumerate(steps):
            seconds = step["seconds"]
            mode = step["mode"]

            if mode == "native_extend":
                if not spec.get("extend_model_id") or not spec.get("build_extend_payload"):
                    raise VideoAdServiceError(
                        "This video length is not available for the selected plan right now. "
                        "Please choose a different length.",
                        provider=spec["provider"],
                        detail=f"plan step {i} needs native_extend but "
                               f"{spec['provider']} has no extend endpoint configured",
                    )
                if not last_remote_url:
                    raise VideoAdServiceError(
                        "Could not continue the video. Please try again.",
                        provider=spec["provider"],
                        detail=f"plan step {i}: native_extend with no previous remote url",
                    )
                model_id = spec["extend_model_id"]
                payload = spec["build_extend_payload"](
                    last_remote_url, extension_prompt, seconds
                )
            else:
                model_id = spec["model_id"]
                prompt = base_prompt if mode == "base" else extension_prompt
                payload = spec["build_payload"](current_image, prompt, seconds)

            result = fal_client.run_model(model_id, payload, api_key)
            video_url = fal_client.extract_video_url(result)
            last_remote_url = video_url

            segment_path = work_dir / f"segment_{i}.mp4"
            fal_client.download_video(video_url, segment_path)

            # ── Provider ka watermark — HAR SEGMENT PAR, foran ───────────
            #
            # Ye yahan hona LAZMI hai, sirf aakhri joint video par nahi.
            # Neeche (dekho `mode == "last_frame"`) is segment ka aakhri frame
            # nikal kar AGLI generation ka start image banta hai. Watermark us
            # frame mein reh jaye to agla segment usay scene ka HISSA samajh
            # kar dobara bana deta hai — aur Veo apna naya watermark us ke
            # oopar bhi laga deta. Us soorat mein wo overlay nahi rehta, asal
            # tasveer ban jata hai, aur phir kisi tarah nahi hatta.
            #
            # Nakami mohlik nahi: generation ka paisa lag chuka hai, is liye
            # watermark reh jana video zaya karne se behtar hai (wahi usool jo
            # end card par hai). strip_in_place khud log likh kar False deta
            # hai, exception nahi phenkta.
            if spec.get("watermark") == "veo":
                veo_watermark.strip_in_place(segment_path)

            if mode == "native_extend":
                measured = frame_utils.clip_duration(segment_path)
                if _absorbs_previous(measured, produced_seconds, seconds):
                    # Extend ne poori video wapas di — pichle segments ab
                    # ISI file mein hain, warna woh dobara jur kar double ho
                    # jate.
                    logger.info(
                        "%s: extend returned the full %.1fs video; replacing %d earlier segment(s)",
                        spec["provider"], measured, len(segment_paths),
                    )
                    frame_utils.cleanup(segment_paths)
                    segment_paths = [segment_path]
                    produced_seconds = measured
                else:
                    segment_paths.append(segment_path)
                    produced_seconds += measured
            else:
                segment_paths.append(segment_path)
                produced_seconds += seconds

            # Agla step last_frame hai to is segment ka aakhri frame chahiye.
            next_step = steps[i + 1] if i + 1 < len(steps) else None
            if next_step and next_step["mode"] == "last_frame":
                frame_path = work_dir / f"frame_{i}.png"
                frame_utils.extract_last_frame(segment_path, frame_path)
                temp_files.append(frame_path)
                current_image = fal_client.file_to_data_uri(frame_path)

        final_path = fal_client.new_video_path()
        frame_utils.join_segments(segment_paths, final_path)

        if trim_target:
            # Joint file ko theek maangi hui lambai par le aao (dekho
            # frame_utils.trim_to — Veo ke even-only durations ki wajah se).
            trimmed = work_dir / "trimmed.mp4"
            frame_utils.trim_to(final_path, trim_target, trimmed)
            trimmed.replace(final_path)

    except VideoAdServiceError:
        raise
    except Exception as e:
        # moviepy/ffmpeg/Pillow ki koi bhi nakami. Generation ka paisa lag
        # CHUKA hai, is liye log mein poori baat honi chahiye.
        logger.exception("video_ads: post-processing failed (provider=%s)", spec["provider"])
        raise VideoAdServiceError(
            "The video clips were generated but could not be assembled on the server. "
            "Please try again.",
            provider=spec["provider"],
            detail=f"{type(e).__name__}: {e}",
        )
    finally:
        frame_utils.cleanup(segment_paths + temp_files)
        try:
            work_dir.rmdir()
        except OSError:
            pass

    return {
        "video_path": str(final_path),
        "segments": len(steps),
        "duration_seconds": trim_target or sum(s["seconds"] for s in steps),
    }
