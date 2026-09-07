import requests
import time
from bs4 import BeautifulSoup
from colorthief import ColorThief
from PIL import Image
from io import BytesIO
import re
import json
from urllib.parse import urlparse, urljoin, unquote

from modules.store_locale import format_price


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def make_absolute_url(url: str, base_url: str) -> str:
    """Relative URL ko absolute banao — all edge cases handle"""
    if not url:
        return None
    url = url.strip()
    if url.startswith("data:"):          # base64 inline — skip
        return None
    if url.startswith("blob:"):          # blob URL — skip
        return None
    if url.startswith("http"):
        return url
    if url.startswith("//"):
        return "https:" + url
    try:
        return urljoin(base_url, url)
    except Exception:
        return None


def clean_image_url(url: str, base_url: str) -> str:
    """
    Next.js /_next/image?url=... encoded URLs decode karo.
    Shopify CDN size suffix hata do (e.g. _200x200.jpg → .jpg).
    """
    if not url:
        return None

    # Next.js image proxy decode
    if "/_next/image" in url and "url=" in url:
        match = re.search(r'url=([^&]+)', url)
        if match:
            decoded = unquote(match.group(1))
            return make_absolute_url(decoded, base_url)

    # Shopify CDN — size variants hata do, original lo
    # e.g. //cdn.shopify.com/…/product_200x200.jpg → …/product.jpg
    shopify_size = re.sub(r'_\d+x\d*(\.[a-z]{3,4})', r'\1', url)
    url = shopify_size

    return make_absolute_url(url, base_url)


def best_image_from_tag(img_tag, base_url: str) -> str:
    """
    <img> tag se best quality image URL nikalo.
    Priority: srcset (largest) → data-* lazy attrs → src
    """
    if not img_tag:
        return None

    # 1. srcset — sabse badi image lo
    srcset = img_tag.get("srcset") or img_tag.get("data-srcset") or ""
    if srcset:
        best = _parse_srcset_best(srcset)
        if best:
            return clean_image_url(best, base_url)

    # 2. Lazy load data attributes (common patterns)
    for attr in ["data-src", "data-lazy-src", "data-original",
                 "data-lazy", "data-img-src", "data-echo",
                 "data-lazyload", "data-url"]:
        val = img_tag.get(attr)
        if val and not val.endswith(".svg"):
            cleaned = clean_image_url(val, base_url)
            if cleaned:
                return cleaned

    # 3. Regular src
    src = img_tag.get("src")
    if src and not src.endswith(".svg"):
        return clean_image_url(src, base_url)

    return None


def _parse_srcset_best(srcset: str) -> str:
    """srcset string se highest resolution URL nikalo"""
    candidates = []
    for part in srcset.split(","):
        part = part.strip()
        if not part:
            continue
        pieces = part.split()
        if len(pieces) >= 2:
            url = pieces[0]
            descriptor = pieces[1]
            # Width descriptor (e.g. 800w) ya density (e.g. 2x)
            if descriptor.endswith("w"):
                try:
                    candidates.append((int(descriptor[:-1]), url))
                except ValueError:
                    pass
            elif descriptor.endswith("x"):
                try:
                    candidates.append((int(float(descriptor[:-1]) * 1000), url))
                except ValueError:
                    pass
        elif len(pieces) == 1:
            candidates.append((0, pieces[0]))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None


def is_product_image(url: str) -> bool:
    """Skip karo icons, placeholders, SVGs"""
    if not url:
        return False
    lower = url.lower()
    skip_patterns = [
        ".svg", "placeholder", "no-image", "noimage",
        "blank", "loading", "spinner", "pixel.gif",
        "1x1", "spacer", "logo", "icon", "favicon"
    ]
    return not any(p in lower for p in skip_patterns)


# ─────────────────────────────────────────────
#  BASIC INFO
# ─────────────────────────────────────────────

def extract_basic_info(soup: BeautifulSoup, url: str) -> dict:
    business_name = ""
    if soup.title:
        business_name = soup.title.string or ""
        for sep in ["|", "-", "–", "—", "•"]:
            if sep in business_name:
                business_name = business_name.split(sep)[0].strip()
                break

    description = ""
    for attr_name, attr_val in [("name", "description"), ("property", "og:description")]:
        tag = soup.find("meta", attrs={attr_name: attr_val})
        if tag:
            description = tag.get("content", "")
            break

    if not description:
        first_p = soup.find("p")
        if first_p:
            description = first_p.get_text(strip=True)[:300]

    if not business_name:
        og_name = soup.find("meta", property="og:site_name")
        if og_name:
            business_name = og_name.get("content", "")

    if not business_name:
        domain = urlparse(url).netloc
        business_name = domain.replace("www.", "").split(".")[0].title()

    return {
        "business_name": business_name.strip(),
        "description": description.strip()
    }


# ─────────────────────────────────────────────
#  SOCIAL LINKS
# ─────────────────────────────────────────────

SOCIAL_DOMAINS = {
    "facebook": ["facebook.com", "fb.com"],
    "instagram": ["instagram.com"],
    "twitter": ["twitter.com", "x.com"],
    "whatsapp": ["wa.me", "whatsapp.com"],
    "youtube": ["youtube.com", "youtu.be"],
    "tiktok": ["tiktok.com"],
    "linkedin": ["linkedin.com"],
    "pinterest": ["pinterest.com"],
}

# "Is page ko share karo" wale links — brand ke apne account NAHI.
#
# YE IS FUNCTION KI SAB SE AHEM CHEEZ HAI. Pehle yahan sirf "pehla match rakh
# lo" tha, aur share widgets page mein FOOTER SE PEHLE aate hain. Natija
# (Gymshark par asal mein hua):
#
#   twitter   -> twitter.com/home?status=http://live.storystream.it/...
#   facebook  -> facebook.com/sharer/sharer.php?u=...
#   linkedin  -> linkedin.com/shareArticle?mini=true&url=...
#   pinterest -> pinterest.com/pin/create/button/?url=...
#
# Chaaron bekaar, aur Instagram BILKUL gayab — kyunki `platform not in result`
# ne footer wale asal link ko baad mein aane par rok diya.
_SHARE_MARKERS = (
    "/sharer", "sharer.php", "/share?", "/share/", "share.php",
    "/intent/", "intent/tweet", "sharearticle", "/pin/create/",
    "?status=", "&status=", "/dialog/", "/submit?", "shareopenlink",
    "/offsite/", "share_url", "sharetosocial",
)


def _platform_for(href: str) -> str | None:
    for platform, domains in SOCIAL_DOMAINS.items():
        if any(d in href for d in domains):
            return platform
    return None


def _is_share_link(href: str, platform: str) -> bool:
    """Share/intent widget hai ya brand ka apna profile?"""
    if any(marker in href for marker in _SHARE_MARKERS):
        return True
    # Share links doosre page ka URL apne andar le kar chalte hain.
    if "url=" in href or "u=http" in href or "text=" in href:
        # wa.me/<number>?text=... jaiz hai (pre-filled message), lekin
        # wa.me/?text=... sirf share button hota hai — us mein number hi nahi.
        if platform == "whatsapp" and re.search(r"wa\.me/\+?\d{6,}", href):
            return False
        return True
    return False


def _in_footer(tag, max_depth: int = 15) -> bool:
    """
    Link footer (ya kisi social block) ke andar hai?

    Brand ke asal social icons taqreeban hamesha footer mein hote hain, jabke
    share widgets product/video blocks mein. Parents ki tarteeb mehdood hai —
    827 anchors par poora tree chalna bewajah susti hai.
    """
    depth = 0
    for parent in tag.parents:
        if depth >= max_depth:
            break
        depth += 1
        if getattr(parent, "name", "") == "footer":
            return True
        if not hasattr(parent, "get"):
            continue
        marker = " ".join(parent.get("class") or []) + " " + (parent.get("id") or "")
        if "footer" in marker.lower():
            return True
    return False


def _score_link(tag, href: str) -> int:
    """
    Kaunsa candidate behtar hai. Bara score = behtar.

    Sirf pehla match rakh lena hi asal bug tha, is liye ab HAR candidate jama
    hota hai aur behtareen chuna jata hai.
    """
    score = 0
    if _in_footer(tag):
        score += 50

    attrs = " ".join(
        (tag.get("class") or []) + [tag.get("rel") and " ".join(tag.get("rel")) or "",
                                    tag.get("aria-label") or "", tag.get("title") or ""]
    ).lower()
    if any(w in attrs for w in ("social", "follow", "instagram", "facebook")):
        score += 20
    if "share" in attrs:
        score -= 40

    # Profile URL chhota hota hai (facebook.com/brand), tracking/deep links
    # lambe. Query string bhi profile par kam hi hoti hai.
    path = href.split("?", 1)[0].rstrip("/")
    score -= path.count("/") * 3
    if "?" in href:
        score -= 10
    return score


def extract_social_links(soup: BeautifulSoup) -> dict:
    """
    Brand ke apne social profiles — share buttons NAHI.

    Har platform ke SAARE candidates jama kar ke behtareen chuna jata hai
    (dekho _score_link). Pehle sirf pehla match rakha jata tha, jo aksar
    "share this page" nikalta.
    """
    best: dict[str, tuple[int, str]] = {}

    for link in soup.find_all("a", href=True):
        href = (link["href"] or "").strip()
        low = href.lower()
        if not low or low.startswith(("javascript:", "mailto:", "#")):
            continue

        platform = _platform_for(low)
        if not platform or _is_share_link(low, platform):
            continue

        score = _score_link(link, low)
        if platform not in best or score > best[platform][0]:
            best[platform] = (score, href)

    return {platform: href for platform, (_, href) in best.items()}


# ─────────────────────────────────────────────
#  CONTACT PAGE
# ─────────────────────────────────────────────
#
# Bohat se stores footer mein social icons rakhte hi nahi — wahan sirf
# "Contact Us" ka link hota hai, aur asal icons us page par hote hain. Home
# page se hi haar maan lene ka matlab hai un sab brands ke links kabhi na
# milna.
#
# Ye SIRF ek extra page hai, poora crawl nahi: ek hi request, aur wo bhi tab
# jab home page se kuch mila hi na ho (dekho scraper.py).

_CONTACT_HINTS = (
    "contact", "contact-us", "contactus", "get-in-touch", "getintouch",
    "reach-us", "customer-service", "customer-care", "support", "help-centre",
    "help-center", "about-us", "aboutus",
)

# Ye lafz URL mein hon to wo contact page nahi — "contact" un mein ittefaqan
# aa jata hai (misal: /pages/contact-lens, /blogs/news/contacting-suppliers).
_CONTACT_SKIP = ("lens", "blog", "article", "product", "collection", "cart")


def find_contact_page(soup: BeautifulSoup, base_url: str) -> str | None:
    """
    Footer/nav mein "Contact Us" ka link — usi domain par.

    Sab se chhota, sab se saaf candidate chuna jata hai: "/pages/contact"
    "/pages/contact-us-form-2" se behtar hai.
    """
    host = urlparse(base_url).netloc.lower().replace("www.", "")
    best: tuple[int, str] | None = None

    for link in soup.find_all("a", href=True):
        href = (link["href"] or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue

        absolute = make_absolute_url(href, base_url)
        parsed = urlparse(absolute)
        if parsed.netloc and parsed.netloc.lower().replace("www.", "") != host:
            continue                       # doosri site — chhoro

        path = (parsed.path or "").lower()
        text = link.get_text(" ", strip=True).lower()[:60]
        haystack = f"{path} {text}"
        if not any(h in haystack for h in _CONTACT_HINTS):
            continue
        if any(s in path for s in _CONTACT_SKIP):
            continue

        # Chhota path behtar; "contact" wala "about" se behtar.
        score = -len(path)
        if "contact" in haystack:
            score += 50
        if best is None or score > best[0]:
            best = (score, absolute)

    return best[1] if best else None


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Woh emails jo store ke apne nahi hote — theme/app vendors ke hote hain.
_EMAIL_SKIP = ("example.com", "sentry.io", "shopify.com", "@2x", "godaddy",
               "wixpress", "yourstore", "domain.com")


def extract_contacts(soup: BeautifulSoup) -> dict:
    """
    Store ka email aur phone.

    mailto:/tel: links par bharosa PEHLE — wo saaf hote hain. Un ke baghair
    page ke text se email dhoondte hain (phone ke liye text par bharosa nahi
    kiya: har page par order numbers, sizes aur prices hote hain jo phone jaise
    lagte hain aur ghalat data DB mein chala jata).
    """
    email = ""
    phone = ""

    for link in soup.find_all("a", href=True):
        href = (link["href"] or "").strip()
        low = href.lower()
        if not email and low.startswith("mailto:"):
            candidate = unquote(href[7:].split("?")[0]).strip()
            if _EMAIL_RE.fullmatch(candidate) and not any(s in candidate.lower() for s in _EMAIL_SKIP):
                email = candidate
        elif not phone and low.startswith("tel:"):
            candidate = unquote(href[4:]).strip()
            digits = re.sub(r"[^\d]", "", candidate)
            if 7 <= len(digits) <= 15:
                phone = candidate

    if not email:
        for match in _EMAIL_RE.findall(soup.get_text(" ", strip=True)[:20000]):
            if not any(s in match.lower() for s in _EMAIL_SKIP):
                email = match
                break

    return {"contact_email": email, "contact_phone": phone}


MAX_SOCIAL_URL = 500


def clean_social_links(raw: dict) -> dict:
    """
    User ke haath se bhare hue social links ko parkho.

    Scraping har site par kaam nahi karti, is liye user profile page se khud
    links bhar sakta hai — magar us ka matlab ye nahi ke koi bhi text DB mein
    chala jaye. Ye links aage chatbot aur ad copy ke prompts mein jate hain.

    Qawaid:
      * sirf woh platforms jo SOCIAL_DOMAINS mein hain
      * khali value = us platform ko HATA do (yehi delete ka tareeqa hai)
      * scheme na ho to https:// laga do (log "instagram.com/x" hi likhte hain)
      * URL usi platform ke domain par hona chahiye — instagram ke khane mein
        facebook ka link daalna ghalti hai, chup-chaap qubool nahi hoga
      * share/intent links yahan bhi mana hain, wahi wajah jo scraping mein hai

    Raises ValueError — route ise 400 banata hai.
    """
    if not isinstance(raw, dict):
        raise ValueError("Social links must be an object of platform -> URL.")

    cleaned: dict[str, str] = {}
    for platform, value in raw.items():
        key = str(platform).strip().lower()
        if key not in SOCIAL_DOMAINS:
            raise ValueError(
                f"Unknown platform '{platform}'. Choose one of: "
                f"{', '.join(sorted(SOCIAL_DOMAINS))}."
            )

        url = (value or "").strip()
        if not url:
            continue                      # khali = hata do

        if len(url) > MAX_SOCIAL_URL:
            raise ValueError(f"The {key} link is too long (max {MAX_SOCIAL_URL} characters).")

        if not re.match(r"^https?://", url, re.IGNORECASE):
            url = "https://" + url.lstrip("/")

        low = url.lower()
        if not any(d in low for d in SOCIAL_DOMAINS[key]):
            raise ValueError(
                f"That does not look like a {key} link. "
                f"It should point to {SOCIAL_DOMAINS[key][0]}."
            )
        if _is_share_link(low, key):
            raise ValueError(
                f"That {key} link is a 'share this page' link, not a profile. "
                f"Please paste the address of your own {key} page."
            )

        cleaned[key] = url

    return cleaned


# ─────────────────────────────────────────────
#  LOGO
# ─────────────────────────────────────────────

def extract_logo(soup: BeautifulSoup, base_url: str) -> str:
    # 1. og:image
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        return og_image.get("content")

    # 2. alt="logo" image
    logo = soup.find("img", alt=lambda x: x and "logo" in x.lower())
    if logo:
        url = best_image_from_tag(logo, base_url)
        if url:
            return url

    # 3. class mein "logo"
    logo = soup.find("img", class_=lambda x: x and "logo" in " ".join(x).lower())
    if logo:
        url = best_image_from_tag(logo, base_url)
        if url:
            return url

    # 4. header → first img
    header = soup.find("header")
    if header:
        img = header.find("img")
        if img:
            url = best_image_from_tag(img, base_url)
            if url:
                return url

    # 5. nav → first img
    nav = soup.find("nav")
    if nav:
        img = nav.find("img")
        if img:
            url = best_image_from_tag(img, base_url)
            if url:
                return url

    # 6. link rel=icon
    icon_link = soup.find("link", rel=lambda x: x and "icon" in " ".join(x).lower())
    if icon_link and icon_link.get("href"):
        return make_absolute_url(icon_link["href"], base_url)

    return None


# ─────────────────────────────────────────────
#  BRAND COLORS
# ─────────────────────────────────────────────

def extract_brand_colors(logo_url: str) -> list:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(logo_url, headers=headers, timeout=10)
        img = Image.open(BytesIO(response.content)).convert("RGB")
        temp = BytesIO()
        img.save(temp, format="PNG")
        temp.seek(0)
        ct = ColorThief(temp)
        palette = ct.get_palette(color_count=3, quality=1)
        return [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in palette]
    except Exception as e:
        print(f"Color extraction error: {e}")
        return []


# ─────────────────────────────────────────────
#  PRODUCT PAGE LINKS
# ─────────────────────────────────────────────

def extract_product_links(soup: BeautifulSoup, base_url: str) -> list:
    product_keywords = [
        "product", "shop", "store", "item", "catalogue",
        "collection", "category", "buy", "order", "menu",
        "products", "catalog", "accessories", "fragrances","western wear", "collections"
    ]

    product_links = set()
    for link in soup.find_all("a", href=True):
        href = link["href"].lower()
        if any(kw in href for kw in product_keywords):
            absolute = make_absolute_url(link["href"], base_url)
            if absolute and urlparse(base_url).netloc in absolute:
                product_links.add(absolute)

    return list(product_links)[:16]


# ─────────────────────────────────────────────
#  PLATFORM DETECTION
# ─────────────────────────────────────────────

def detect_platform(html: str, soup: BeautifulSoup, base_url: str) -> str:
    """
    Website ka platform detect karo.
    Returns: 'shopify' | 'woocommerce' | 'nextjs' | 'react' | 'vue' | 'html'
    """
    # Shopify
    if (
        "Shopify.shop" in html or
        "cdn.shopify.com" in html or
        "/products.json" in html or
        soup.find("meta", attrs={"name": "shopify-checkout-api-token"})
    ):
        return "shopify"

    # WooCommerce / WordPress
    if (
        "woocommerce" in html.lower() or
        "/wp-content/" in html or
        "/wp-json/" in html
    ):
        return "woocommerce"

    # Next.js
    if "__NEXT_DATA__" in html or "/_next/static" in html:
        return "nextjs"

    # React (CRA / Vite)
    if (
        'id="root"' in html or
        "data-reactroot" in html or
        "react" in html.lower() and 'id="app"' in html
    ):
        return "react"

    # Vue / Nuxt
    if "__nuxt" in html or "data-v-app" in html or "id=\"__nuxt\"" in html:
        return "vue"

    return "html"


# ─────────────────────────────────────────────
#  SHOPIFY EXTRACTOR
# ─────────────────────────────────────────────

# Shopify /products.json 250 rows per page se zyada nahi deta. Pehle yahan
# hardcoded 4-page cap tha (=1000 products) jo bare catalogs truncate kar deta
# tha. Ab empty page tak paginate karte hain; ye cap sirf misbehaving endpoint
# par infinite loop rokne ke liye hai, functional limit nahi.
SHOPIFY_MAX_PAGES = 200          # 200 × 250 = 50,000 products
SHOPIFY_PAGE_SIZE = 250
SHOPIFY_PAGE_DELAY = 0.3         # rate limiting se bachne ke liye
SHOPIFY_MAX_COLLECTION_PAGES = 20   # 20 × 250 = 5,000 collections
# Bare catalogs 30-40 pages lete hain; beech mein ek rate-limit (429) bina
# retry ke poora scrape adhoora kar deta hai.
SHOPIFY_MAX_RETRIES = 4             # 1 initial + 3 retries
SHOPIFY_RETRY_BASE_DELAY = 2.0      # 2s, 4s, 8s exponential backoff


def _parse_shopify_product(p: dict, store_base: str, currency: str = None) -> dict:
    """
    Ek raw Shopify product JSON ko BrandWave ke product dict mein badalta hai.

    currency store ki apni currency hai (store_locale se detect hui). None ho
    to price bina symbol ke jata hai.
    """
    images = p.get("images", []) or []

    image_url = None
    image_alt = ""
    if images:
        # Biggest src lo — Shopify CDN par size suffix remove karo
        image_url = clean_image_url(images[0].get("src", ""), store_base)
        image_alt = images[0].get("alt") or ""

    # NOTE: pehle yahan `all_images` (har product ki poori image list) bhi store
    # hoti thi. Wo poore payload ka ~41% thi (7,157 products par 3.78 MB of
    # 9.12 MB) aur use koi module, route ya component padhta hi nahi tha —
    # frontend ka Product interface use declare tak nahi karta. Isliye ab store
    # nahi hoti. Agar kabhi gallery/carousel banani ho to `image_url` ke saath
    # yahin se dobara nikaal lena.

    # Price from first variant
    # Price from first variant — store ki apni currency ke saath.
    # Pehle yahan ek currency symbol HARDCODED tha, to har store ke products
    # usi symbol ke saath DB mein jate the (US store ke $ wale products bhi),
    # aur wahi ghalat price ad copy aur blog prompts mein feed hota tha.
    variants = p.get("variants", []) or []
    price = None
    if variants:
        price = format_price(variants[0].get("price"), currency)

    # Description — HTML se plain text
    desc_html = p.get("body_html", "") or ""
    clean_desc = BeautifulSoup(desc_html, "html.parser").get_text(strip=True)[:300]

    # Tags — list of strings
    tags = p.get("tags", []) or []
    if isinstance(tags, str):
        # Sometimes Shopify returns comma-separated string
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    return {
        # id merge/dedup ke liye chahiye — collections aur /products.json ke
        # beech same product do baar aa sakta hai.
        "id": p.get("id"),
        "handle": p.get("handle"),
        "name": p.get("title"),
        "price": price,
        "description": clean_desc or None,
        "image_url": image_url,
        "image_alt": image_alt,
        "category": p.get("product_type") or "",
        # Raw Shopify product_type ALAG se mehfooz. `category` ko aage
        # scraper.py detect_product_category() ke natije se OVERWRITE kar
        # deta hai — pehle is se asli product_type hamesha ke liye zaya ho
        # jata tha, aur category dobara nikalne ke liye poora store
        # dobara scrape karna parta tha.
        "product_type": p.get("product_type") or "",
        "tags": tags,
        "vendor": p.get("vendor") or "",
        "source": "shopify_api",
    }


def _fetch_shopify_pages(store_base: str, path: str, headers: dict, label: str) -> list:
    """
    Kisi bhi Shopify products endpoint ko empty page tak paginate karta hai.
    Empty products array = catalog ka natural end.
    """
    collected = []
    page = 1

    while page <= SHOPIFY_MAX_PAGES:
        url = f"{store_base}{path}?limit={SHOPIFY_PAGE_SIZE}&page={page}"
        batch, error = _get_products_page(url, headers, label, page)

        if error:
            # Retries ke baad bhi fail — partial data return hoga, isliye ise
            # LOUDLY report karo. Warna scrape chup-chaap adhoora catalog de dega.
            print(
                f"[shopify] {label}: GIVING UP on page {page} after "
                f"{SHOPIFY_MAX_RETRIES} attempts ({error}). "
                f"RESULT IS PARTIAL - {len(collected)} product(s) fetched so far."
            )
            break

        if not batch:
            break

        collected.extend(batch)
        print(f"[shopify] {label} page {page}: +{len(batch)} (total {len(collected)})")

        page += 1
        time.sleep(SHOPIFY_PAGE_DELAY)

    if page > SHOPIFY_MAX_PAGES:
        print(f"[shopify] {label}: hit {SHOPIFY_MAX_PAGES}-page safety cap - catalog may be larger")

    return collected


def _get_products_page(url: str, headers: dict, label: str, page: int):
    """
    Ek page fetch karta hai, transient failures par exponential backoff ke saath
    retry karke.

    Ye zaroori hai: bare catalogs 30-40 pages lete hain, aur beech mein ek 429
    (rate limit) aa jaye to bina retry ke scrape chup-chaap adhoora reh jata
    hai — asimjofa par exactly yehi hua tha (page 18 par 429 => 7,157 ki jagah
    sirf 4,250 products).

    Return: (batch, error). error None ho to batch valid hai (khali bhi ho
    sakta hai = catalog ka end).
    """
    delay = SHOPIFY_RETRY_BASE_DELAY
    last_error = None

    for attempt in range(1, SHOPIFY_MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=headers, timeout=20)

            if response.status_code == 200:
                return response.json().get("products", []), None

            # 429 / 5xx transient hote hain — inhe retry karna banta hai.
            # 404 waghera permanent hain, foran haar maan lo.
            if response.status_code != 429 and response.status_code < 500:
                return None, f"HTTP {response.status_code}"

            last_error = f"HTTP {response.status_code}"

        except Exception as e:
            last_error = str(e)

        if attempt < SHOPIFY_MAX_RETRIES:
            print(
                f"[shopify] {label}: {last_error} on page {page} - "
                f"retry {attempt}/{SHOPIFY_MAX_RETRIES - 1} in {delay:.1f}s"
            )
            time.sleep(delay)
            delay *= 2

    return None, last_error


def _fetch_shopify_collection_handles(store_base: str, headers: dict) -> list:
    """/collections.json se saare collection handles nikalta hai."""
    handles = []
    page = 1

    while page <= SHOPIFY_MAX_COLLECTION_PAGES:
        url = f"{store_base}/collections.json?limit={SHOPIFY_PAGE_SIZE}&page={page}"
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                break

            batch = response.json().get("collections", [])
            if not batch:
                break

            handles.extend(c.get("handle") for c in batch if c.get("handle"))
            page += 1
            time.sleep(SHOPIFY_PAGE_DELAY)

        except Exception as e:
            print(f"[shopify] collections.json error on page {page}: {e}")
            break

    return handles


def extract_shopify_products(
    base_url: str, include_collections: bool = False, currency: str = None
) -> list:
    """
    Shopify JSON API se saare products fetch karo.

    currency = store ki detect ki hui currency (modules/store_locale.py se);
    product prices isi symbol ke saath format hote hain.

    /products.json ko empty page tak paginate karta hai — yahi default source hai.

    include_collections=True karne par /collections.json enumerate karke har
    collection ke products bhi fetch hote hain aur product id par merge +
    dedupe hota hai.

    ── Default OFF kyun hai ──────────────────────────────────────────────
    /products.json akela hi poora catalog de deta hai (asimjofa 7,157 |
    gulahmedshop 6,821 | bonanzasatrangi 9,640 products), jo SEO audit, ad
    generation aur chatbot modules ke liye kaafi se zyada hai.

    Collections sweep bohat mehenga hai: asimjofa par 788 collections hain,
    yani ~1,600 extra requests aur har scrape mein 15+ minutes ka izafa —
    is fayde ke liye jo (neeche dekho) na ke barabar hai.

    Flag future ke liye rakha gaya hai; ise on karne se pehle scrape time
    budget zaroor dekh lena.
    """
    parsed = urlparse(base_url)
    store_base = f"{parsed.scheme}://{parsed.netloc}"
    headers = {"User-Agent": "Mozilla/5.0"}

    raw = _fetch_shopify_pages(store_base, "/products.json", headers, "products.json")
    print(f"[shopify] /products.json total rows: {len(raw)}")

    # id par dedupe — id na ho to handle/title fallback
    by_key = {}
    for p in raw:
        key = p.get("id") or p.get("handle") or p.get("title")
        if key is not None and key not in by_key:
            by_key[key] = p

    base_count = len(by_key)

    # ── INVESTIGATED 2026-08-21 — collections add NOTHING ────────────────
    # Sawal ye tha: kya /products.json sirf default scope deta hai aur kuch
    # products sirf collections mein hote hain? Jawab: NAHI.
    #
    # asimjofa.com par test kiya — 7,157 products ka poora baseline banaya
    # (empty page tak walk, koi truncation nahi), phir sabse bare collections
    # check kiye:
    #
    #   designer-picks              196 products  ->  0 not in /products.json
    #   designers-limited-edition   188 products  ->  0
    #   ai-shoot                    506 products  ->  0
    #   festive-edit                622 products  ->  0
    #   basics                      162 products  ->  0
    #   bangles                     143 products  ->  0
    #   daily-pret / chamkeeli       88 products  ->  0
    #
    # Har collection ka har product /products.json mein pehle se mojood tha.
    #
    # ⚠️ TRAP — agar dobara test karo to delay 0.3s se kam mat karna. 0.15s par
    # store rate-limit karta hai aur pagination CHUP-CHAAP jaldi ruk jati hai
    # (7,157 ki jagah 6,500 products, 788 ki jagah 250 collections). Aisa
    # adhoora baseline jhooti "125 new products" wali reading deta hai —
    # wo products asal mein un pages par the jo fetch hi nahi hue the.
    #
    # Yani: is code path ko on karne se sirf waqt lagega, products nahi milenge.
    # ─────────────────────────────────────────────────────────────────────
    if include_collections:
        handles = _fetch_shopify_collection_handles(store_base, headers)
        print(f"[shopify] collections found: {len(handles)}")

        for handle in handles:
            batch = _fetch_shopify_pages(
                store_base, f"/collections/{handle}/products.json", headers, f"col:{handle}"
            )
            for p in batch:
                key = p.get("id") or p.get("handle") or p.get("title")
                if key is not None and key not in by_key:
                    by_key[key] = p

        added = len(by_key) - base_count
        print(f"[shopify] collections added {added} product(s) not in /products.json")

    products = [_parse_shopify_product(p, store_base, currency) for p in by_key.values()]
    print(f"[shopify] total unique products: {len(products)}")
    return products


# ─────────────────────────────────────────────
#  WOOCOMMERCE EXTRACTOR
# ─────────────────────────────────────────────

def extract_woocommerce_products(base_url: str, soup: BeautifulSoup, currency: str = None) -> list:
    """
    WooCommerce ke liye 2 methods:
    1. REST API (/wp-json/wc/v3/products) — agar public ho
    2. HTML scraping with WooCommerce-specific selectors
    """
    parsed = urlparse(base_url)
    store_base = f"{parsed.scheme}://{parsed.netloc}"
    headers = {"User-Agent": "Mozilla/5.0"}
    products = []

    # Method 1: WooCommerce REST API (public products — no auth needed for public)
    try:
        api_url = f"{store_base}/wp-json/wc/v3/products?per_page=20&status=publish"
        response = requests.get(api_url, headers=headers, timeout=10)
        if response.status_code == 200:
            woo_products = response.json()
            if isinstance(woo_products, list) and woo_products:
                for p in woo_products:
                    images = p.get("images", [])
                    image_url = images[0].get("src") if images else None
                    all_images = [img.get("src") for img in images if img.get("src")]

                    desc_html = p.get("short_description") or p.get("description") or ""
                    desc_soup = BeautifulSoup(desc_html, "html.parser")
                    clean_desc = desc_soup.get_text(strip=True)[:300]

                    # Yahan bhi pehle ek symbol hardcoded tha — ab currency
                    # maloom na ho to sirf raw amount jata hai.
                    price = format_price(p.get("price"), currency)

                    products.append({
                        "name": p.get("name"),
                        "price": price,
                        "description": clean_desc or None,
                        "image_url": image_url,
                        "all_images": all_images,
                        "category": p.get("categories", [{}])[0].get("name") if p.get("categories") else None,
                        "source": "woocommerce_api"
                    })

                print(f"✅ WooCommerce API: {len(products)} products")
                return products
    except Exception as e:
        print(f"WooCommerce API failed: {e}")

    # Method 2: HTML scraping with WooCommerce CSS selectors
    products = _scrape_woo_html(soup, store_base)
    return products


def _scrape_woo_html(soup: BeautifulSoup, base_url: str) -> list:
    """WooCommerce HTML structure scrape karo"""
    products = []

    # WooCommerce standard product grid
    containers = soup.find_all("li", class_=lambda x: x and "product" in " ".join(x).lower())

    if not containers:
        containers = soup.find_all(
            ["div", "article"],
            class_=lambda x: x and any(
                w in " ".join(x).lower()
                for w in ["product-item", "product-card", "woocommerce-loop-product"]
            )
        )

    for container in containers[:20]:
        product = {}

        # Name — WooCommerce uses .woocommerce-loop-product__title
        name_tag = (
            container.find(class_=lambda x: x and "product__title" in " ".join(x).lower())
            or container.find(class_=lambda x: x and "product-title" in " ".join(x).lower())
            or container.find(["h2", "h3"])
        )
        if name_tag:
            product["name"] = name_tag.get_text(strip=True)

        # Price — .woocommerce-Price-amount
        price_tag = container.find(class_=lambda x: x and "price" in " ".join(x).lower())
        if price_tag:
            product["price"] = price_tag.get_text(strip=True)

        # Image
        img = container.find("img")
        url = best_image_from_tag(img, base_url)
        if url and is_product_image(url):
            product["image_url"] = url

        if product.get("name"):
            product["source"] = "woocommerce_html"
            products.append(product)

    return products


# ─────────────────────────────────────────────
#  NEXT.JS EXTRACTOR
# ─────────────────────────────────────────────

def extract_nextjs_products(html: str, soup: BeautifulSoup, base_url: str) -> list:
    """
    Next.js sites ke liye:
    1. __NEXT_DATA__ JSON se products nikalo
    2. Hydrated HTML se scrape karo
    """
    products = []

    # Method 1: __NEXT_DATA__ embedded JSON
    next_data_tag = soup.find("script", id="__NEXT_DATA__")
    if next_data_tag and next_data_tag.string:
        try:
            next_data = json.loads(next_data_tag.string)
            found = _deep_find_products(next_data)
            if found:
                print(f"✅ Next.js __NEXT_DATA__: {len(found)} products")
                return found
        except Exception as e:
            print(f"__NEXT_DATA__ parse error: {e}")

    # Method 2: Inline JSON scripts mein product data
    for script in soup.find_all("script", type="application/json"):
        if script.string:
            try:
                data = json.loads(script.string)
                found = _deep_find_products(data)
                if found:
                    products.extend(found)
            except Exception:
                continue

    if products:
        return products

    # Method 3: Rendered HTML scrape (Playwright ne already render kar diya)
    return _generic_html_scrape(soup, base_url)


def _deep_find_products(data, depth=0) -> list:
    """
    Nested JSON mein products dhundho recursively.
    Common keys: products, items, nodes, edges, data
    """
    if depth > 6:
        return []

    products = []

    if isinstance(data, dict):
        # Direct product object check
        if _looks_like_product(data):
            p = _normalize_product_from_json(data)
            if p:
                return [p]

        # Recurse into values
        for key in ["products", "items", "nodes", "edges", "data",
                    "pageProps", "initialState", "props", "catalog",
                    "collection", "productList", "results"]:
            if key in data:
                found = _deep_find_products(data[key], depth + 1)
                if found:
                    products.extend(found)

        # Generic recurse
        if not products:
            for val in data.values():
                if isinstance(val, (dict, list)):
                    found = _deep_find_products(val, depth + 1)
                    products.extend(found)

    elif isinstance(data, list):
        for item in data[:50]:  # limit
            found = _deep_find_products(item, depth + 1)
            products.extend(found)

    return products[:20]


def _looks_like_product(obj: dict) -> bool:
    """Dict product hai ya nahi check karo"""
    has_name = any(k in obj for k in ["name", "title", "productName"])
    has_price = any(k in obj for k in ["price", "cost", "amount", "variants"])
    has_image = any(k in obj for k in ["image", "images", "imageUrl", "thumbnail", "media"])
    return has_name and (has_price or has_image)


def _normalize_product_from_json(obj: dict) -> dict:
    """JSON object se product dict banao"""
    name = obj.get("name") or obj.get("title") or obj.get("productName")
    if not name:
        return None

    # Image
    image_url = None
    img_val = obj.get("image") or obj.get("imageUrl") or obj.get("thumbnail")
    if isinstance(img_val, str):
        image_url = img_val
    elif isinstance(img_val, dict):
        image_url = img_val.get("url") or img_val.get("src") or img_val.get("uri")
    elif isinstance(obj.get("images"), list) and obj["images"]:
        first_img = obj["images"][0]
        image_url = first_img if isinstance(first_img, str) else (
            first_img.get("url") or first_img.get("src")
        )

    # Price
    price = None
    price_val = obj.get("price") or obj.get("cost")
    if isinstance(price_val, (int, float)):
        price = str(price_val)
    elif isinstance(price_val, str):
        price = price_val
    elif isinstance(price_val, dict):
        price = str(price_val.get("amount") or price_val.get("value") or "")

    return {
        "name": str(name),
        "price": price,
        "image_url": image_url,
        "description": obj.get("description") or obj.get("shortDescription"),
        "category": obj.get("category") or obj.get("productType") or obj.get("type"),
        "source": "nextjs_json"
    }


# ─────────────────────────────────────────────
#  SCHEMA.ORG EXTRACTOR
# ─────────────────────────────────────────────

def extract_from_schema(soup: BeautifulSoup, base_url: str) -> list:
    """Schema.org JSON-LD se products — @graph bhi handle karo"""
    products = []
    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        if not script.string:
            continue
        try:
            data = json.loads(script.string)

            # Normalize to list
            items = []
            if isinstance(data, dict):
                if data.get("@type") == "ItemList":
                    items = data.get("itemListElement", [])
                elif "@graph" in data:
                    items = data["@graph"]
                else:
                    items = [data]
            elif isinstance(data, list):
                items = data

            for item in items:
                if not isinstance(item, dict):
                    continue

                item_type = item.get("@type", "")
                if isinstance(item_type, list):
                    item_type = " ".join(item_type)

                if "Product" not in item_type:
                    # ListItem mein nested product
                    nested = item.get("item", {})
                    if isinstance(nested, dict) and "Product" in nested.get("@type", ""):
                        item = nested
                    else:
                        continue

                # Image — string ya ImageObject
                image_url = None
                img_data = item.get("image")
                if isinstance(img_data, str):
                    image_url = img_data
                elif isinstance(img_data, list) and img_data:
                    first = img_data[0]
                    image_url = first if isinstance(first, str) else first.get("url")
                elif isinstance(img_data, dict):
                    image_url = img_data.get("url") or img_data.get("contentUrl")

                # Price
                offers = item.get("offers", {})
                price = None
                if isinstance(offers, dict):
                    price = str(offers.get("price", "") or "")
                    currency = offers.get("priceCurrency", "")
                    if price and currency:
                        price = f"{currency} {price}"
                elif isinstance(offers, list) and offers:
                    price = str(offers[0].get("price", ""))

                products.append({
                    "name": item.get("name"),
                    "description": item.get("description", "")[:300] if item.get("description") else None,
                    "price": price or None,
                    "image_url": make_absolute_url(image_url, base_url) if image_url else None,
                    "source": "schema_org"
                })

        except Exception:
            continue

    return products


# ─────────────────────────────────────────────
#  GENERIC HTML SCRAPER (fallback)
# ─────────────────────────────────────────────

def _generic_html_scrape(soup: BeautifulSoup, base_url: str) -> list:
    """
    Generic HTML scraper — Playwright-rendered HTML ke liye bhi kaam karta hai.
    Wide net cast karo, cleaner.py baad mein filter karega.
    """
    products = []

    # Product container patterns — ordered by specificity
    container_selectors = [
        # Explicit product classes
        lambda x: x and any(
            w in " ".join(x).lower()
            for w in [
                "product-card", "product-item", "product-tile",
                "product-grid__item", "product-list__item",
                "shop-item", "catalog-item", "item-card",
                "grid-product", "product-block"
            ]
        ),
        # Broader
        lambda x: x and any(
            w in " ".join(x).lower()
            for w in ["product", "prod-", "item", "card"]
        ) and not any(
            skip in " ".join(x).lower()
            for skip in ["header", "footer", "nav", "cart", "checkout", "review", "blog"]
        )
    ]

    containers = []
    for selector in container_selectors:
        containers = soup.find_all(
            ["div", "article", "li", "section"],
            class_=selector
        )
        if len(containers) >= 2:
            break

    if not containers:
        return []

    seen_names = set()

    for container in containers[:25]:
        product = {}

        # Name
        for tag in ["h1", "h2", "h3", "h4", "h5"]:
            h = container.find(tag)
            if h:
                text = h.get_text(strip=True)
                if len(text) > 2 and len(text) < 200:
                    product["name"] = text
                    break

        if not product.get("name"):
            # Try name-classed spans/divs
            name_tag = container.find(
                class_=lambda x: x and any(
                    w in " ".join(x).lower()
                    for w in ["name", "title", "product-name", "item-name"]
                ) if x else False
            )
            if name_tag:
                product["name"] = name_tag.get_text(strip=True)

        if not product.get("name"):
            continue

        # Skip duplicates
        if product["name"] in seen_names:
            continue
        seen_names.add(product["name"])

        # Price
        price_tag = container.find(
            class_=lambda x: x and "price" in " ".join(x).lower() if x else False
        )
        if price_tag:
            product["price"] = price_tag.get_text(strip=True)

        # Description
        desc_tag = container.find(
            class_=lambda x: x and any(
                w in " ".join(x).lower()
                for w in ["description", "desc", "excerpt", "summary"]
            ) if x else False
        ) or container.find("p")
        if desc_tag:
            desc_text = desc_tag.get_text(strip=True)
            if len(desc_text) > 10 and desc_text != product["name"]:
                product["description"] = desc_text[:300]

        # Image — best quality
        img_tag = container.find("img")
        img_url = best_image_from_tag(img_tag, base_url)
        if img_url and is_product_image(img_url):
            product["image_url"] = img_url

        # Product link
        link = container.find("a", href=True)
        if link:
            product["product_url"] = make_absolute_url(link["href"], base_url)

        product["source"] = "html_scrape"
        products.append(product)

    return products


# ─────────────────────────────────────────────
#  MAIN ENTRY POINT
# ─────────────────────────────────────────────

def extract_products_from_page(soup: BeautifulSoup, base_url: str, html: str = "") -> list:
    """
    Smart product extractor — platform detect karke best method use karo.
    
    Priority order:
    1. Schema.org JSON-LD (most reliable, platform-agnostic)
    2. Next.js __NEXT_DATA__ 
    3. Shopify/WooCommerce API (agar platform detected)
    4. Generic HTML scrape (fallback)
    """

    all_products = []

    # 1. Schema.org — always try first (works on any platform)
    schema_products = extract_from_schema(soup, base_url)
    if schema_products:
        print(f"📦 Schema.org: {len(schema_products)} products")
        all_products.extend(schema_products)

    # 2. Next.js embedded data
    if "__NEXT_DATA__" in html:
        next_products = extract_nextjs_products(html, soup, base_url)
        if next_products:
            print(f"📦 Next.js: {len(next_products)} products")
            all_products.extend(next_products)

    # 3. If we already have good results, return
    if len(all_products) >= 5:
        return _deduplicate_products(all_products)

    # 4. Platform-specific HTML scrape
    platform = detect_platform(html, soup, base_url)
    print(f"🔍 Detected platform: {platform}")

    if platform == "woocommerce":
        woo_products = _scrape_woo_html(soup, base_url)
        if woo_products:
            print(f"📦 WooCommerce HTML: {len(woo_products)} products")
            all_products.extend(woo_products)
    else:
        generic = _generic_html_scrape(soup, base_url)
        if generic:
            print(f"📦 Generic HTML: {len(generic)} products")
            all_products.extend(generic)

    return _deduplicate_products(all_products)


def _deduplicate_products(products: list) -> list:
    """Name-based deduplication — case insensitive"""
    seen = set()
    unique = []
    for p in products:
        name = (p.get("name") or "").strip().lower()
        if name and name not in seen:
            seen.add(name)
            unique.append(p)
    return unique