"""
Veo ka nazar aane wala watermark hatana.

Veo har frame ke neeche-dayen ek chhota sparkle chipka deta hai. Do asal
generations par naapa gaya (1280x720, dono par bilkul aik jagah):

    48 x 48 px @ (1136, 576)  —  dayen aur neeche dono kinaron se theek 96 px

TAREEQA: ffmpeg ka `delogo` filter — box ko us ke kinaron se interpolate kar
deta hai. Koi nayi dependency nahi: ffmpeg wahi hai jo moviepy (imageio-ffmpeg)
ke saath pehle se aata hai, jise end_card.py aur frame_utils.py istemal karte
hain.

── "Reverse alpha blending" kyun NAHI ───────────────────────────────────────
Kaghaz par wo behtar hai. Watermark generative nahi, ek saada alpha composite
hai (o = (1-a)b + aL), yani asli pixel HISAAB se wapas nikala ja sakta hai —
andaza lagaye baghair. Hum ne wo poora bana kar dekha:

    * dono videos se per-pixel alpha map aur logo colour calibrate kiye
      (alpha max ~0.48, logo ~[235,225,224])
    * residue ko sifar par lane ke liye scale bhi empirically tune kiya
      (score -15.7 -> 0.07; solved logo [211,202,202] — jo ek alag,
      mustaqil andaze [214,208,209] se bhi mel khata tha)

Phir bhi natija delogo se BURA nikla: correction ke baad wahan ek STRUCTURED
dhabba reh jata tha (ek taraf kaala, doosri taraf roshan) — yani ghalti sirf
paimane ki nahi, SHAKL ki thi. Ya to logo ka rang poore sparkle par aik jaisa
nahi, ya sub-pixel alignment ka farq hai; sirf DO namoona videos se itni
bareek calibration nahi hoti.

delogo dono test videos par bilkul saaf nikla — detailed floral background par
bhi, smooth gradient par bhi, aur contrast stretch kar ke dekhne par bhi koi
nishan nahi. Watermark chhota hai (48px) aur us ke neeche aam tor par
background hota hai (shallow depth of field), is liye interpolation ka nuqsaan
nazar nahi aata.

Bohat detailed background par kabhi dhundlapan nazar aaye to reverse alpha
blending dobara dekhi ja sakti hai — magar us ke liye kahin zyada namoona
videos chahiyen.

── SynthID ─────────────────────────────────────────────────────────────────
Google ka POSHEEDA watermark (SynthID) is se NAHI jata. Video phir bhi
AI-generated ke tor par pehchani ja sakti hai — yahan sirf nazar aane wala
nishan hatta hai.
"""
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Sab kuch WIDTH ki nisbat se — alag width/height fractions se NAHI. Sparkle
# MURABBA hai; alag fractions lagane par 9:16 frame par box 31x89 ka ban jata
# tha, yani na logo poora aata na sahi jagah saaf hoti.
WATERMARK_SIZE_FRAC = 48 / 1280        # 0.0375
WATERMARK_INSET_FRAC = 96 / 1280       # 0.075  — dayen/neeche kinare se

# Sparkle ke kinare narm (anti-aliased) hain; bilkul tight box chhorne par un
# ka halka sa nishan reh jata hai.
PAD_PX = 2

# Sirf 16:9 par TASDEEQ SHUDA (dono namoona videos wahi thin).
VERIFIED_ASPECT = 16 / 9
ASPECT_TOLERANCE = 0.02

# CRF 18 par re-encode ka farq nazar nahi aata. Audio waise bhi copy hota hai.
DEFAULT_CRF = 18

# ffmpeg par WAQT KI HADD — dono call sites par lazmi.
#
# Ek 10s/720p segment ~8s leta hai (server par naapa gaya), is liye ye hadd
# bohat kushada hai. Maqsad raftaar nahi, LATAK jane se bachao hai: timeout ke
# baghair koi kharab file ffmpeg ko hamesha ke liye rok sakti hai, aur chunke
# ye generation ke baad sync route mein chalta hai, us request ka thread bhi
# wahin phans jata — user ko sirf ek na-khatam hone wala spinner milta.
PROBE_TIMEOUT = 30
ENCODE_TIMEOUT = 300


class WatermarkError(RuntimeError):
    """
    Watermark hatate waqt nakami.

    Caller ke liye ye MOHLIK NAHI honi chahiye: video ban chuki hai aur us ka
    credit kharch ho chuka hai, is liye watermark reh jane par bhi generation
    zaya karna ghalat hai (wahi usool jo end_card par hai).
    """


def _ffmpeg() -> str:
    """moviepy jo ffmpeg istemal karta hai, wohi — koi nayi dependency nahi."""
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def watermark_box(width: int, height: int) -> tuple[int, int, int, int]:
    """(x, y, w, h) — is frame size ke liye watermark ka murabba box + padding."""
    aspect = width / height if height else VERIFIED_ASPECT
    off_spec = abs(aspect - VERIFIED_ASPECT) > ASPECT_TOLERANCE
    if off_spec:
        # Sirf ittila — kaam rukta nahi. Box thora bara le lete hain taake
        # extrapolation thori ghalat ho to bhi logo andar hi rahe.
        logger.warning(
            "veo watermark: aspect %.2f par jagah tasdeeq shuda nahi "
            "(sirf 16:9 naapi gayi hai) — box bara le kar chala rahe hain",
            aspect,
        )

    size = round(WATERMARK_SIZE_FRAC * width)
    inset = round(WATERMARK_INSET_FRAC * width)
    pad = PAD_PX if not off_spec else max(PAD_PX, size // 3)

    # inset kinare se watermark ke BAHRI kinare tak hai, is liye box ka
    # shuruati nuqta nikalne ke liye size bhi ghatana parta hai:
    #     720p -> 1280 - 96 - 48 = 1136   (naapa hua x)
    #             720  - 96 - 48 = 576    (naapa hua y)
    x = width - inset - size - pad
    y = height - inset - size - pad
    w = h = size + 2 * pad

    # delogo ko box ke BAHAR ka pixel chahiye (wahin se interpolate karta hai),
    # is liye box kabhi frame ke kinare ko na chhue.
    x = max(1, min(x, width - 2))
    y = max(1, min(y, height - 2))
    w = max(1, min(w, width - x - 1))
    h = max(1, min(h, height - y - 1))
    return x, y, w, h


def probe_size(path: str | Path, ffmpeg: str | None = None) -> tuple[int, int]:
    """
    (width, height) — ffmpeg ke stderr se.

    ffprobe JAAN BOOJH KAR nahi: wo imageio-ffmpeg ke saath nahi aata, aur usay
    maangna server par ek nayi dependency ban jata.
    """
    ffmpeg = ffmpeg or _ffmpeg()
    out = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True,
                         timeout=PROBE_TIMEOUT).stderr
    for line in out.splitlines():
        if "Video:" not in line:
            continue
        for token in line.split(","):
            head = token.strip().split(" ")[0]
            if "x" in head:
                a, _, b = head.partition("x")
                if a.isdigit() and b.isdigit():
                    return int(a), int(b)
    raise WatermarkError(f"video ki resolution nahi mili: {path}")


def remove_watermark(src: str | Path, dst: str | Path,
                     ffmpeg: str | None = None, crf: int = DEFAULT_CRF) -> Path:
    """`src` se watermark hata kar `dst` par likho. Audio copy hota hai."""
    ffmpeg = ffmpeg or _ffmpeg()
    src, dst = Path(src), Path(dst)
    w, h = probe_size(src, ffmpeg)
    x, y, bw, bh = watermark_box(w, h)

    cmd = [
        ffmpeg, "-v", "error", "-y", "-i", str(src),
        "-vf", f"delogo=x={x}:y={y}:w={bw}:h={bh}",
        "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
        # Audio dobara encode nahi hota — re-encode sirf video ka.
        "-c:a", "copy", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(dst),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True,
                         timeout=ENCODE_TIMEOUT)
    if res.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
        raise WatermarkError(
            f"ffmpeg delogo nakaam ({res.returncode}): {res.stderr[-400:]}")

    logger.info("veo watermark removed: %s (%dx%d, box %d,%d %dx%d)",
                src.name, w, h, x, y, bw, bh)
    return dst


def strip_in_place(path: str | Path) -> bool:
    """
    Usi file par watermark hata do. Kaamyabi par True.

    Nakami par ye EXCEPTION NAHI phenkta — sirf False deta hai aur log likhta
    hai. Wajah: yeh generation ke BAAD chalta hai, jab credit kharch ho chuka
    hota hai. Us waqt watermark reh jana bura hai, magar poori video zaya kar
    dena us se kahin bura.

    Asal file tab tak nahi badalti jab tak nayi file mukammal na ho jaye — beech
    mein nakami par purani file jyun ki tyun rehti hai.
    """
    # Path banana bhi try ke ANDAR — with_name() ajeeb raste par ValueError
    # de sakta hai, aur is function se koi exception bahar nahi jani chahiye.
    tmp = None
    try:
        path = Path(path)
        tmp = path.with_name(f"{path.stem}_nowm{path.suffix}")
        remove_watermark(path, tmp)
        tmp.replace(path)
        return True
    except Exception as e:  # noqa: BLE001 — dekho docstring
        # Yahan se koi exception BAHAR nahi jani chahiye. engine.run_plan ka
        # generic handler har exception ko VideoAdServiceError (502) bana deta
        # hai — yani watermark ki safai ki nakami poori bani hui video zaya
        # kar deti, halanke us ka credit lag chuka hota hai.
        try:
            logger.error("veo watermark hataya nahi ja saka (%s) — video "
                         "watermark ke saath hi rakhi ja rahi hai: %s: %s",
                         path, type(e).__name__, e)
            if tmp is not None:
                tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001 — safai bhi nakaam ho to bhi chup
            pass
        return False
