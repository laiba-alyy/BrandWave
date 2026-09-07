"""
Products se seed keywords nikalta hai — bina LLM, bina API.

── Ye module kyun bana ──────────────────────────────────────────────────────
Keywords pehle SIRF LLM banata tha, aur prompt mein market_block() ka ye line
jata tha:

    "its demonym, cities, seasons and cultural references are the default"

Nateeja: "Karachi embroidered lawn suit", "Lahore unstitched silk suit",
"Sydney unstitched wedding attire". Koi shopper aise search nahi karta, aur
audit ka Keyword Usage factor 0.0% aata tha kyunke "Karachi" kisi product
title mein hai hi nahi.

Ab ground truth catalogue se aati hai: jo alfaz ASAL product titles/tags mein
sabse zyada baar aate hain, wahi seeds hain. LLM sirf in seeds ko phrases mein
badalta hai. Seeds catalogue se aate hain, is liye wo definition ke mutabiq
products se match karte hain.

Do consumers:
  * seo_llm.generate_keyword_suggestions() — LLM prompt ka grounding
  * seo_auditor.audit_keywords()           — jab brand ke keywords maujood na hon
"""

import re
from collections import Counter

from modules.store_locale import COUNTRY_NAME_TO_ISO, ISO_COUNTRY_NAMES


# ─────────────────────────────────────────────
#  LOCATION BLOCKLIST
# ─────────────────────────────────────────────
#
# Yehi wo list hai jo "Karachi embroidered lawn suit" ko rokti hai. Teen
# hisse: mulk ke naam (store_locale se, taake ek hi source of truth rahe),
# demonyms, aur wo baray sheher jo LLM keywords mein ghusa deta tha.
#
# Sirf ek exception hai — dekho NATURAL_DEMONYMS: kuch demonyms product TYPE
# ka hissa hain ("Pakistani bridal wear" ek asli search term hai), wo keyword
# ke SHURU mein allowed hain.

_COUNTRY_WORDS = set()
for _name in list(ISO_COUNTRY_NAMES.values()) + list(COUNTRY_NAME_TO_ISO):
    for _w in re.findall(r"[a-z]+", _name.lower()):
        if _w != "the":
            _COUNTRY_WORDS.add(_w)

DEMONYMS = {
    "pakistani", "indian", "american", "british", "emirati", "australian",
    "canadian", "bangladeshi", "srilankan", "saudi", "qatari", "kuwaiti",
    "omani", "chinese", "japanese", "korean", "german", "french", "italian",
    "spanish", "dutch", "irish", "turkish", "egyptian", "nigerian", "kenyan",
    "malaysian", "singaporean", "indonesian", "filipino", "thai", "vietnamese",
    "mexican", "brazilian", "swiss", "swedish", "norwegian", "danish", "polish",
    "desi", "asian", "european", "western", "arabic", "arab",
}

CITIES = {
    # PK
    "karachi", "lahore", "islamabad", "rawalpindi", "faisalabad", "multan",
    "peshawar", "quetta", "sialkot", "gujranwala", "hyderabad", "punjab",
    "sindh", "balochistan", "kpk", "gujrat", "bahawalpur", "sargodha",
    # Gulf
    "dubai", "abudhabi", "sharjah", "doha", "riyadh", "jeddah", "muscat",
    "manama",
    # West / other
    "london", "manchester", "birmingham", "glasgow", "leeds", "bradford",
    "chicago", "houston", "dallas", "toronto", "vancouver", "montreal",
    "sydney", "melbourne", "brisbane", "perth", "auckland", "delhi",
    "mumbai", "bangalore", "chennai", "kolkata", "dhaka", "colombo",
    "paris", "berlin", "madrid", "rome", "amsterdam", "istanbul", "cairo",
    "lagos", "nairobi", "johannesburg",
}

LOCATION_TERMS = _COUNTRY_WORDS | DEMONYMS | CITIES

# Demonyms jo product type ka hissa ban chuke hain. Ye SIRF keyword ke shuru
# mein chalte hain: "pakistani bridal wear" theek hai, "lawn suit pakistani"
# nahi. Brief ka exact rule.
NATURAL_DEMONYMS = {"pakistani", "indian", "arabic", "asian", "desi", "western"}


# ─────────────────────────────────────────────
#  STOPWORDS
# ─────────────────────────────────────────────

STOPWORDS = {
    # English glue
    "a", "an", "the", "and", "or", "but", "for", "with", "without", "from",
    "into", "onto", "of", "in", "on", "at", "to", "by", "is", "are", "was",
    "be", "been", "it", "its", "this", "that", "these", "those", "as", "we",
    "you", "your", "our", "their", "his", "her", "all", "any", "each", "more",
    "most", "other", "some", "such", "no", "not", "only", "own", "same", "so",
    "than", "too", "very", "can", "will", "just", "up", "out", "off", "over",
    "under", "again", "then", "once", "here", "there", "when", "where", "why",
    "how", "which", "who", "whom", "what", "if", "about",
    # ecommerce / catalogue noise — ye har store par aate hain, signal zero
    "new", "sale", "shop", "buy", "online", "store", "product", "products",
    "item", "items", "collection", "collections", "code", "sku", "ref",
    "available", "stock", "instock", "sold", "size", "sizes", "color",
    "colour", "colors", "colours", "please", "note", "click", "details",
    "detail", "info", "information", "description", "quality", "made",
    "material", "fabric", "wash", "care", "delivery", "shipping", "return",
    "returns", "price", "pkr", "usd", "rs", "inr", "aed", "gbp", "eur",
    "free", "best", "top", "premium", "exclusive", "special", "offer",
    "discount", "percent", "vol", "edition", "series", "article",
    "design", "style", "styles", "images", "image", "picture",
    "front", "back", "approx", "inches", "meters", "meter", "yards",
}

# Ye tokens akele bekaar hain lekin bigram mein qeemti ("3 piece", "2 pc").
_BIGRAM_ONLY = {"piece", "pieces", "pcs", "set"}

_WORD_RE = re.compile(r"[a-z0-9]+")

# "Un-Stitched" ko "un" + "stitched" mein torhna ghalat seed deta tha
# ("stitched" 59.6% par aa raha tha jabke store UNstitched bechta hai —
# bilkul ulta matlab). Hyphen ke dono taraf harf hon to jorh do.
_INWORD_HYPHEN_RE = re.compile(r"(?<=[a-z])[-_](?=[a-z])")


def _tokens(text: str) -> list[str]:
    """Lowercase alphanumeric tokens. Digits rakhe jate hain — '3 piece' chahiye."""
    return _WORD_RE.findall(_INWORD_HYPHEN_RE.sub("", (text or "").lower()))


def _is_noise(token: str) -> bool:
    if token in STOPWORDS or token in LOCATION_TERMS:
        return True
    if token.isdigit():
        # "3" akela bekaar hai; bigram builder ise alag handle karta hai.
        return True
    return len(token) < 3


def is_location_word(token: str) -> bool:
    return token.lower() in LOCATION_TERMS


def strip_location(keyword: str) -> str:
    """
    Keyword se location tokens nikaal deta hai.

    Leading natural demonym bacha rehta hai ("pakistani bridal wear"), baqi
    har jagah se country/city/demonym gir jata hai ("karachi lawn suit" ->
    "lawn suit").
    """
    tokens = _tokens(keyword)
    if not tokens:
        return ""
    kept = []
    for i, token in enumerate(tokens):
        if is_location_word(token):
            if i == 0 and token in NATURAL_DEMONYMS:
                kept.append(token)
            continue
        kept.append(token)
    return " ".join(kept).strip()


def has_location(keyword: str) -> bool:
    """True agar keyword mein koi aisa location hai jo allowed nahi."""
    tokens = _tokens(keyword)
    for i, token in enumerate(tokens):
        if is_location_word(token):
            if i == 0 and token in NATURAL_DEMONYMS:
                continue
            return True
    return False


# ─────────────────────────────────────────────
#  SEED EXTRACTION
# ─────────────────────────────────────────────

def _clean_tag(tag: str) -> str:
    """
    Shopify tags aksar `namespace:value` hote hain — Maria.B par
    'dhlcode:6204 1900', 'dhldes:Women Unstitch Embroidered shirt', ':hide-zoom'.
    Namespace operational hai, value kabhi kabhi kaam ki. Sirf value lo.
    """
    tag = str(tag or "")
    return tag.split(":", 1)[1] if ":" in tag else tag


def _product_text(product: dict) -> tuple[list[str], str]:
    """
    (title_fields, support_text) — title/category vs tags + description.

    title_fields ALAG rehte hain, jorh kar ek string nahi bante: warna bigram
    builder field ki seema paar kar jata hai aur "suit clothing" (name ka
    aakhri lafz + category) jaise jhoote phrases banta hai.
    """
    tags = product.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    title_fields = [product.get("name") or "", product.get("category") or ""]
    # Description se sirf shuruat — poori description par common words
    # boilerplate (shipping policy waghera) se bhar jate hain.
    support = " ".join(_clean_tag(t) for t in tags) + " " + (product.get("description") or "")[:200]
    return title_fields, support


def extract_seeds(products: list, limit: int = 25) -> list[dict]:
    """
    Catalogue ki asli vocabulary — document frequency ke hisaab se.

    Raw count ke bajaye DOCUMENT frequency (kitne products mein aaya) use hoti
    hai: ek product jo apne title mein "lawn" teen baar likhe, wo poore
    catalogue ka signal nahi bana sakta.

    Return: [{"term": "embroidered", "products": 412, "coverage": 41.2,
              "kind": "unigram"}, ...] — coverage ke hisaab se sorted.
    """
    if not products:
        return []

    unigram_docs = Counter()
    bigram_docs = Counter()
    title_docs = Counter()

    for product in products:
        title_fields, weak = _product_text(product)
        seen_uni = set()
        seen_bi = set()
        seen_title = set()

        for field in title_fields:
            field_tokens = _tokens(field)
            for token in field_tokens:
                if not _is_noise(token):
                    seen_title.add(token)
                    seen_uni.add(token)

            # Bigrams sirf title/category se, aur field ke ANDAR — tags mein
            # 'dhlcode 6204' jaise operational pairs hote hain, aur description
            # ke jumle phrases nahi hain.
            for a, b in zip(field_tokens, field_tokens[1:]):
                if a in STOPWORDS or b in STOPWORDS:
                    continue
                if is_location_word(a) or is_location_word(b):
                    continue
                # "3 piece" chalega (digit + word), "12 34" ya "suit 2" nahi.
                if a.isdigit() and b.isdigit():
                    continue
                if b.isdigit() or len(b) < 3:
                    continue
                if not a.isdigit() and len(a) < 3:
                    continue
                seen_bi.add(f"{a} {b}")

        for token in _tokens(weak):
            if not _is_noise(token):
                seen_uni.add(token)

        title_docs.update(seen_title)
        unigram_docs.update(seen_uni)
        bigram_docs.update(seen_bi)

    total = len(products)
    seeds = []

    # ── Ek seed ko QUALIFY karne ka asool ────────────────────────────────
    # Term ko kisi ASAL product title/category mein aana ZAROORI hai.
    #
    # Ye sirf tidiness nahi — seeds ka poora maqsad hi ye hai ke wo products
    # se match karen (audit ka Keyword Usage factor, aur LLM ki grounding).
    # Sirf tags mein rehne wale terms ye kaam kar hi nahi sakte: Maria.B par
    # bina is gate ke top seeds 'tax rate' (99.9%), 'dhlcode' (99.7%),
    # 'dhldes', 'sizechart' aa rahe the — yani Shopify ka logistics metadata,
    # jise koi shopper Google par search nahi karta.
    title_floor = max(2, total * 0.01)

    def qualifies(term: str) -> bool:
        return all(title_docs[w] >= title_floor for w in term.split())

    # Bigrams par threshold ooncha hai — random word pairs bohat hote hain,
    # sirf wo chahiye jo waqai recurring phrase hon.
    bigram_floor = max(3, total * 0.02)
    for term, count in bigram_docs.most_common(limit * 6):
        if count >= bigram_floor and qualifies(term):
            seeds.append({
                "term": term, "products": count,
                "coverage": round(count / total * 100, 1), "kind": "bigram",
            })

    unigram_floor = max(2, total * 0.01)
    for term, count in unigram_docs.most_common(limit * 6):
        if count >= unigram_floor and term not in _BIGRAM_ONLY and qualifies(term):
            seeds.append({
                "term": term, "products": count,
                "coverage": round(count / total * 100, 1), "kind": "unigram",
            })

    seeds.sort(key=lambda s: s["products"], reverse=True)

    # Ek bigram ke andar jo unigram already aa chuka ho use dobara mat lo —
    # "lawn" aur "lawn suit" dono top 5 mein ho to seeds bekaar ho jate hain.
    out, covered = [], set()
    for seed in seeds:
        if seed["kind"] == "unigram" and seed["term"] in covered:
            continue
        out.append(seed)
        if seed["kind"] == "bigram":
            covered |= set(seed["term"].split())
        if len(out) >= limit:
            break
    return out


def seed_terms(products: list, limit: int = 25) -> list[str]:
    """Sirf strings — un call sites ke liye jinhe counts nahi chahiye."""
    return [s["term"] for s in extract_seeds(products, limit)]


def audit_seed_keywords(products: list, limit: int = 20) -> list[str]:
    """
    Audit ke Keyword Usage factor ke liye seeds.

    Ye JAAN BOOJH KAR generate_keyword_suggestions() se alag hai: audit ko wo
    terms chahiye jo products se match KAR SAKEN, na ke wo long-tail phrases
    jo Google par search hoti hain. Yehi Part 3 ka asal fix hai.
    """
    return [s["term"] for s in extract_seeds(products, limit)]
