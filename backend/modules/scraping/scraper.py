import asyncio
import re
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from sqlalchemy.orm import Session
from sqlalchemy import cast, String
from urllib.parse import urlparse
import httpx
import logging

logging.basicConfig(level=logging.INFO)

from modules.scraping.extractor import (
    extract_basic_info,
    extract_contacts,
    extract_social_links,
    find_contact_page,
    extract_product_links,
    extract_products_from_page,
    extract_shopify_products,
    detect_platform,
)
from modules.scraping.cleaner import (
    clean_and_extract_business_info,
    infer_home_country,
    infer_target_audience,
    detect_product_category,
    detect_price_range,
    get_unique_categories_from_products,
)
from modules.scraping.verifier import check_robots_txt, verify_shopify_store
from modules.store_locale import (
    collect_locale_signals,
    resolve_home_country,
    resolve_markets,
)
from models.brand_profile import BrandProfile


async def scrape_website(website_url: str, user_id: str, db: Session, progress_callback=None) -> dict:
    """Main scraping function — Shopify only"""

    async def update_progress(stage: str, percent: int):
        if progress_callback:
            await progress_callback(stage, percent)
        print(f"[{percent}%] {stage}")

    website_url = normalize_store_url(website_url)

    print(f"🔍 Scraping started: {website_url}")

    # ── EVENT LOOP KO BLOCK MAT KARO ────────────────────────────────────────
    # Is function ke andar ka zyadatar kaam SYNC hai (requests, torch nahi par
    # bhaari HTTP + LLM calls). Ye `async def` hai aur ise ek async route se
    # await kiya jata hai, is liye har sync call POORE server ko rok deti thi:
    # measure kiya gaya — 131 products wale chhote store ke scrape ke doran ek
    # khali /health request 0.87s se 15.87s ho gayi thi (18x).
    #
    # Har blocking call ab `asyncio.to_thread` mein jati hai. Loop azad rehta
    # hai, progress WebSocket chalti rehti hai, aur baaqi requests normal
    # raftaar se chalti rehti hain.

    # Step 1: robots.txt check
    if not await asyncio.to_thread(check_robots_txt, website_url):
        raise Exception("Website scraping is not allowed by robots.txt")

    # Step 2: Shopify verification
    await update_progress("Verifying Shopify store...", 10)
    is_shopify = await asyncio.to_thread(verify_shopify_store, website_url)
    if not is_shopify:
        raise Exception(
            "This URL does not appear to be a Shopify store. "
            "BrandWave currently supports Shopify stores only."
        )

    # Step 3: Page fetch
    await update_progress("Website Loaded", 25)
    html_content = await fetch_page(website_url)
    if not html_content:
        raise Exception("Could not fetch website content")

    soup = BeautifulSoup(html_content, "html.parser")
    print("✅ Page fetched successfully")

    # Step 4: Platform detection — double check
    platform = detect_platform(html_content, soup, website_url)
    print(f"🏭 Platform: {platform}")

    # Step 5: Basic info + social links
    raw_text = extract_raw_text(soup)
    basic_info = extract_basic_info(soup, website_url)
    social_links = extract_social_links(soup)
    contacts = extract_contacts(soup)
    print(f"✅ Basic info: {basic_info.get('business_name')}")

    # ── Contact page — sirf zaroorat par ─────────────────────────────────
    #
    # Bohat se stores footer mein social icons rakhte hi nahi; wahan sirf
    # "Contact Us" ka link hota hai aur asal icons/email us page par hote
    # hain. Home page se haar maan lene ka matlab un brands ke links kabhi na
    # milna.
    #
    # Ye poora crawl NAHI — sirf EK extra request, aur wo bhi tab jab home
    # page se social links ya email mila hi na ho.
    #
    # try POORE block par hai, sirf fetch par nahi. Wajah: find_contact_page()
    # har anchor ke href par urlparse() chalata hai, aur urlparse kharab URL
    # (misal "http://[::1") par ValueError phenkta hai — yani kisi store ke
    # footer ka EK gharab link poora scrape gira sakta tha. Ye step ek behtari
    # hai, scrape ki shart nahi: kuch bhi ghalat ho to chhoR kar aage.
    try:
        if not social_links or not contacts.get("contact_email"):
            contact_url = find_contact_page(soup, website_url)
            if contact_url:
                print(f"🔎 Social/contact info adhoori — contact page dekh rahe hain: {contact_url}")
                contact_html = await fetch_page(contact_url)
                if contact_html:
                    contact_soup = BeautifulSoup(contact_html, "html.parser")
                    # Home page ki value ko tarjeeh — wo brand ka apna footer
                    # hai; contact page par kabhi partner/agency ke links bhi
                    # hote hain.
                    # NOTE: loop variable ka naam `platform` NAHI — wo upar
                    # detect_platform() ka natija hai aur aage DB mein jata
                    # hai. Yahan use dobara bind karne se store ka platform
                    # "Shopify" se badal kar "youtube" save ho jata.
                    for network, href in extract_social_links(contact_soup).items():
                        social_links.setdefault(network, href)
                    for field, value in extract_contacts(contact_soup).items():
                        if value and not contacts.get(field):
                            contacts[field] = value
                    print(f"✅ Contact page se: {len(social_links)} social, "
                          f"email={'haan' if contacts.get('contact_email') else 'nahi'}")
    except Exception as e:  # noqa: BLE001 — dekho upar wali wajah
        # contact_url ko yahan mat chhapo: agar find_contact_page hi gira to wo
        # bandha hi nahi gaya hoga aur ye line khud NameError de degi.
        print(f"⚠️ Contact page step chhoR diya: {type(e).__name__}: {e}")

    # Step 5b: Market detection — HAR LLM call se PEHLE
    #
    # Country/currency yahan ek hi baar nikalte hain aur aage har prompt
    # (scraping, SEO keywords, blog, ad copy, chatbot) isi ko padhta hai.
    #
    # Do marhale: pehle deterministic signals (TLD, meta.json, currencies,
    # shipping), phir LLM page padh kar home country batata hai. Faisla
    # resolve_home_country() karta hai — TLD aur LLM ko currency par tarjeeh
    # deta hai, kyunke bohat se brands foreign currency mein price karte hain.
    signals = await asyncio.to_thread(collect_locale_signals, website_url, html_content)
    llm_country = await asyncio.to_thread(
        infer_home_country, raw_text, website_url, signals
    )
    home = resolve_home_country(signals, llm_country.get("iso"))
    markets = resolve_markets(signals, home["iso"], llm_country.get("also_sells_to"))
    currencies = signals.get("currencies") or []

    locale = {
        "store_country": home["store_country"],
        "store_currency": currencies[0] if currencies else None,
        "store_currencies": currencies,
        "store_markets": markets,
        "store_ships_worldwide": bool(signals.get("ships_worldwide")),
        "source": home["source"],
    }
    print(
        f"🌍 Home country: {locale['store_country']} "
        f"(via {home['source']}, {home['confidence']} confidence)"
    )
    print(f"💱 Currencies: {currencies or ['unknown']}")
    print(f"🗺️  Markets: {[m['name'] for m in markets] or ['unknown']}")

    # Step 6: Products via Shopify API
    await update_progress("Content Extracted", 50)
    print("🛍️ Fetching products via Shopify API...")
    raw_products = await asyncio.to_thread(
        extract_shopify_products, website_url, currency=locale["store_currency"]
    )

    # Deduplicate by Shopify product id — name par dedupe karna galat tha, kyunke
    # bohat se stores alag-alag products ko same title dete hain (e.g. article
    # code same, colour alag), jo silently drop ho jate the.
    seen = set()
    unique_products = []
    for p in raw_products:
        key = p.get("id") or (p.get("name") or "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique_products.append(p)

    print(f"✅ Unique products: {len(unique_products)}")

    # Step 7: Category detection per product — no LLM
    for p in unique_products:
        # product_type pehle — `category` us waqt tak wahi hoti hai, magar
        # re-classification par (jab category pehle se badli ja chuki ho)
        # sirf product_type hi asli source hota hai.
        raw_category = (p.get("product_type") or p.get("category") or "").strip()
        p["category"] = detect_product_category(
            name=p.get("name", ""),
            product_type=raw_category,
            tags=p.get("tags", [])
        )

    # Step 8: LLM — business info + audience (2 calls only)
    await update_progress("Brand Analysis", 75)
    print("🤖 LLM analyzing business info...")
    llm_business_info = await asyncio.to_thread(
        clean_and_extract_business_info, raw_text, website_url, locale
    )

    business_name = llm_business_info.get("business_name") or basic_info.get("business_name")
    description = llm_business_info.get("description") or basic_info.get("description")
    business_type = llm_business_info.get("business_type")
    price_range = detect_price_range(unique_products)

    # Combine LLM categories + keyword-detected categories from products
    # This ensures no category is missed even if LLM overlooks it
    llm_categories = llm_business_info.get("product_categories") or []
    detected_categories = get_unique_categories_from_products(unique_products)
    product_categories = list(set(llm_categories + detected_categories))
    print(f"✅ LLM categories: {llm_categories}")
    print(f"✅ Detected categories: {detected_categories}")
    print(f"✅ Final categories: {product_categories}")

    # Ye bhi ek LLM call hai (cleaner.py:469) — thread mein.
    target_audience = await asyncio.to_thread(
        infer_target_audience, llm_business_info, unique_products, locale
    )

    print(f"✅ Business: {business_name}")
    print(f"✅ Products: {len(unique_products)}")
    print(f"✅ Price range: {price_range}")
    print(f"✅ Audience: {target_audience}")

    # Step 9: Save to DB
    # 7,168 products ka JSON ~9 MB hai; wo insert bhi loop rok deta tha.
    await update_progress("Profile Ready", 100)
    brand_profile = await asyncio.to_thread(
        save_brand_profile,
        db=db,
        user_id=user_id,
        website_url=website_url,
        business_name=business_name,
        description=description,
        products=unique_products,
        brand_colors=[],
        logo_url=None,
        social_links=social_links,
        contact_email=contacts.get("contact_email") or None,
        contact_phone=contacts.get("contact_phone") or None,
        target_audience=target_audience,
        platform=platform,
        product_categories=product_categories,
        business_type=business_type,
        price_range=price_range,
        store_country=locale["store_country"],
        store_currency=locale["store_currency"],
        store_currencies=locale["store_currencies"],
        store_markets=locale["store_markets"],
        store_ships_worldwide=locale["store_ships_worldwide"],
    )

    print(f"✅ Saved! ID: {brand_profile.id}")

    return {
        "id": brand_profile.id,
        "business_name": business_name,
        "description": description,
        "products": unique_products,
        "brand_colors": [],
        "logo_url": None,
        "social_links": social_links,
        "contact_email": contacts.get("contact_email") or None,
        "contact_phone": contacts.get("contact_phone") or None,
        "target_audience": target_audience,
        "website_url": website_url,
        "platform": platform,
        "product_categories": product_categories,
        "business_type": business_type,
        "price_range": price_range,
        "store_country": brand_profile.store_country,
        "store_currency": locale["store_currency"],
        "store_currencies": locale["store_currencies"],
        "store_markets": locale["store_markets"],
        "store_ships_worldwide": locale["store_ships_worldwide"],
        "store_country_source": brand_profile.store_country_source,
    }


async def fetch_page(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        async with httpx.AsyncClient(
            timeout=15,
            headers=headers,
            follow_redirects=True
        ) as client:
            response = await client.get(url)
            if response.status_code == 200:
                html = response.text
                if _needs_js_rendering(html):
                    print(f"🎭 JS rendering needed → Playwright: {url}")
                    playwright_html = await fetch_with_playwright(url)
                    return playwright_html or html
                return html

    except Exception as e:
        print(f"httpx failed: {e}")

    return await fetch_with_playwright(url)


def _needs_js_rendering(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    body_text = soup.get_text(strip=True)

    if len(body_text) < 500:
        return True
    if re.search(r'<div id=["\']root["\']>\s*</div>', html):
        return True
    if re.search(r'<div id=["\']app["\']>\s*</div>', html):
        return True

    return False


async def fetch_with_playwright(url: str) -> str:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = await context.new_page()
            page.on("pageerror", lambda err: None)
            page.on("requestfailed", lambda req: None)

            await page.goto(url, timeout=40000, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            await page.evaluate("""
                async () => {
                    await new Promise((resolve) => {
                        let totalHeight = 0;
                        const distance = 400;
                        const timer = setInterval(() => {
                            window.scrollBy(0, distance);
                            totalHeight += distance;
                            if (totalHeight >= 3000) {
                                clearInterval(timer);
                                resolve();
                            }
                        }, 150);
                    });
                }
            """)

            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)

            content = await page.content()
            await context.close()
            await browser.close()
            return content

    except Exception as e:
        print(f"Playwright error: {e}")
        return None


def extract_raw_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "nav", "footer", "head"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r'\s+', ' ', text)
    return text[:4000]


def normalize_store_url(url: str) -> str:
    """
    Ek store ka EK canonical URL.

    Pehle dedup exact string match par tha, is liye ye sab alag alag "brands"
    ban jate the:

        https://www.asimjofa.com
        https://asimjofa.com
        https://www.asimjofa.com/
        HTTPS://WWW.AsimJofa.com

    Asar sirf switcher mein duplicate dikhne tak mehdood nahi tha: har module
    brand_profile_id par scope karta hai, to id 4 par chalaya gaya SEO audit
    id 5 par ghayab lagta tha.

    Rules — sirf wo jo hamesha mehfooz hain:
      * scheme na ho to https
      * scheme aur host lowercase (path case-sensitive ho sakta hai)
      * leading "www."
      * trailing slash
      * default port (:80 / :443)

    Query string aur path chhera nahi jata — Shopify stores hamesha root par
    hote hain, lekin kisi ne path diya hai to usay chupke se badalna ghalat hoga.
    """
    value = (url or "").strip()
    if not value:
        return value
    if not re.match(r"^https?://", value, re.IGNORECASE):
        value = "https://" + value

    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    # Non-default port ho to rakh lo.
    if parsed.port and parsed.port not in (80, 443):
        host = f"{host}:{parsed.port}"

    path = (parsed.path or "").rstrip("/")
    scheme = (parsed.scheme or "https").lower()
    rebuilt = f"{scheme}://{host}{path}"
    if parsed.query:
        rebuilt += f"?{parsed.query}"
    return rebuilt


def save_brand_profile(db: Session, **kwargs) -> BrandProfile:
    # Canonical URL par hi dedup — dekho normalize_store_url().
    kwargs["website_url"] = normalize_store_url(kwargs["website_url"])

    existing = db.query(BrandProfile).filter(
        BrandProfile.user_id == kwargs["user_id"],
        BrandProfile.website_url == kwargs["website_url"]
    ).first()

    # Purane rows normalize hone se PEHLE save hue the (www./trailing slash ke
    # sath). Un ke against bhi match karo, warna pehla rescrape ek NAYA
    # duplicate bana dega — bilkul wahi bug jo ye function theek kar raha hai.
    if not existing:
        existing = next(
            (
                row
                for row in db.query(BrandProfile).filter(
                    BrandProfile.user_id == kwargs["user_id"]
                ).all()
                if normalize_store_url(row.website_url or "") == kwargs["website_url"]
            ),
            None,
        )
        if existing:
            print(
                f"🔗 Matched legacy profile {existing.id} "
                f"({existing.website_url!r}) — canonicalising"
            )

    if existing:
        # User ne country khud theek ki hai to rescrape use CHHUEGA NAHI.
        # Warna har rescrape uski correction chup-chaap wapas auto-detected
        # (ghalat) value par le jata — bilkul wahi bug jo Maria.B par mila.
        if (existing.store_country_source or "auto") == "manual":
            kwargs.pop("store_country", None)
            print(f"🔒 store_country is user-set ({existing.store_country}) — keeping it")

        # Wahi usool social links par. User ne khud bhare hon to rescrape
        # unhe overwrite nahi karta — warna profile page par bhari hui links
        # agle rescrape par chup-chaap ud jatin, aur scraping har site par
        # social links theek nikal bhi nahi pati.
        if (existing.social_links_source or "auto") == "manual":
            kwargs.pop("social_links", None)
            print(f"🔒 social_links are user-set "
                  f"({len(existing.social_links or {})} links) — keeping them")

        for key, value in kwargs.items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing
    kwargs.setdefault("store_country_source", "auto")
    profile = BrandProfile(**kwargs)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile