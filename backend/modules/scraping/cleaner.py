import os
import json
import re
from dotenv import load_dotenv
from modules.llm_config import (
    RateLimitedError,
    call_with_retry,
    check_sdk_response,
    groq_client,
    reasoning_params,
)
from modules.store_locale import ISO_COUNTRY_NAMES, market_block

load_dotenv()

# Client aur model llm_config se — dekho PURPOSE_MODELS.

# ─────────────────────────────────────────────
#  PRODUCT CATEGORIES
# ─────────────────────────────────────────────

PRODUCT_CATEGORIES = [
    "clothing", "footwear", "jewellery", "makeup", "fragrance",
    "accessories", "home_decor", "food", "bakery", "electronics",
    "stationery", "books", "sports", "toys", "health", "beauty",
    "handmade", "gifts", "other"
]

PRICE_RANGES = {
    "budget": (0, 2000),
    "mid-range": (2001, 8000),
    "premium": (8001, 25000),
    "luxury": (25001, float("inf"))
}

CATEGORY_KEYWORDS = {
    "clothing": [
        "shirt", "kameez", "kurta", "shalwar", "trouser", "pant",
        "jeans", "dress", "frock", "suit", "dupatta", "saree",
        "lehenga", "abaya", "hijab", "shawl", "coat", "jacket",
        "sweater", "hoodie", "top", "blouse", "skirt", "co-ord",
        "kaftan", "lawn", "fabric", "kurti", "waistcoat", "t-shirt",
        "polo", "shorts", "pajama", "linen", "embroidered", "printed",
        "stitched", "unstitched", "denim", "chino", "cargo", "sweatshirt",
        "sweatpant", "tracksuit", "blazer", "formal", "casual", "parka",
        "trench", "cardigan", "pullover", "vest", "overcoat", "tunic",
        "kimono", "romper", "jumpsuit", "playsuit", "coords", "palazzo",
        "culottes", "capri", "tights", "leggings", "nighty", "loungewear", "kids",
        # Activewear ki aam ashya — inke baghair Gymshark jaise store ke
        # products naam se pehchane nahi jate the aur "other" ban jate.
        "tank", "bra", "stringer", "tee", "singlet", "bodysuit",
        "baselayer", "base layer", "crop", "jogger",
        # Socks/underwear clothing(0) mein hain — footwear(1) se PEHLE.
        # Warna "Trainer Socks" aur "Sneaker Socks" jute ban jate the,
        # aur "Sports Tech Boxer" ka "tech" usay electronics(11) mein
        # daal deta tha.
        "sock", "underwear", "boxer", "brief", "thong", "bikini",
        "swimwear", "swimsuit", "sleeve"
    ],
    "footwear": [
        "shoe", "sandal", "heel", "boot", "slipper",   # "flat" hataya:
        # "Flat Peak Cap" jaise naam footwear ban jate the.
        "chappal", "khussa", "sneaker", "loafer", "pump", "wedge",
        "mule", "jogger", "trainer", "oxford", "derby", "espadrille",
        "flip flop", "ankle boot", "knee boot", "platform", "stiletto",
        "slip on", "lace up", "mocassin", "clog", "footwear", "slide", "flip-flop"
    ],
    "jewellery": [
        "necklace", "earring", "bracelet", "ring", "bangle",
        "jhumka", "pendant", "chain", "choker", "tikka", "haar",
        "jewellery", "jewelry", "brooch", "anklet", "nose pin",
        "maang tikka", "jhoomar", "passa", "stud",
        "hoop", "drop earring", "statement necklace", "layered"
    ],
    "makeup": [
        "lipstick", "foundation", "mascara", "eyeshadow", "concealer",
        "blush", "highlighter", "eyeliner", "kajal", "primer",
        "contour", "bronzer", "makeup", "cosmetic", "lip gloss",
        "lip liner", "setting spray", "bb cream", "cc cream",
        "compact", "powder", "palette", "nude", "lip tint"
    ],
    "fragrance": [
        "perfume", "attar", "cologne", "mist", "fragrance",
        "scent", "deodorant", "oud", "body spray", "eau de parfum",
        "eau de toilette", "roll on", "body mist", "incense"
    ],
    "accessories": [
        "bag", "handbag", "clutch", "belt", "wallet", "scarf",
        "cap", "hat", "sunglasses", "pouch", "tote", "backpack",
        "crossbody", "sling bag", "shoulder bag", "mini bag",
        "hair clip", "hair band", "scrunchie", "headband",
        "gloves", "mittens", "tie", "bow tie", "suspender",
        "keychain", "key chain", "lanyard", "phone case", "watch strap",
        # Headwear + gym gear. accessories(5) home_decor(6) aur
        # electronics(11) se PEHLE aati hai, is liye "E-Frame Trucker"
        # ab "frame" se aur "Cable Beanie" "cable" se nahi katt_te.
        "beanie", "trucker", "gymsack", "bottle", "water bottle",
        "shaker", "towel", "duffel", "wristband", "gym bag"
    ],
    "home_decor": [
        "cushion", "bedsheet", "curtain", "candle", "towel",
        "pillow", "blanket", "duvet", "vase", "diffuser", "decor",
        "table cloth", "runner", "rug", "carpet", "lamp",
        "frame", "mirror", "clock", "basket", "tray", "planter",
        "pot", "figurine", "wall art", "poster", "tapestry",
        "bed cover", "quilt", "comforter", "throw", "bolster"
    ],
    "food": [
        "food", "snack", "chocolate", "sauce", "spice", "drink",
        "juice", "tea", "coffee", "pickle", "jam", "honey",
        "dry fruit", "nuts", "chips", "crisp", "biscuit",
        "noodle", "pasta", "rice", "flour", "oil", "ghee",
        "masala", "curry", "chutney", "syrup", "energy drink",
        "protein bar", "granola", "cereal", "soup", "broth"
    ],
    "bakery": [
        "cake", "cookie", "bread", "pastry", "muffin", "brownie",
        "biscuit", "dessert", "cupcake", "tart", "pie", "donut",
        "waffle", "pancake", "croissant", "loaf", "roll", "bun",
        "macaroon", "cheesecake", "truffle", "fudge", "pudding"
    ],
    "beauty": [
        "serum", "moisturiser", "moisturizer", "toner", "face wash",
        "scrub", "mask", "hair oil", "shampoo", "conditioner",
        "skincare", "sunscreen", "spf", "cleanser", "exfoliant",
        "eye cream", "lip balm", "body lotion", "body butter",
        "body wash", "shower gel", "soap", "micellar", "essence",
        "ampoule", "retinol", "vitamin c", "hyaluronic", "niacinamide",
        "hair mask", "hair serum", "hair spray", "dry shampoo"
    ],
    "health": [
        "vitamin", "supplement", "protein", "herbal", "organic",
        "collagen", "omega", "probiotic", "prebiotic", "zinc",
        "iron", "calcium", "multivitamin", "detox", "immunity",
        "weight loss", "fat burner", "creatine", "whey", "bcaa",
        "ayurvedic", "homeopathic", "medical", "health"
    ],
    "electronics": [
        "phone", "laptop", "charger", "cable", "earphone",
        "speaker", "smartwatch", "tablet", "keyboard", "mouse",
        "monitor", "headphone", "airpod", "powerbank", "adapter",
        "usb", "hdmi", "router", "camera", "drone", "gadget",
        "electronic", "device", "tech", "smart"
    ],
    "sports": [
        "gym", "yoga", "sports", "fitness", "workout", "cricket",
        "football", "basketball", "tennis", "badminton", "cycling",
        "running", "hiking", "swimming", "boxing", "martial arts",
        "dumbell", "barbell", "resistance band", "mat", "gloves",
        "jersey", "kit", "athletic", "activewear", "compression"
    ],
    "stationery": [
        "pen", "pencil", "notebook", "diary", "journal", "planner",
        "stationery", "marker", "highlighter", "eraser", "ruler",
        "scissors", "tape", "glue", "folder", "binder", "envelope",
        "card", "sticky note", "washi tape", "stamp", "ink"
    ],
    "books": [
        "book", "novel", "guide", "textbook", "magazine", "comic",
        "manga", "ebook", "literature", "fiction", "nonfiction",
        "biography", "autobiography", "poetry", "anthology", "cookbook",
        "children book", "religious", "quran", "islamic", "educational"
    ],
    "toys": [
        "toy", "doll", "puzzle", "game", "lego", "board game",
        "action figure", "stuffed animal", "teddy", "plush",
        "remote control", "rc car", "building block", "play set",
        "educational toy", "baby toy", "toddler"
    ],
    "handmade": [
        "handmade", "handcrafted", "custom", "artisan", "bespoke",
        "hand painted", "hand embroidered", "hand knitted",
        "hand stitched", "hand woven", "hand printed", "craft"
    ],
    "gifts": [
        "gift", "hamper", "bundle", "gift set", "gift box",
        "gift card", "voucher", "combo", "package", "surprise box",
        "corporate gift", "wedding gift", "birthday gift", "eid gift"
    ],
}


# ─────────────────────────────────────────────
#  HELPERS — NO LLM
# ─────────────────────────────────────────────

# ── Category matching ka engine ──────────────────────────────────────────
#
# Pehle yahan seedha `kw in text` tha — bemaqsad substring match. Us ka natija
# ye tha ke Gymshark ka ek tag "nosizeguide" books ke keyword "guide" se match
# kar gaya, aur ek WATER BOTTLE ki category "books" ban gayi. Isi tarah "pen"
# "open" se, "card" "cardigan" se, aur "roll" "enrollment" se match karta tha.
#
# Ab do tabdeeliyan hain:
#   1. Text pehle NORMALISE hota hai — har non-alphanumeric (>, _, -, /) space
#      ban jata hai. Ye zaroori hai kyunke Shopify ka product_type
#      "Mens>Apparel>SS Tops>t_shirt" jaisa hota hai, aur "_" regex mein WORD
#      character hai — yani bina normalise kiye \bshirt\b "t_shirt" par fail
#      kar jata.
#   2. Match word-boundary par hota hai, to "nosizeguide" ab "guide" nahi hai.
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")


def _normalise(text: str) -> str:
    """lowercase + har non-alphanumeric ko single space."""
    return _NON_WORD_RE.sub(" ", (text or "").lower()).strip()


def _compile_words(words) -> re.Pattern:
    """
    Word-boundary regex. Lambe phrase pehle, taake wo chhote se na katen.

    (?:e?s)? JAAN BOOJH KAR hai: keyword list zyadatar WAAHID hai — "pant",
    "top", "shoe" — jab ke Shopify ka product_type JAMA likhta hai:
    "Womens>Apparel>Pants>wide_leg", "Sleeveless Tops>tanks". Purana
    substring match ye farq chhupa deta tha; word boundary lagate hi "pant"
    ne "pants" par match karna chhod diya aur trousers FOOTWEAR ban gaye.
    Ab plural chalta hai, magar "nosizeguide" phir bhi "guide" nahi banta —
    kyunke boundary lafz ke SHURU mein bhi lagti hai.
    """
    parts = sorted({_normalise(w) for w in words if _normalise(w)},
                   key=len, reverse=True)
    return re.compile(
        r"\b(?:" + "|".join(re.escape(x) for x in parts) + r")(?:e?s)?\b"
    )


# "other" JAAN BOOJH KAR bahar hai. Wo fallback hai, signal nahi — aur
# Shopify apni taxonomy mein lafz "Other" istemal karta hai
# ("Womens>Apparel>Other>skirt"), jis se step 1 usay category samajh kar
# foran "other" return kar deta tha aur "skirt" tak pohanchta hi nahi tha.
_CATEGORY_NAME_RE = {c: _compile_words([c]) for c in PRODUCT_CATEGORIES if c != "other"}
_CATEGORY_KEYWORD_RE = {c: _compile_words(k) for c, k in CATEGORY_KEYWORDS.items()}


def _strip_colour_suffix(name: str) -> str:
    """
    "Gymshark Legacy Deep Cuff Beanie - Cement Brown" -> "Gymshark Legacy Deep Cuff Beanie"

    Sirf " - " (dono taraf space) par kaat_ta hai, is liye "E-Frame" aur
    "T-Shirt" jaise naam nahi tootte.
    """
    n = (name or "").strip()
    return n.rsplit(" - ", 1)[0] if " - " in n else n


def detect_product_category(name: str, product_type: str = "", tags: list = None) -> str:
    """
    Shopify product_type -> name -> tags se category detect karo. No LLM.
    Returns one of PRODUCT_CATEGORIES.

    TARTEEB AHEM HAI. Pehle tags name se OOPAR thay, aur tags sab se kam
    qabil-e-etibar source hain — un mein "algolia", "bfcm24", "all-products",
    "nosizeguide" jaisa operational kachra hota hai jo category ke liye likha
    hi nahi gaya. Us ki wajah se "Element Baselayer Shorts" (jis ke naam mein
    saaf "shorts" hai) tags se books ban jata tha. Ab name pehle dekha jata
    hai aur tags sirf aakhri sahara hain.
    """
    # 1. product_type — sab se qabil-e-etibar (merchant ne khud set kiya)
    pt = _normalise(product_type)
    if pt:
        for cat, rx in _CATEGORY_NAME_RE.items():
            if rx.search(pt):
                return cat
        for cat, rx in _CATEGORY_KEYWORD_RE.items():
            if rx.search(pt):
                return cat

    # 2. Product ka naam — RANG ka hissa kaat kar
    #
    # Bohat se stores product ko "<Cheez> - <Rang>" likhte hain, aur rang ke
    # naam category keywords se takra jate hain:
    #   "Arrival Tank - Powder Mauve"     -> powder  -> makeup
    #   "Drop Arm Tank - Ink Teal"        -> ink     -> stationery
    #   "Sports Bra - Truffle Brown"      -> truffle -> bakery
    #   "Stringer - Modern Blush"         -> blush   -> makeup
    # Rang classification ke liye shor hai, signal nahi — is liye aakhri
    # " - " ke baad wala hissa hata dete hain. ("E-Frame" jaise naam
    # mehfooz rehte hain kyunke wahan dashes ke ird-gird spaces nahi hain.)
    nm = _normalise(_strip_colour_suffix(name))
    if nm:
        for cat, rx in _CATEGORY_KEYWORD_RE.items():
            if rx.search(nm):
                return cat

    # 3. Tags — aakhri sahara
    if tags:
        tag_text = _normalise(" ".join(str(t) for t in tags))
        if tag_text:
            for cat, rx in _CATEGORY_KEYWORD_RE.items():
                if rx.search(tag_text):
                    return cat

    return "other"


def detect_price_range(products: list) -> str:
    """Products ki average price se range detect karo. No LLM."""
    prices = []
    for p in products:
        price_str = p.get("price", "") or ""
        # Remove commas and currency symbols before parsing
        cleaned = re.sub(r'[^\d.]', '', price_str.replace(",", ""))
        if cleaned:
            try:
                prices.append(float(cleaned))
            except ValueError:
                continue

    if not prices:
        return "mid-range"

    avg_price = sum(prices) / len(prices)

    for range_name, (low, high) in PRICE_RANGES.items():
        if low <= avg_price <= high:
            return range_name

    return "mid-range"


def get_unique_categories_from_products(products: list) -> list:
    """
    Already categorized products se unique categories nikalo.
    LLM categories ke saath combine karne ke liye use karo.
    """
    cats = set()
    for p in products:
        cat = p.get("category", "")
        if cat and cat != "other":
            cats.add(cat)
    return list(cats)


# ─────────────────────────────────────────────
#  LLM — HOME COUNTRY INFERENCE (1 call)
# ─────────────────────────────────────────────

def infer_home_country(raw_text: str, website_url: str, signals: dict) -> dict:
    """
    Page content se brand ka HOME country nikalta hai — deterministic signals
    ke saath cross-check ke liye.

    ── Ye kyun chahiye ──────────────────────────────────────────────────────
    Deterministic signals akele kaafi nahi. mariab.pk par:
        ccTLD .pk    -> Pakistan
        meta country -> AE  (Dubai mein registered)
        meta city    -> Dubai
    Sirf meta.json dekhein to ek Pakistani fashion brand "Emirati" ban jata
    hai aur uske saare keywords Dubai/Abu Dhabi ke ban jate hain.

    LLM wo cheezein padh sakta hai jo structured data mein hoti hi nahi:
    "About Us" ka matn, head office ka address, phone number ka format
    (+92 vs +971), zabaan, aur cultural references.

    ISO code deta hai (2 letters) taake milana aasan rahe — mulk ka poora
    naam LLM ki apni spelling par nahi chhora jata.
    """
    hints = []
    if signals.get("tld_iso"):
        hints.append(f"- Domain TLD suggests: {signals['tld_iso']}")
    if signals.get("meta_country_iso"):
        hints.append(
            f"- Shopify store settings say country={signals['meta_country_iso']}"
            f"{', city=' + signals['meta_city'] if signals.get('meta_city') else ''}"
            " (NOTE: this is the merchant's registered/billing address, which is"
            " often NOT where the brand is from)"
        )
    if signals.get("currencies"):
        hints.append(
            f"- Currencies on the storefront: {', '.join(signals['currencies'])}"
            " (brands often price in foreign currencies for overseas buyers)"
        )
    if signals.get("store_name"):
        hints.append(f"- Store name: {signals['store_name']}")
    if signals.get("money_format"):
        hints.append(f"- Money format: {signals['money_format']}")

    prompt = f"""
You are identifying where an e-commerce brand is actually FROM.

Website: {website_url}

Signals already collected:
{chr(10).join(hints) or "- none"}

Page text:
{raw_text[:2500]}

Decide the brand's HOME country — the country it originates from and where
its main customer base is. This is NOT necessarily the registered company
address, and NOT necessarily where its currency points.

Evidence to weigh, strongest first:
1. Explicit statements ("a Pakistani brand", "founded in Lahore")
2. Head office / store addresses in the page text
3. Phone number country code (+92 Pakistan, +971 UAE, +44 UK, +1 US)
4. Language, cultural and seasonal references, product vocabulary
5. Domain TLD

Also list every OTHER country it sells or ships to. Look for: international
shipping pages, currency/country selectors, overseas store locations, "we ship
worldwide" notices, and prices quoted in foreign currencies. Many brands from
one country sell heavily into others — those are real SEO markets and must not
be missed.

Return ONLY valid JSON:
{{
    "home_country": "two-letter ISO code, e.g. PK",
    "confidence": "high | medium | low",
    "reasoning": "one short sentence citing the evidence you used",
    "also_sells_to": ["ISO codes of other markets, [] if none stated"]
}}

Rules:
- home_country MUST be a 2-letter ISO 3166-1 code, nothing else
- If the page genuinely gives no clue, use null for home_country
- Do NOT guess from the currency alone
"""

    try:
        client, model = groq_client("scraping")
        response = call_with_retry(
            lambda: client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                # gpt-oss reasoning tokens OUTPUT se pehle kharch karta hai.
                # 1,200 par bruvi.com ki inference beech mein kat gayi thi aur
                # detection chup-chaap currency par gir gayi — is liye
                # reasoning_effort=low + bara budget.
                extra_body=reasoning_params(model),
                max_tokens=3000,
            ),
            what="Home country inference",
        )
        result = check_sdk_response(response, "Home country inference", max_tokens=3000)
        parsed = json.loads(re.sub(r'```json|```', '', result).strip())

        iso = (parsed.get("home_country") or "").strip().upper()
        if len(iso) != 2 or iso not in ISO_COUNTRY_NAMES:
            iso = None

        markets = []
        for code in parsed.get("also_sells_to") or []:
            code = str(code).strip().upper()
            if len(code) == 2 and code in ISO_COUNTRY_NAMES and code != iso:
                markets.append(code)

        print(f"🧭 LLM home country: {iso} ({parsed.get('confidence')}) — {parsed.get('reasoning')}")
        return {"iso": iso, "confidence": parsed.get("confidence"),
                "reasoning": parsed.get("reasoning"), "also_sells_to": markets}

    except RateLimitedError:
        raise
    except Exception as e:
        # Country inference fail hone par scrape rukna nahi chahiye —
        # deterministic signals (TLD, currency) phir bhi kaam karte hain.
        print(f"Home country inference error: {e}")
        return {"iso": None, "confidence": None, "reasoning": None, "also_sells_to": []}


# ─────────────────────────────────────────────
#  LLM — BUSINESS INFO (1 call)
# ─────────────────────────────────────────────

def clean_and_extract_business_info(raw_text: str, website_url: str, locale: dict = None) -> dict:
    """
    LLM se business info extract karo — sirf 1 call.

    locale = detect_store_locale() ka nateeja. Pehle yahan prompt ek hi
    region hardcode karta tha, jis se HAR store ka description aur audience
    usi region ka rang le leta tha. Ab jo country asal mein detect hui wahi
    jati hai, aur detect na ho to koi country context jata hi nahi.
    """

    categories_list = ", ".join(PRODUCT_CATEGORIES)

    prompt = f"""
You are analyzing a scraped Shopify store.
Website URL: {website_url}

{market_block(locale)}

Raw scraped text:
{raw_text[:3000]}

Extract and return ONLY a valid JSON object:
{{
    "business_name": "store/brand name",
    "description": "2-3 sentence description of what this store sells",
    "target_audience": "describe customers: gender, age range, interests",
    "business_type": "type e.g. clothing_brand, food_store, electronics_store, handmade_crafts, multi_category",
    "product_categories": ["list of categories this store sells"],
    "key_offerings": ["top 3-5 product types"]
}}

Rules:
- Return ONLY the JSON, no extra text or markdown
- If info not found, use null
- Do not make up information
- product_categories MUST only contain values from this exact list:
  {categories_list}
- If a category does not match the list, use the closest match or use "other"
- Include ALL categories that apply to this store — do not miss any
"""

    try:
        client, model = groq_client("scraping")
        response = call_with_retry(
            lambda: client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000
            ),
            what="Business info extraction",
        )

        result = check_sdk_response(response, "Business info extraction", max_tokens=2000)
        result = re.sub(r'```json|```', '', result).strip()
        parsed = json.loads(result)

        # Post-process: validate categories against allowed list
        raw_cats = parsed.get("product_categories") or []
        validated_cats = [c for c in raw_cats if c in PRODUCT_CATEGORIES]

        # If LLM returned nothing valid, fallback to "other"
        if not validated_cats:
            validated_cats = ["other"]

        parsed["product_categories"] = validated_cats
        return parsed

    # Rate limit par khaali/degraded brand profile save karna sabse mehnga
    # silent failure hai - ye data har doosre module ko feed karta hai.
    except RateLimitedError:
        raise

    except json.JSONDecodeError:
        return {
            "business_name": None,
            "description": None,
            "target_audience": None,
            "business_type": None,
            "product_categories": [],
            "key_offerings": []
        }
    except Exception as e:
        print(f"LLM business info error: {e}")
        return {}


# ─────────────────────────────────────────────
#  LLM — TARGET AUDIENCE (1 call)
# ─────────────────────────────────────────────

def infer_target_audience(business_info: dict, products: list, locale: dict = None) -> str:
    """
    Target audience infer karo — sirf 1 call.

    Ye field aage SEO keywords, blog, ad copy sab mein feed hoti hai, is liye
    yahan ka hardcoded mulk poore platform mein phail jata tha. Ab audience
    wahi market reflect karti hai jo detect hui — US store ko US audience,
    .pk store ko uski apni.
    """

    # Combine LLM categories + keyword-detected categories from products
    llm_categories = business_info.get("product_categories") or []
    detected_categories = get_unique_categories_from_products(products)
    all_categories = list(set(llm_categories + detected_categories))

    price_range = detect_price_range(products)
    product_names = [p.get("name", "") for p in products[:8]]
    business_type = business_info.get("business_type") or ""

    prompt = f"""
Based on this Shopify store, describe the target audience in ONE sentence.

Store: {business_info.get('business_name', '')}
Business Type: {business_type}
Price Range: {price_range}
Categories: {all_categories}
Sample products: {product_names}

{market_block(locale, audience_hint=True)}

Return ONLY one sentence.
The sentence must name the market, an age range, and what they are looking for.

Follow this SHAPE, but use ONLY the market given above:
  "<market> <shopper type> aged <range> who want <what this store sells>"

Do not copy any country from these shape examples — they are placeholders:
- "<COUNTRY> coffee enthusiasts aged 25-45 who want single-serve brewing at home"
- "<COUNTRY> home decor buyers aged 30-50 seeking handmade ceramics"
"""

    try:
        client, model = groq_client("scraping")
        response = call_with_retry(
            lambda: client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=800
            ),
            what="Audience inference",
        )
        return check_sdk_response(response, "Audience inference", max_tokens=800)

    except RateLimitedError:
        raise

    except Exception as e:
        print(f"Audience inference error: {e}")
        # Fallback bhi country-neutral hai. Pehle yahan ek mulk ka naam likha
        # tha, yani LLM fail hone par har store ko usi mulk ki audience milti thi.
        return business_info.get("target_audience", "Online shoppers looking for quality products")