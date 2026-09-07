"""
YouTube comments as a SUPPLEMENTARY feedback source.

Ye Trustpilot ki jagah nahi leta — uske SAATH chalta hai. Jo comments yahan se
aate hain wo bilkul usi shape mein hote hain jo review_platforms.py deta hai,
is liye wahi predict_batch + Groq pipeline un par bina kisi tabdeeli ke chalti hai.

QUOTA (rozana 10,000 units):
    search.list       = 100 units  <- isse bachte hain
    channels.list     =   1 unit
    playlistItems.list=   1 unit   (50 videos tak)
    videos.list       =   1 unit   (50 ids tak)
    commentThreads    =   1 unit   (100 comments tak)

Aik brand ka kharcha:
    1  channel resolve      (channels.list)
  + 1  uploads playlist     (playlistItems.list, 50 recent videos)
  + 1  view/comment counts  (videos.list — isi se "most popular" locally sort
                             hota hai, search.list?order=viewCount ke 100 units
                             ke bajaye)
  + N  comments             (sirf un videos par jin par commentCount > 0)
  = ZYADA SE ZYADA ~13 units per brand.

Sab kuch defensive hai: koi bhi API error, quotaExceeded, commentsDisabled, ya
channel na milna — sirf log hota hai. Jo mila wo return hota hai (chahe khali
list ho). Ye module KABHI raise nahi karta, taake Trustpilot ka analysis chalta rahe.
"""

import logging
import os
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://www.googleapis.com/youtube/v3"

# .env mein maujood exact naam.
KEY_ENV = "YOUTUBE_API_KEY"

# Config — env se override ho sakta hai.
RECENT_VIDEOS      = int(os.getenv("YOUTUBE_RECENT_VIDEOS",      "5"))
POPULAR_VIDEOS     = int(os.getenv("YOUTUBE_POPULAR_VIDEOS",     "5"))
COMMENTS_PER_VIDEO = int(os.getenv("YOUTUBE_COMMENTS_PER_VIDEO", "100"))

# playlistItems/videos ek call mein 50 tak deta hai — isi se recent aur popular
# dono select ho jate hain.
VIDEO_POOL_SIZE = 50
REQUEST_TIMEOUT = 20

# search.list 100 units ka hai (baqi sab 1). Ise sirf legacy /c/ aur /user/
# URLs ke liye use karte hain — dekho resolve_channel(). Quota tang ho to
# YOUTUBE_ALLOW_SEARCH_FALLBACK=0 se bilkul band kiya ja sakta hai.
ALLOW_SEARCH_FALLBACK = os.getenv("YOUTUBE_ALLOW_SEARCH_FALLBACK", "1") not in ("0", "false", "False")

# Bohat chhote comments ("nice", "❤️") sentiment ke liye bekaar hain aur Groq ka
# token budget kha jate hain.
MIN_COMMENT_CHARS = 8

# ── Third-party review videos (naya source) ──────────────────────────────
# Brand ke APNE channel ke ilawa, un logon ke videos jinhon ne is brand ka
# review banaya. Wo raaye brand ke apne channel se kahin zyada be-laag hoti hai.
#
# QUOTA: search.list 100 units ka hai (baqi endpoints 1). Is liye default par
# sirf EK query chalti hai. Har extra query 100 units aur legi — rozana budget
# 10,000 hai.
REVIEW_SEARCH_ENABLED = os.getenv("YOUTUBE_REVIEW_SEARCH", "1") not in ("0", "false", "False")
REVIEW_QUERY_TEMPLATES = [
    t.strip()
    for t in os.getenv("YOUTUBE_REVIEW_QUERIES", "{brand} review").split("|")
    if t.strip()
]
# search.list ek call mein 50 tak deta hai — 5 lein ya 50, kharcha wahi 100.
REVIEW_SEARCH_RESULTS = int(os.getenv("YOUTUBE_REVIEW_SEARCH_RESULTS", "50"))
# In mein se kitni videos parhni hain (har video 1+ unit).
REVIEW_VIDEOS_TO_READ = int(os.getenv("YOUTUBE_REVIEW_VIDEOS", "12"))

# Ek video se zyada se zyada kitni comments. commentThreads ek page mein 100
# deta hai aur har page SIRF 1 unit ka hai — yani gehrai bohat sasti hai.
# Mehnga hissa videos DHOONDNA hai, unhein parhna nahi.
MAX_COMMENTS_PER_VIDEO = int(os.getenv("YOUTUBE_MAX_COMMENTS_PER_VIDEO", "300"))


# ── Relevance filter ─────────────────────────────────────────────────────
# NAAP KAR LAGAYA GAYA. Gymshark ke 12 third-party review videos se 1,152
# comments aayin; un mein se sirf 37% ne brand ya kisi product/khareedari
# ki baat ki. Baqi 63% mazaq, tags, aur video par tabsira thay — ek comedy
# "TIER LIST" video akele 246 comments laya.
#
# Bina filter ke wo shor asli raaye ko daba deta hai: sentiment counts
# un comments se bhar jate hain jin ka brand se koi taalluq hi nahi.
_SPAM_RE = re.compile(
    r"(https?://|www\.|subscribe|check out my|my channel|promo ?code|discount ?code|"
    r"link in bio|dm me)",
    re.I,
)

# Product/khareedari ki lughat — English + Roman Urdu. Roman Urdu jaan boojh
# kar shamil hai: model bilingual (XLM-R) hai aur Pakistani brands par
# comments aksar Roman Urdu mein hoti hain.
_PRODUCT_WORDS = [
    # English — product aur khareedari
    "size", "sizing", "fit", "fits", "fitting", "fabric", "material", "quality",
    "stitch", "stitching", "shorts", "legging", "leggings", "top", "shirt",
    "tshirt", "hoodie", "jacket", "dress", "suit", "kurta", "pants", "bra",
    "price", "priced", "pricing", "expensive", "cheap", "affordable", "worth",
    "money", "cost", "shipping", "delivery", "deliver", "return", "refund",
    "exchange", "order", "ordered", "bought", "buy", "buying", "purchase",
    "wash", "washed", "shrink", "shrunk", "squat proof", "seamless", "stretch",
    "comfort", "comfortable", "comfy", "wear", "wearing", "wore", "colour",
    "color", "design", "customer service", "packaging", "recommend",
    # Roman Urdu
    "acha", "achi", "bura", "buri", "bakwas", "zabardast", "behtareen",
    "mehnga", "mehngi", "sasta", "sasti", "paisa", "paise", "qeemat",
    "kapra", "kapray", "silai", "size", "asli", "nakli", "ghatiya",
]
_PRODUCT_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in sorted(set(_PRODUCT_WORDS), key=len, reverse=True)) + r")\b",
    re.I,
)

FILTER_IRRELEVANT = os.getenv("YOUTUBE_FILTER_IRRELEVANT", "1") not in ("0", "false", "False")

# Pehli page ke baad is se kam relevance ho to aage paginate nahi karte.
MIN_PAGE_YIELD = float(os.getenv("YOUTUBE_MIN_PAGE_YIELD", "0.15"))


def _flatten(text: str) -> str:
    """lowercase + sirf a-z0-9. "GYM SHARK haul" -> "gymsharkhaul" """
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def brand_tokens(brand_name: str) -> List[str]:
    """
    Brand ka naam match karne ke liye normalise karo.

    Pehle yahan ek ANDAZE wala split tha jo naam do tukron mein toRta:
    "Gymshark" -> "gym shark" (jo ittefaqan theek tha) magar "Alkaram" ->
    "alk aram" aur "Sapphire" -> "sap phire" (jo bekaar hain). Wo guess hata
    diya — _flatten() dono taraf se spaces nikaal deta hai, is liye
    "GYM SHARK haul" khud ba khud "gymshark" par match ho jata hai.
    """
    flat = _flatten(brand_name)
    return [flat] if len(flat) >= 3 else []


def title_mentions_brand(title: str, tokens: List[str]) -> bool:
    """
    Video ka TITLE brand ka zikr karta hai ya nahi — HASHTAGS chhod kar.

    Hashtags jaan boojh kar hata dete hain. Creators reach ke liye har
    mashhoor brand tag kar dete hain: ek comedy video ka title tha
        "THE GYM CLOTHING TIER LIST!  #bodybuilder #gym #gymshark #zyzz"
    Us mein "gymshark" sirf hashtag mein tha, aur us akele video se 246
    mazaqiya comments Gymshark ke sentiment mein chali jatin. Hashtags hata
    kar title reh jata hai "THE GYM CLOTHING TIER LIST!" — brand hai hi nahi.

    Iske bar-aks ye title asli hai aur rehna chahiye:
        "IN DEPTH HONEST TRY ON GYMWEAR REVIEW | ALPHALETE | GYMSHARK"
    """
    if not title:
        return False
    flat = _flatten(re.sub(r"#\S+", " ", title))
    return any(tok in flat for tok in tokens)


def is_relevant_comment(text: str, tokens: List[str]) -> bool:
    """
    Comment brand ya kisi product/khareedari ki baat karta hai ya nahi.

    Spam pehle nikaalte hain (self-promo links video ke neeche aam hain),
    phir brand ka zikr, phir product ki lughat.
    """
    if not text:
        return False
    if _SPAM_RE.search(text):
        return False
    # Brand ka match FLATTEN kar ke — "gym shark", "Gym-Shark" aur
    # "GYMSHARK" teenon chalte hain. Bare "gym" phir bhi match nahi
    # karta, kyunke poora "gymshark" darkar hai.
    if any(tok in _flatten(text) for tok in tokens):
        return True
    return bool(_PRODUCT_RE.search(text))


class QuotaTracker:
    """Sirf logging ke liye — kitne units kharch hue."""

    def __init__(self) -> None:
        self.units = 0
        self.calls: Dict[str, int] = {}

    def spend(self, endpoint: str, units: int = 1) -> None:
        self.units += units
        self.calls[endpoint] = self.calls.get(endpoint, 0) + 1

    def __str__(self) -> str:
        detail = ", ".join(f"{k}x{v}" for k, v in sorted(self.calls.items()))
        return f"{self.units} units ({detail})"


def get_api_key() -> Optional[str]:
    key = (os.getenv(KEY_ENV) or "").strip()
    if not key:
        logger.warning("%s not set — YouTube source will be skipped.", KEY_ENV)
        return None
    return key


# ── URL parsing ───────────────────────────────────────────────────────────────

def extract_channel_ref(channel_url: str) -> Optional[Tuple[str, str]]:
    """
    YouTube URL se pata karo ke channel kis tarah dhoondna hai.

    Return ('id'|'handle'|'username'|'search', value) ya None.

    Handled forms:
        /channel/UCxxxx           -> ('id', 'UCxxxx')        sab se sasta
        /@handle                  -> ('handle', '@handle')
        /c/CustomName             -> ('handle', 'CustomName')  (forUsername in par
                                     kaam nahi karta — test kar ke dekha)
        /user/LegacyName          -> ('username', 'LegacyName')
        youtu.be / watch?v=       -> None (video link hai, channel nahi)
    """
    if not channel_url or not isinstance(channel_url, str):
        return None

    url = channel_url.strip()
    if not url:
        return None
    if "youtube.com" not in url.lower() and "youtu.be" not in url.lower():
        return None

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        parsed = urlparse(url)
    except ValueError:
        logger.warning("Unparseable YouTube URL: %r", channel_url)
        return None

    path = (parsed.path or "").strip("/")
    if not path:
        return None

    parts = [p for p in path.split("/") if p]
    if not parts:
        return None

    head = parts[0]

    # /channel/UCxxxx  — direct id, sab se sasta raasta
    if head == "channel" and len(parts) > 1:
        return ("id", parts[1])

    # /@handle
    if head.startswith("@"):
        return ("handle", head)

    # /c/Name  aur  /user/Name
    if head in ("c", "user") and len(parts) > 1:
        return ("username" if head == "user" else "handle", parts[1])

    # /watch?v=... ya /shorts/... — ye channel link nahi hai
    if head in ("watch", "shorts", "playlist", "embed"):
        return None

    # Bare /SomeName — modern YouTube ise handle ki tarah treat karta hai
    return ("handle", head)


def _uploads_from_channel_id(channel_id: str) -> str:
    """
    Uploads playlist id channel id se derive hoti hai: UC... -> UU...
    (YouTube ka documented convention.) Fallback ke taur par use hoti hai
    agar contentDetails na mile.
    """
    if channel_id.startswith("UC"):
        return "UU" + channel_id[2:]
    return channel_id


# ── low-level API helper ──────────────────────────────────────────────────────

def _api_get(
    endpoint: str, params: Dict, key: str, quota: QuotaTracker, cost: int = 1
) -> Optional[Dict]:
    """
    Ek API call. Har error handle hota hai — None return hota hai, raise nahi.

    Khaas taur par pehchane jate hain:
        quotaExceeded      -> din ka budget khatam
        commentsDisabled   -> is video par comments band hain
        videoNotFound      -> video hat gaya / private
    """
    params = {**params, "key": key}
    try:
        resp = requests.get(
            f"{API_BASE}/{endpoint}", params=params, timeout=REQUEST_TIMEOUT
        )
    except requests.exceptions.RequestException as e:
        logger.warning("YouTube %s request failed: %s", endpoint, e)
        return None

    quota.spend(endpoint, cost)

    if resp.status_code == 200:
        try:
            return resp.json()
        except ValueError:
            logger.warning("YouTube %s returned non-JSON body", endpoint)
            return None

    # Error ki asli wajah nikalo
    reason = ""
    message = ""
    try:
        err = resp.json().get("error", {})
        message = err.get("message", "")
        errors = err.get("errors") or []
        if errors:
            reason = errors[0].get("reason", "")
    except ValueError:
        message = resp.text[:200]

    if reason == "quotaExceeded":
        # Ye poore din ke liye hai — caller ko batana zaroori hai taake baqi
        # calls bhi na kare.
        logger.error(
            "YouTube API daily quota exhausted (quotaExceeded). "
            "Skipping YouTube for this analysis."
        )
        raise _QuotaExceeded()

    if reason in ("commentsDisabled", "videoNotFound"):
        # Ye normal hai — chup-chaap skip karo (debug level).
        logger.debug("YouTube %s skipped (%s)", endpoint, reason)
        return None

    logger.warning(
        "YouTube %s error %s (%s): %s",
        endpoint,
        resp.status_code,
        reason or "unknown",
        message[:160],
    )
    return None


class _QuotaExceeded(Exception):
    """Internal — sirf is module ke andar quota khatam hone ka signal."""


# ── channel resolution ────────────────────────────────────────────────────────

def resolve_channel(
    channel_url: str, key: str, quota: QuotaTracker
) -> Optional[Tuple[str, str]]:
    """
    Channel URL -> (channel_id, uploads_playlist_id).  Nahi mila to None.

    Sab se sasta raasta pehle. search.list (100 units) sirf tab jab aur koi
    tareeqa na bache.
    """
    ref = extract_channel_ref(channel_url)
    if not ref:
        logger.info("Not a usable YouTube channel URL: %r", channel_url)
        return None

    kind, value = ref
    logger.info("Resolving YouTube channel: %s=%r (from %s)", kind, value, channel_url)

    # channels.list ke liye param map — sab 1 unit
    attempts: List[Tuple[str, str]] = []
    if kind == "id":
        attempts.append(("id", value))
    elif kind == "handle":
        attempts.append(("forHandle", value if value.startswith("@") else "@" + value))
        # kuch purane /c/ names asal mein legacy usernames hain
        attempts.append(("forUsername", value.lstrip("@")))
    elif kind == "username":
        attempts.append(("forUsername", value))
        # /user/ links aksar ab handles ban chuke hain
        attempts.append(("forHandle", "@" + value.lstrip("@")))

    for param, val in attempts:
        data = _api_get(
            "channels", {"part": "id,contentDetails", param: val}, key, quota
        )
        items = (data or {}).get("items") or []
        if items:
            cid = items[0]["id"]
            uploads = (
                items[0]
                .get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads")
            ) or _uploads_from_channel_id(cid)
            logger.info("Resolved channel %s via %s (uploads=%s)", cid, param, uploads)
            return cid, uploads

    # ── search.list (100 units) — SIRF genuinely ambiguous case mein ─────────
    #
    # Ye 100 units ka hai, yani poore din ke budget (10,000) ka 1%. Is liye
    # ise sirf tab chalate hain jab channel WAQAI kisi aur tareeqe se nahi mil
    # sakta:
    #
    #   /c/Name aur /user/Name  -> ye purane vanity URLs hain. In par
    #      forUsername aur forHandle dono fail ho sakte hain CHAHE channel
    #      mojood ho. Yehi asli ambiguous case hai -> search justified.
    #
    #   /channel/UC...  -> id lookup authoritative hai. 0 items ka matlab id
    #      ghalat hai; UC-string ko search karna bekaar hai. -> NO search.
    #
    #   /@handle  -> forHandle authoritative hai. Handle nahi hai to nahi hai.
    #      -> NO search.
    #
    # Warna ek typo'd YouTube URL har analysis par 102 units kha jata (test
    # mein dekha), yani ~98 analyses mein poora din ka quota khatam.
    if kind not in ("username",) and not (kind == "handle" and not value.startswith("@")):
        logger.info(
            "Could not resolve YouTube channel for %r (%s lookup is authoritative "
            "— not spending 100 units on search.list). Quota used: %s",
            channel_url,
            kind,
            quota,
        )
        return None

    if not ALLOW_SEARCH_FALLBACK:
        logger.info(
            "Could not resolve %r and search.list fallback is disabled "
            "(YOUTUBE_ALLOW_SEARCH_FALLBACK=0).",
            channel_url,
        )
        return None

    logger.warning(
        "Legacy vanity URL %r did not resolve cheaply — falling back to "
        "search.list (100 quota units)",
        channel_url,
    )
    data = _api_get(
        "search",
        {"part": "snippet", "q": value.lstrip("@"), "type": "channel", "maxResults": 1},
        key,
        quota,
        cost=100,
    )
    items = (data or {}).get("items") or []
    if items:
        cid = items[0]["snippet"]["channelId"]
        logger.info("Resolved channel %s via search.list fallback", cid)
        return cid, _uploads_from_channel_id(cid)

    logger.info("Could not resolve YouTube channel for %r", channel_url)
    return None


# ── video selection ───────────────────────────────────────────────────────────

def select_videos(
    uploads_playlist: str, key: str, quota: QuotaTracker
) -> List[Dict]:
    """
    Uploads playlist se videos chuno: RECENT_VIDEOS sab se naye +
    POPULAR_VIDEOS sab se zyada dekhe gaye. Duplicates hata kar.

    Popularity ke liye search.list?order=viewCount (100 units) ki zaroorat nahi —
    playlistItems (1u) + videos.list statistics (1u) se locally sort kar lete hain.
    """
    # 1 unit — uploads playlist reverse-chronological hoti hai
    data = _api_get(
        "playlistItems",
        {
            "part": "contentDetails,snippet",
            "playlistId": uploads_playlist,
            "maxResults": VIDEO_POOL_SIZE,
        },
        key,
        quota,
    )
    items = (data or {}).get("items") or []
    if not items:
        logger.info("No videos found in uploads playlist %s", uploads_playlist)
        return []

    ordered_ids: List[str] = []
    titles: Dict[str, str] = {}
    for it in items:
        vid = it.get("contentDetails", {}).get("videoId")
        if vid and vid not in titles:
            ordered_ids.append(vid)
            titles[vid] = it.get("snippet", {}).get("title", "")

    if not ordered_ids:
        return []

    # 1 unit — 50 ids tak ke statistics
    stats_data = _api_get(
        "videos",
        {"part": "statistics", "id": ",".join(ordered_ids[:VIDEO_POOL_SIZE])},
        key,
        quota,
    )
    stats: Dict[str, Dict[str, int]] = {}
    for v in (stats_data or {}).get("items") or []:
        s = v.get("statistics", {})
        stats[v["id"]] = {
            "views": int(s.get("viewCount", 0) or 0),
            "comments": int(s.get("commentCount", 0) or 0),
        }

    def entry(vid: str) -> Dict:
        st = stats.get(vid, {"views": 0, "comments": 0})
        return {
            "video_id": vid,
            "title": titles.get(vid, ""),
            "views": st["views"],
            "comments": st["comments"],
        }

    recent = [entry(v) for v in ordered_ids[:RECENT_VIDEOS]]

    popular = sorted(
        (entry(v) for v in ordered_ids), key=lambda e: e["views"], reverse=True
    )[:POPULAR_VIDEOS]

    # Dedupe — order barqarar rakhte hue (recent pehle)
    seen = set()
    selected: List[Dict] = []
    for e in recent + popular:
        if e["video_id"] not in seen:
            seen.add(e["video_id"])
            selected.append(e)

    logger.info(
        "Selected %d unique videos (%d recent + %d popular, %d overlap)",
        len(selected),
        len(recent),
        len(popular),
        len(recent) + len(popular) - len(selected),
    )
    return selected


# ── comments ──────────────────────────────────────────────────────────────────

def fetch_video_comments(
    video: Dict,
    key: str,
    quota: QuotaTracker,
    max_comments: int = None,
    relevance_tokens: List[str] = None,
) -> List[Dict]:
    """
    Ek video ke top-level comments (replies nahi).

    PAGINATION: pehle sirf ek page (100 comments) aati thi aur bas. Ab
    MAX_COMMENTS_PER_VIDEO tak paginate karte hain — har page SIRF 1 unit ka
    hai, yani 300 comments ka kul kharcha 3 units. Sentiment ke liye zyada
    comments seedha behtar hai: chhote sample par do gusse waale comments
    poori tasveer bigaad dete hain.

    Jin videos par commentCount 0 hai un par call hi nahi karte.
    """
    vid = video["video_id"]
    if video.get("comments", 0) == 0:
        logger.debug("Skipping %s — commentCount is 0 (saves 1 unit)", vid)
        return []

    limit = max_comments or MAX_COMMENTS_PER_VIDEO
    out: List[Dict] = []
    page_token = None
    pages = 0
    kept_total = 0
    seen_total = 0

    while len(out) < limit:
        params = {
            "part": "snippet",
            "videoId": vid,
            "maxResults": 100,
            "order": "relevance",
            "textFormat": "plainText",
        }
        if page_token:
            params["pageToken"] = page_token

        data = _api_get("commentThreads", params, key, quota)
        if not data:
            break
        pages += 1

        for item in data.get("items", []):
            try:
                snip = item["snippet"]["topLevelComment"]["snippet"]
            except (KeyError, TypeError):
                continue
            text = (snip.get("textDisplay") or "").strip()
            if len(text) < MIN_COMMENT_CHARS:
                continue
            seen_total += 1
            # Relevance YAHIN — pehle ye baad mein hota tha, yani har
            # comment do dafa dekha jata. Yahan karne se video ka
            # "yield" bhi maloom ho jata hai (dekho neeche).
            if relevance_tokens is not None and not is_relevant_comment(
                text, relevance_tokens
            ):
                continue
            kept_total += 1
            out.append(
                {
                    "content": text,
                    # source/platform video se aate hain, taake apne channel ki
                    # comments aur third-party review videos alag pehchane jayen.
                    "source": video.get("source", "youtube"),
                    "platform": video.get("platform", "youtube"),
                    "is_real": True,
                    "video_id": vid,
                    "video_title": video.get("title", ""),
                    "channel_title": video.get("channel_title", ""),
                    "author": snip.get("authorDisplayName", ""),
                    "likes": int(snip.get("likeCount", 0) or 0),
                    "published_at": snip.get("publishedAt", ""),
                }
            )
            if len(out) >= limit:
                break

        page_token = data.get("nextPageToken")
        if not page_token:
            break

        # ADAPTIVE PAGINATION — kam yield wali video par aage nahi jate.
        #
        # Kuch videos par 90% comments mazaq ya emoji hote hain. Un ki
        # agli page laane ka matlab hai 1 unit kharch kar ke tqreeban
        # kuch na milna. Pehli page ke baad agar relevance
        # MIN_PAGE_YIELD se neeche ho to wahin rukk jate hain — quota
        # un videos par bachta hai jahan waqai raaye mil rahi hai.
        if relevance_tokens is not None and seen_total >= 50:
            ratio = kept_total / seen_total
            if ratio < MIN_PAGE_YIELD:
                logger.info(
                    "  %s -> stopping early, only %.0f%% relevant (saves quota)",
                    vid, 100 * ratio,
                )
                break

    logger.info(
        "  %s -> %d comments across %d page(s) (%s)",
        vid, len(out), pages, video.get("title", "")[:40],
    )
    return out


def search_review_videos(
    brand_name: str, key: str, quota: QuotaTracker, exclude_channel_id: str = None
) -> List[Dict]:
    """
    Doosron ke banaye review videos dhoondo — brand ka APNA channel chhod kar.

    Kyun: brand ke apne channel par comments aksar fans ki hoti hain aur
    marketing ke gird ghoomti hain. "<brand> review" par doosre logon ke
    videos mein khareedaron ki asli raaye hoti hai — achhi aur buri dono.

    QUOTA: har query 100 units.
    """
    if not brand_name:
        return []

    found: Dict[str, Dict] = {}
    tokens = brand_tokens(brand_name)
    skipped_offtopic = 0
    for template in REVIEW_QUERY_TEMPLATES:
        query = template.format(brand=brand_name)
        data = _api_get(
            "search",
            {
                "part": "snippet",
                "q": query,
                "type": "video",
                "order": "relevance",
                "maxResults": min(REVIEW_SEARCH_RESULTS, 50),
            },
            key,
            quota,
            cost=100,
        )
        if not data:
            continue
        for item in data.get("items", []):
            vid = (item.get("id") or {}).get("videoId")
            snip = item.get("snippet") or {}
            if not vid or vid in found:
                continue
            # Brand ka apna channel chhodo — wo doosre source se pehle hi aa
            # chuka hai, aur yahan maqsad hi GHAIR-JANIBDAR raaye hai.
            if exclude_channel_id and snip.get("channelId") == exclude_channel_id:
                continue
            # Title mein brand ka zikr laazmi (hashtags shumar nahi).
            # Isi ne "GYM CLOTHING TIER LIST" jaisi comedy videos ko rok diya
            # jo sirf #gymshark tag ki wajah se search mein aati thin.
            if FILTER_IRRELEVANT and not title_mentions_brand(
                snip.get("title", ""), tokens
            ):
                skipped_offtopic += 1
                continue
            found[vid] = {
                "video_id": vid,
                "title": snip.get("title", ""),
                "channel_title": snip.get("channelTitle", ""),
                "channel_id": snip.get("channelId", ""),
                "source": "youtube_review_video",
                "platform": "youtube_reviews",
            }

    if skipped_offtopic:
        logger.info(
            "Skipped %d search results whose title never mentions %r "
            "(hashtag-only matches)", skipped_offtopic, brand_name,
        )
    if not found:
        logger.info("No third-party review videos found for %r", brand_name)
        return []

    # 1 unit — statistics batati hain kis par comments hain aur kaunsi video
    # sab se zyada dekhi gayi (yani sab se ba-asar raaye).
    ids = list(found)[:50]
    stats_data = _api_get(
        "videos", {"part": "statistics", "id": ",".join(ids)}, key, quota
    )
    for v in (stats_data or {}).get("items") or []:
        st = v.get("statistics", {})
        if v["id"] in found:
            found[v["id"]]["views"] = int(st.get("viewCount", 0) or 0)
            found[v["id"]]["comments"] = int(st.get("commentCount", 0) or 0)

    ranked = sorted(
        (v for v in found.values() if v.get("comments", 0) > 0),
        key=lambda e: e.get("views", 0),
        reverse=True,
    )[:REVIEW_VIDEOS_TO_READ]

    logger.info(
        "Third-party review videos: %d found, %d with comments, reading top %d by views",
        len(found),
        sum(1 for v in found.values() if v.get("comments", 0) > 0),
        len(ranked),
    )
    return ranked


def fetch_review_video_comments(
    brand_name: str, own_channel_url: str = None
) -> List[Dict]:
    """
    Third-party review videos ki comments — public entry point.

    fetch_youtube_comments() ki tarah ye bhi KABHI raise nahi karta. Quota
    khatam, koi video na mile, comments band hon — jo mila wo return hota hai.
    """
    if not REVIEW_SEARCH_ENABLED:
        logger.info("YouTube review-video search disabled by env — skipping.")
        return []

    key = get_api_key()
    if not key:
        return []

    quota = QuotaTracker()
    collected: List[Dict] = []

    try:
        own_channel_id = None
        if own_channel_url:
            resolved = resolve_channel(own_channel_url, key, quota)
            if resolved:
                own_channel_id = resolved[0]

        videos = search_review_videos(brand_name, key, quota, own_channel_id)
        if not videos:
            logger.info("No third-party review videos. Quota used: %s", quota)
            return []

        seen_text = set()
        duplicates = 0
        tokens = brand_tokens(brand_name)
        for video in videos:
            fetched = fetch_video_comments(
                video, key, quota,
                relevance_tokens=tokens if FILTER_IRRELEVANT else None,
            )
            for comment in fetched:
                fingerprint = comment["content"].strip().lower()
                if fingerprint in seen_text:
                    duplicates += 1
                    continue
                seen_text.add(fingerprint)
                collected.append(comment)

        if duplicates:
            logger.info("Dropped %d duplicate review-video comments", duplicates)

        logger.info(
            "YouTube review videos done: %d videos, %d comments. Quota used: %s",
            len(videos), len(collected), quota,
        )

    except _QuotaExceeded:
        logger.error(
            "Quota exhausted mid-run — returning %d review comments. Quota used: %s",
            len(collected), quota,
        )
    except Exception as e:
        logger.error(
            "Unexpected error in review-video source (%s) — returning %d comments",
            e, len(collected), exc_info=True,
        )

    return collected


# ── public entry point ────────────────────────────────────────────────────────

def fetch_youtube_comments(channel_url: Optional[str]) -> List[Dict]:
    """
    Brand ke YouTube channel se comments lao.

    KABHI raise nahi karta. Koi bhi masla ho — khali list milti hai aur
    Trustpilot ka analysis normally chalta rehta hai.
    """
    if not channel_url:
        logger.info("No YouTube URL for this brand — skipping YouTube source.")
        return []

    key = get_api_key()
    if not key:
        return []

    quota = QuotaTracker()
    collected: List[Dict] = []

    try:
        resolved = resolve_channel(channel_url, key, quota)
        if not resolved:
            logger.info("YouTube skipped — channel not resolved. Quota used: %s", quota)
            return []

        channel_id, uploads = resolved

        videos = select_videos(uploads, key, quota)
        if not videos:
            logger.info("YouTube skipped — no videos. Quota used: %s", quota)
            return []

        # Duplicate comment text hata do. Channel owner aksar wahi promo comment
        # ("Get Bruvi on bruvi.com") har video par pin karta hai — bina dedup ke
        # wo sentiment counts aur Groq ke insights dono ko skew karta hai.
        # (Trustpilot scraper bhi isi tarah dedupe karta hai.)
        seen_text = set()
        duplicates = 0
        for video in videos:
            for comment in fetch_video_comments(video, key, quota):
                fingerprint = comment["content"].strip().lower()
                if fingerprint in seen_text:
                    duplicates += 1
                    continue
                seen_text.add(fingerprint)
                collected.append(comment)

        if duplicates:
            logger.info("Dropped %d duplicate YouTube comments", duplicates)

        with_comments = sum(1 for v in videos if v.get("comments", 0) > 0)
        logger.info(
            "YouTube done: channel=%s, %d videos selected (%d had comments), "
            "%d comments collected. Quota used: %s",
            channel_id,
            len(videos),
            with_comments,
            len(collected),
            quota,
        )

    except _QuotaExceeded:
        logger.error(
            "YouTube quota exhausted mid-run — returning %d comments collected "
            "so far. Quota used: %s",
            len(collected),
            quota,
        )
    except Exception as e:
        # Aakhri safety net — YouTube kabhi bhi poori analysis na girae.
        logger.error(
            "Unexpected YouTube error (%s) — returning %d comments collected so far",
            e,
            len(collected),
            exc_info=True,
        )

    return collected


if __name__ == "__main__":
    # Smoke test:
    #   python -m modules.sentiment.services.youtube_service
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    from dotenv import load_dotenv

    load_dotenv()

    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/@asimjofa"
    comments = fetch_youtube_comments(url)
    print(f"\n{len(comments)} comments from {url}\n")
    for c in comments[:10]:
        print(f"  [{c['author'][:18]:18}] {c['content'][:70]}")
