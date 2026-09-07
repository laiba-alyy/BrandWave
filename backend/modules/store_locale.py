"""
Store ka market (country + currency) detect karta hai, aur har LLM prompt ke
liye location-aware context banata hai.

── Ye module kyun bana ──────────────────────────────────────────────────────
Pehle EK hi mulk 6 modules ke prompts mein HARDCODED tha — scraping cleaner,
SEO keywords, SEO content, SEO blog, ad copy, chatbot. BrandWave ab duniya bhar
ke Shopify stores target karta hai, to ek US coffee brand ke liye bhi us doosre
mulk ke shehron wale keywords ban rahe the — bilkul be-maani.

Ab country ek hi jagah detect hoti hai (scrape ke waqt), brand profile mein
save hoti hai, aur har prompt wahin se padhta hai.

── Sabse ahem rule ──────────────────────────────────────────────────────────
Detection FAIL ho jaye to kisi bhi mulk par default MAT karo.
Us soorat mein prompt se country context bilkul nikal jata hai aur LLM ko
product data se khud infer karne ka kaha jata hai. Ghalat country batana
"country nahi pata" se kahin zyada nuqsan-deh hai.
"""

import re
from urllib.parse import urlparse

import httpx


# ─────────────────────────────────────────────
#  LOOKUP TABLES
# ─────────────────────────────────────────────

# ISO 3166-1 alpha-2 → display name. Shopify /meta.json isi format mein
# country deta hai ("US", "PK"). List mukammal nahi hai — jo code yahan na
# mile uske liye raw code hi use hota hai (ghalat naam se behtar hai).
ISO_COUNTRY_NAMES = {
    "AE": "the United Arab Emirates", "AR": "Argentina", "AT": "Austria",
    "AU": "Australia", "BD": "Bangladesh", "BE": "Belgium", "BH": "Bahrain",
    "BR": "Brazil", "CA": "Canada", "CH": "Switzerland", "CL": "Chile",
    "CN": "China", "CO": "Colombia", "CZ": "Czechia", "DE": "Germany",
    "DK": "Denmark", "EG": "Egypt", "ES": "Spain", "FI": "Finland",
    "FR": "France", "GB": "the United Kingdom", "GR": "Greece",
    "HK": "Hong Kong", "ID": "Indonesia", "IE": "Ireland", "IL": "Israel",
    "IN": "India", "IT": "Italy", "JP": "Japan", "KE": "Kenya",
    "KR": "South Korea", "KW": "Kuwait", "LK": "Sri Lanka", "MA": "Morocco",
    "MX": "Mexico", "MY": "Malaysia", "NG": "Nigeria", "NL": "the Netherlands",
    "NO": "Norway", "NZ": "New Zealand", "OM": "Oman", "PH": "the Philippines",
    "PK": "Pakistan", "PL": "Poland", "PT": "Portugal", "QA": "Qatar",
    "RO": "Romania", "RU": "Russia", "SA": "Saudi Arabia", "SE": "Sweden",
    "SG": "Singapore", "TH": "Thailand", "TR": "Turkey", "TW": "Taiwan",
    "UA": "Ukraine", "US": "the United States", "VN": "Vietnam",
    "ZA": "South Africa",
}

# Currency → country. Sirf wahi currencies jo EK mulk ko point karti hain.
# EUR/XAF/XCD jaisi shared currencies yahan JAAN BOOJH KAR nahi hain — un se
# country guess karna ghalat jawab dega, is liye wo TLD/address par chhori
# jati hain (dekho AMBIGUOUS_CURRENCIES).
CURRENCY_TO_ISO = {
    "AED": "AE", "ARS": "AR", "AUD": "AU", "BDT": "BD", "BHD": "BH",
    "BRL": "BR", "CAD": "CA", "CHF": "CH", "CLP": "CL", "CNY": "CN",
    "COP": "CO", "CZK": "CZ", "DKK": "DK", "EGP": "EG", "GBP": "GB",
    "HKD": "HK", "IDR": "ID", "ILS": "IL", "INR": "IN", "JPY": "JP",
    "KES": "KE", "KRW": "KR", "KWD": "KW", "LKR": "LK", "MAD": "MA",
    "MXN": "MX", "MYR": "MY", "NGN": "NG", "NOK": "NO", "NZD": "NZ",
    "OMR": "OM", "PHP": "PH", "PKR": "PK", "PLN": "PL", "QAR": "QA",
    "RON": "RO", "RUB": "RU", "SAR": "SA", "SEK": "SE", "SGD": "SG",
    "THB": "TH", "TRY": "TR", "TWD": "TW", "UAH": "UA", "USD": "US",
    "VND": "VN", "ZAR": "ZA",
}

# Ye currencies kai mulkon mein chalti hain — country IN SE kabhi infer mat karo.
AMBIGUOUS_CURRENCIES = {"EUR", "XAF", "XOF", "XCD", "XPF"}

# ccTLD → country. Sirf wo TLDs jo asal mein geographic hain.
# .co, .io, .ai, .tv, .me, .cc jaisi "vanity" TLDs yahan nahi hain — unhe
# duniya bhar ke brands generic tor par use karte hain.
TLD_TO_ISO = {
    "ae": "AE", "ar": "AR", "at": "AT", "au": "AU", "bd": "BD", "be": "BE",
    "bh": "BH", "br": "BR", "ca": "CA", "ch": "CH", "cl": "CL", "cn": "CN",
    "cz": "CZ", "de": "DE", "dk": "DK", "eg": "EG", "es": "ES", "fi": "FI",
    "fr": "FR", "gr": "GR", "hk": "HK", "id": "ID", "ie": "IE", "il": "IL",
    "in": "IN", "it": "IT", "jp": "JP", "ke": "KE", "kr": "KR", "kw": "KW",
    "lk": "LK", "ma": "MA", "mx": "MX", "my": "MY", "ng": "NG", "nl": "NL",
    "no": "NO", "nz": "NZ", "om": "OM", "ph": "PH", "pk": "PK", "pl": "PL",
    "pt": "PT", "qa": "QA", "ro": "RO", "ru": "RU", "sa": "SA", "se": "SE",
    "sg": "SG", "th": "TH", "tr": "TR", "tw": "TW", "ua": "UA", "uk": "GB",
    "us": "US", "vn": "VN", "za": "ZA",
}

# Address block mein dikhne wale mulk ke naam → ISO. Aakhri fallback,
# jab meta.json, currency aur TLD teeno khali hon.
COUNTRY_NAME_TO_ISO = {
    "pakistan": "PK", "united states": "US", "usa": "US",
    "united kingdom": "GB", "england": "GB", "scotland": "GB", "wales": "GB",
    "united arab emirates": "AE", "saudi arabia": "SA", "australia": "AU",
    "canada": "CA", "india": "IN", "bangladesh": "BD", "sri lanka": "LK",
    "singapore": "SG", "malaysia": "MY", "indonesia": "ID", "germany": "DE",
    "france": "FR", "italy": "IT", "spain": "ES", "netherlands": "NL",
    "ireland": "IE", "new zealand": "NZ", "south africa": "ZA",
    "nigeria": "NG", "kenya": "KE", "japan": "JP", "china": "CN",
    "philippines": "PH", "thailand": "TH", "vietnam": "VN", "turkey": "TR",
    "egypt": "EG", "qatar": "QA", "kuwait": "KW", "oman": "OM",
    "bahrain": "BH", "mexico": "MX", "brazil": "BR",
}

# Currency code → wo symbol jo shopper apne store par dekhta hai. Jo code
# yahan na mile uske liye code hi prefix ban jata hai ("SEK 249.00") — ghalat
# symbol lagane se behtar hai.
CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "PKR": "Rs.", "INR": "₹",
    "JPY": "¥", "CNY": "¥", "AUD": "A$", "CAD": "C$", "NZD": "NZ$",
    "SGD": "S$", "HKD": "HK$", "BRL": "R$", "MXN": "MX$", "ZAR": "R",
    "TRY": "₺", "RUB": "₽", "KRW": "₩", "PHP": "₱",
    "THB": "฿", "VND": "₫", "NGN": "₦", "ILS": "₪",
    "UAH": "₴", "BDT": "৳", "LKR": "Rs.", "AED": "AED",
    "SAR": "SAR", "QAR": "QAR", "KWD": "KWD", "BHD": "BHD", "OMR": "OMR",
    "CHF": "CHF", "SEK": "SEK", "NOK": "NOK", "DKK": "DKK", "PLN": "zł",
}

# Jab country na mile to profile mein yahi save hota hai. Kisi mulk par
# default karna hi asal bug tha.
UNKNOWN_COUNTRY = "international"

_UA = {"User-Agent": "Mozilla/5.0 (compatible; BrandWave/1.0)"}


# ─────────────────────────────────────────────
#  DETECTION
# ─────────────────────────────────────────────

def _iso_to_name(iso):
    if not iso:
        return None
    iso = iso.strip().upper()
    if len(iso) != 2:
        return None
    return ISO_COUNTRY_NAMES.get(iso, iso)


def _iso_from_currency(currency):
    if not currency:
        return None
    code = currency.strip().upper()
    if code in AMBIGUOUS_CURRENCIES:
        return None
    return CURRENCY_TO_ISO.get(code)


def _iso_from_tld(website_url: str):
    """
    Domain ke ccTLD se country. `.com.pk` / `.co.uk` jaise do-hisse wale
    suffixes bhi is se handle ho jate hain kyunke sirf AAKHRI label dekha
    jata hai. `.com`/`.shop`/`.store` se kuch nahi milta — wo generic hain
    (yehi bruvi.com ka case hai).
    """
    host = (urlparse(website_url).netloc or website_url).lower().split(":")[0]
    parts = [p for p in host.split(".") if p]
    if len(parts) < 2:
        return None
    return TLD_TO_ISO.get(parts[-1])


def _fetch_shopify_meta(website_url: str) -> dict:
    """
    Shopify ka /meta.json — country aur currency ka SABSE authoritative source.
    Har Shopify storefront ise serve karta hai aur ye merchant ki apni store
    settings se aata hai (guess nahi):
        {"country":"US","currency":"USD","city":"Beverly Hills", ...}
    """
    url = website_url if website_url.startswith("http") else "https://" + website_url
    parsed = urlparse(url)
    base = parsed.scheme + "://" + parsed.netloc
    try:
        res = httpx.get(base + "/meta.json", timeout=10, headers=_UA, follow_redirects=True)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict):
                return data
    except Exception as e:
        print("[locale] meta.json unavailable: " + str(e))
    return {}


def _currency_from_html(html: str):
    """
    meta.json na mile to HTML se currency. Shopify theme layouts ye chaar
    shapes mein currency inject karte hain.
    """
    if not html:
        return None

    patterns = [
        r'Shopify\.currency\s*=\s*\{[^}]*?"active"\s*:\s*"([A-Z]{3})"',
        r'["\']currency["\']\s*:\s*["\']([A-Z]{3})["\']',
        r'itemprop=["\']priceCurrency["\'][^>]*content=["\']([A-Z]{3})["\']',
        r'property=["\']og:price:currency["\'][^>]*content=["\']([A-Z]{3})["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            code = match.group(1).upper()
            if code in CURRENCY_TO_ISO or code in AMBIGUOUS_CURRENCIES:
                return code
    return None


def _iso_from_html_address(html: str):
    """
    Footer/contact/shipping text mein mulk ka naam dhoondo.

    Sirf tab chalta hai jab baaki sab fail ho — ye sabse KAMZOR signal hai,
    kyunke "we ship to Canada" bhi match kar jata hai. Is liye jo naam page
    mein sabse PEHLE aata hai wahi lete hain (address footer mein hota hai,
    magar shipping banners upar) aur ise aakhri fallback rakha hai.
    """
    if not html:
        return None

    text = re.sub(r"<[^>]+>", " ", html).lower()
    text = re.sub(r"\s+", " ", text)

    best_iso, best_pos = None, len(text)
    for name, iso in COUNTRY_NAME_TO_ISO.items():
        match = re.search(r"\b" + re.escape(name) + r"\b", text)
        if match and match.start() < best_pos:
            best_iso, best_pos = iso, match.start()
    return best_iso


def _currencies_from_html(html: str) -> list:
    """
    HTML mein jitni bhi currencies nazar aayen, sab. Multi-currency stores
    apna currency selector inhi shapes mein render karte hain.
    """
    if not html:
        return []

    found = []
    patterns = [
        r'Shopify\.currency\s*=\s*\{[^}]*?"active"\s*:\s*"([A-Z]{3})"',
        r'["\']currency["\']\s*:\s*["\']([A-Z]{3})["\']',
        r'itemprop=["\']priceCurrency["\'][^>]*content=["\']([A-Z]{3})["\']',
        r'property=["\']og:price:currency["\'][^>]*content=["\']([A-Z]{3})["\']',
        # currency selector <option value="AED">
        r'<option[^>]*\bvalue=["\']([A-Z]{3})["\']',
        r'data-currency=["\']([A-Z]{3})["\']',
    ]
    known = set(CURRENCY_TO_ISO) | AMBIGUOUS_CURRENCIES
    for pattern in patterns:
        for code in re.findall(pattern, html):
            code = code.upper()
            if code in known and code not in found:
                found.append(code)
    return found



# Shipping policy par itne se zyada mulk mile to wo shipping zones nahi,
# poora country-picker dropdown hai — us se markets infer karna galat hoga.
_MAX_SHIPPING_COUNTRIES = 18


def _shipping_policy_countries(website_url: str) -> list:
    """
    Shopify ke /policies/shipping-policy se wo mulk nikalta hai jahan store
    bhejta hai.

    ── Ye kyun chahiye ──────────────────────────────────────────────────────
    Markets pehle sirf LLM ke `also_sells_to` par depend karte the, jo
    homepage text par chalta hai — aur homepage par international shipping
    ka zikr aksar hota hi nahi. Nateeja: ek hi store do run mein 7 markets
    aur phir 0 markets deta tha. Shipping policy deterministic hai.

    mariab.pk par ye page 12 mulk deta hai (Australia, Canada, France,
    Germany, Japan, Singapore, ...), jabke alkaramstudio par sirf Pakistan —
    yani signal asli hai, shor nahi.

    Safety: agar bohat saare mulk mil jayen to wo shipping zones nahi balki
    country picker hai; us soorat mein khali list wapas jati hai.
    """
    url = website_url if website_url.startswith("http") else "https://" + website_url
    parsed = urlparse(url)
    base = parsed.scheme + "://" + parsed.netloc

    try:
        res = httpx.get(base + "/policies/shipping-policy", timeout=15,
                        headers=_UA, follow_redirects=True)
        if res.status_code != 200:
            return []
        text = re.sub(r"<[^>]+>", " ", res.text).lower()
        text = re.sub(r"\s+", " ", text)
    except Exception as e:
        print("[locale] shipping policy unavailable: " + str(e))
        return []

    found = []
    for name, iso in COUNTRY_NAME_TO_ISO.items():
        if re.search(r"\b" + re.escape(name) + r"\b", text) and iso not in found:
            found.append(iso)

    if len(found) > _MAX_SHIPPING_COUNTRIES:
        print(f"[locale] shipping policy listed {len(found)} countries — "
              "looks like a country picker, ignoring")
        return []
    return found


def collect_locale_signals(website_url: str, html: str = "") -> dict:
    """
    Har available signal jama karta hai — koi faisla nahi karta.

    Faisla resolve_home_country() karta hai, LLM ki inference ke saath.
    Dono ko alag rakhne ki wajah: signals deterministic aur test karne mein
    aasan hain, jabke faisla policy hai jo badal sakti hai.
    """
    meta = _fetch_shopify_meta(website_url)

    meta_country = (meta.get("country") or "").strip().upper()
    meta_currency = (meta.get("currency") or "").strip().upper()

    currencies = []
    if meta_currency:
        currencies.append(meta_currency)
    for code in _currencies_from_html(html):
        if code not in currencies:
            currencies.append(code)

    # meta.json ka ships_to_countries: ["*"] ka matlab "duniya bhar",
    # baqi 2-letter codes asli markets hain.
    ships_raw = meta.get("ships_to_countries") or []
    ships_to = [c.upper() for c in ships_raw if isinstance(c, str) and len(c) == 2]
    ships_worldwide = "*" in ships_raw

    return {
        "tld_iso": _iso_from_tld(website_url),
        "shipping_countries": _shipping_policy_countries(website_url),
        "meta_country_iso": meta_country if len(meta_country) == 2 else None,
        "meta_city": (meta.get("city") or "").strip() or None,
        "store_name": (meta.get("name") or "").strip() or None,
        "money_format": (meta.get("money_format") or "").strip() or None,
        "currencies": currencies,
        "ships_to": ships_to,
        "ships_worldwide": ships_worldwide,
        "address_iso": _iso_from_html_address(html),
    }


def resolve_home_country(signals: dict, llm_iso: str = None) -> dict:
    """
    Signals + LLM inference ko mila kar brand ka HOME country tay karta hai.

    ── Tarteeb kyun aisi hai ────────────────────────────────────────────────
    Sawal ye NAHI hai ke "store kis currency mein bechta hai" — sawal ye hai
    ke "brand kahan ka hai". Ye do alag cheezein hain, aur mariab.pk ne
    farq saaf kar diya:

        ccTLD          .pk            -> Pakistan
        meta country   AE (Dubai)     -> UAE      (registered office)
        meta city      Dubai          -> UAE
        currency       PKR            -> Pakistan
        store name     "Maria.B. Designs (PK)"

    Registered office Dubai mein hona brand ko Emirati nahi bana deta.
    Isi tarah bohat se Pakistani brands foreign currency mein price karte
    hain taake international customers kharid saken — is liye currency
    home country ka kamzor signal hai.

    Priority:
      1. ccTLD  — sabse mazboot. .pk ek registry-backed geographic fact hai.
      2. LLM    — page content padh kar (about us, address, phone format).
                  .com jaise generic domains par yahi kaam aata hai.
      3. Currency — sirf tab jab upar wale dono khamosh hon.
      4. meta.json country — registered address, market nahi. Currency ke
         baad is liye ke Dubai-registered PK brands aam hain.
      5. HTML address text — aakhri sahara.
    """
    tld = signals.get("tld_iso")
    llm = (llm_iso or "").strip().upper() or None
    if llm and len(llm) != 2:
        llm = None

    currencies = signals.get("currencies") or []
    currency_iso = _iso_from_currency(currencies[0]) if currencies else None

    if tld and llm and tld == llm:
        iso, source, confidence = tld, "tld+llm", "high"
    elif tld:
        iso, source, confidence = tld, "tld", "high" if not llm else "medium"
    elif llm:
        iso, source, confidence = llm, "llm", "medium"
    elif currency_iso:
        iso, source, confidence = currency_iso, "currency", "medium"
    elif signals.get("meta_country_iso"):
        iso, source, confidence = signals["meta_country_iso"], "shopify_meta", "low"
    elif signals.get("address_iso"):
        iso, source, confidence = signals["address_iso"], "html_address", "low"
    else:
        iso, source, confidence = None, "none", "none"

    # Conflict hua to log karo — silent ghalat country hi asal bug tha.
    candidates = {
        "tld": tld, "llm": llm, "currency": currency_iso,
        "meta": signals.get("meta_country_iso"),
    }
    disagreeing = {k: v for k, v in candidates.items() if v and v != iso}
    if disagreeing:
        print(f"[locale] home country = {iso} (via {source}); other signals said {disagreeing}")

    return {
        "store_country": _iso_to_name(iso) or UNKNOWN_COUNTRY,
        "iso": iso,
        "source": source,
        "confidence": confidence,
        "conflicts": disagreeing,
    }


def resolve_markets(signals: dict, home_iso: str, llm_markets: list = None) -> list:
    """
    Wo saare mulk jahan ye store bechta hai — home country hamesha pehla.

    Part 3 (multi-market keywords) isi list par chalti hai: ek Pakistani
    brand jo UAE aur UK bhi ship karta hai use teeno markets ke keywords
    milne chahiye, sirf Pakistan ke nahi.
    """
    ordered = []

    def add(iso):
        iso = (iso or "").strip().upper()
        if len(iso) == 2 and iso not in ordered:
            ordered.append(iso)

    add(home_iso)
    for iso in (llm_markets or []):
        add(iso)
    # ships_to_countries — explicit country list (["*"] worldwide ignore hoti hai)
    for iso in signals.get("ships_to") or []:
        add(iso)
    # shipping policy page — sabse mazboot deterministic market signal
    for iso in signals.get("shipping_countries") or []:
        add(iso)
    # har accepted currency ek market ka pata deti hai
    for code in signals.get("currencies") or []:
        add(_iso_from_currency(code))

    return [{"iso": i, "name": _iso_to_name(i)} for i in ordered]


# ─────────────────────────────────────────────
#  PROMPT HELPERS  —  har LLM module yahin se padhta hai
# ─────────────────────────────────────────────

def _read(profile, field: str):
    """BrandProfile object ya plain dict, dono se field padh leta hai."""
    if profile is None:
        return None
    value = profile.get(field) if isinstance(profile, dict) else getattr(profile, field, None)
    if isinstance(value, str):
        value = value.strip()
    return value or None


def store_country(profile):
    """
    Prompt mein daalne layak country naam — ya None agar pata nahi.

    None ka matlab hai "country context bilkul chhor do", koi mulk maan lena
    nahi. Isi liye UNKNOWN_COUNTRY yahan None ban jata hai.
    """
    country = _read(profile, "store_country")
    if not country or country.lower() == UNKNOWN_COUNTRY:
        return None
    return country


def store_currency(profile):
    return _read(profile, "store_currency")


def store_currencies(profile) -> list:
    """
    Store jitni currencies leta hai, sab. Purane profiles par sirf
    store_currency hota hai, is liye us par fallback.
    """
    values = _read(profile, "store_currencies")
    if isinstance(values, list) and values:
        return [str(v).upper() for v in values if v]
    single = store_currency(profile)
    return [single] if single else []


def store_markets(profile) -> list:
    """
    Jin markets ke liye content banana hai — [{"iso","name"}, ...],
    home country hamesha pehla. Purane profiles par sirf home country.
    """
    values = _read(profile, "store_markets")
    if isinstance(values, list) and values:
        out = []
        for m in values:
            if isinstance(m, dict) and m.get("name"):
                out.append({"iso": m.get("iso"), "name": m["name"]})
            elif isinstance(m, str) and m.strip():
                out.append({"iso": None, "name": m.strip()})
        if out:
            return out
    home = store_country(profile)
    return [{"iso": None, "name": home}] if home else []


def market_suffix(profile) -> str:
    """
    Prompt ki pehli line mein lagne wala location phrase — " in the United
    States" ya khaali string.

    Suffix ki shakal is liye chuni gayi ke ye har jagah grammatically theek
    baithti hai, dono soorton mein:
        "You are an SEO expert for e-commerce stores in the United States."
        "You are an SEO expert for e-commerce stores."
    Pehle yahan ek mulk ka adjective hardcoded tha.
    """
    country = store_country(profile)
    return " in " + country if country else ""


def market_block(profile, audience_hint: bool = False) -> str:
    """
    Har prompt mein daalne wala market context block.

    Country maloom ho to LLM ko saaf batata hai kis market ke liye likhna hai.
    Maloom NA ho to ULTA instruction deta hai: koi mulk maan mat lo, product
    data se khud andaza lagao. Yehi wo behaviour hai jo ek US store ko kisi
    doosre mulk ke shehron wale keywords milne se bachata hai.
    """
    country = store_country(profile)
    currency = store_currency(profile)

    if not country:
        return (
            "STORE MARKET: not detected.\n"
            "- Do NOT assume any country. Never name a country, city, or region "
            "that you have not been given.\n"
            "- Infer the likely market from the product names, language, and "
            "pricing shown above, and otherwise keep the wording "
            "country-neutral and international."
        )

    currencies = store_currencies(profile) or ([currency] if currency else [])

    lines = ["STORE MARKET:", "- Home country: " + country + " (this is where the brand is FROM)"]
    if currencies:
        lines.append("- Currencies accepted: " + ", ".join(currencies))

    lines.append(
        "- The brand is " + country + "-based. " + country + " is the ONLY "
        "country you may ever name."
    )
    if _read(profile, "store_ships_worldwide"):
        # Pehle yahan secondary markets ki poori list jati thi aur likha hota
        # tha ke unhein "referenced" kiya ja sakta hai. Natija: ek Pakistani
        # brand ke product titles "...Set Dubai" ban gaye kyunke UAE us list
        # mein tha. Ships-to list shipping ki maloomat hai, content ka
        # subject nahi — is liye ab wo list kisi prompt mein nahi jati.
        lines.append(
            "- It ships to many countries, so keep the wording usable by "
            "international buyers."
        )
    lines.append(
        "- Do NOT name any other country. Do NOT name any city or region at "
        "all, not even in " + country + ". Never imply the brand belongs to "
        "another country, and never write copy aimed at one."
    )

    if audience_hint:
        lines.append(
            "- Describe the audience as shoppers of a " + country + "-based "
            "brand, using that country's own demonym. Do not name any city."
        )
    return "\n".join(lines)


def market_allocation(profile, total: int = 15) -> str:
    """
    Multi-market keyword allocation — Part 3.

    !! FILHAL KAHIN USE NAHI HO RAHA — aur soch samajh kar. Ye helper LLM ko
    kehta hai ke "country/city wording keyword ke ANDAR daalo", jo bilkul
    wahi behaviour hai jis se product content mein "Dubai" aaya tha. Isay
    kisi content/blog/ads prompt mein wapas jorhne se pehle tay karna hoga
    ke location kis surat mein allowed hai; warna secondary-market ke sheher
    dobara customer-facing copy mein aa jayenge.

    Ek international brand ke liye sirf home-country keywords banana SEO
    ki barbadi hai: Maria.B ke UAE customers "maria b abaya dubai" search
    karte hain, "maria b lawn Lahore" nahi. Ye helper LLM ko saaf batata hai
    kitne keywords kis market ke liye chahiye — home market ko sabse bara
    hissa, phir baqi.

    Ek hi market ho to koi allocation nahi, khali string (prompt saaf rehta hai).
    """
    markets = [m for m in store_markets(profile) if m.get("name")]
    if len(markets) < 2:
        return ""

    # Home ko ~40%, baqi barabar; koi bhi market 2 se kam na ho.
    secondary = markets[1:5]                      # 4 se zyada markets shor hai
    home_share = max(4, round(total * 0.4))
    general = 2
    per_secondary = max(2, (total - home_share - general) // len(secondary))

    lines = [
        "KEYWORD ALLOCATION ACROSS MARKETS:",
        f"- {home_share} keywords for {markets[0]['name']} (primary/home market)",
    ]
    used = home_share
    for m in secondary:
        lines.append(f"- {per_secondary} keywords for {m['name']}")
        used += per_secondary
    remaining = max(general, total - used)
    lines.append(f"- {remaining} general/international keywords with no country in them")
    lines.append(
        "- Put each keyword's country wording INSIDE the keyword itself "
        "(e.g. city or country name), so it actually targets that market."
    )
    return "\n".join(lines)


def currency_symbol(currency) -> str:
    """Currency code ka symbol — na mile to code khud."""
    if not currency:
        return ""
    code = currency.strip().upper()
    return CURRENCY_SYMBOLS.get(code, code)


def format_price(amount, currency=None):
    """
    Shopify variant price ko display string banata hai.

    Pehle extractor har product par ek hi currency symbol hardcode karta tha
    (`# default — can be enhanced`), to ek US store ke $17.99 wale products DB
    mein doosri currency ke ban jate the — aur wahi ghalat price ad copy aur
    blog prompts mein chala jata tha. Ab store ki apni currency lagti hai;
    currency maloom na ho to sirf raw amount (ghalat symbol se behtar hai).
    """
    if amount in (None, ""):
        return None
    symbol = currency_symbol(currency)
    return (symbol + " " + str(amount)).strip() if symbol else str(amount)
