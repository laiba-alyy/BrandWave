"""
ReviewPlatformService
----------------------
Fetches REAL customer reviews from Trustpilot.

Windows + FastAPI fix:
  FastAPI runs on asyncio (ProactorEventLoop on Windows).
  sync_playwright runs inside a ThreadPoolExecutor thread
  (outside the asyncio loop) so it works perfectly on Windows.

Speed optimization:
  Target 20 reviews (1-2 pages) instead of 80 (10 pages).
  20 reviews is more than enough for reliable SVM sentiment analysis.
  This reduces response time from ~120s to ~10-15s.
"""

import re
import time
import asyncio
import logging
import os
import random
from typing import List, Dict
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup
import requests

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/webp,*/*;q=0.8"
    ),
}

TLD_VARIANTS = [".com", ".pk", ".ae", ".store", ".co"]

# ── Optimized settings for fast demo-ready scraping ──────────────────────────
# Page 1 alone gives 15-20 reviews for most brands (e.g. Asim Jofa gave 16).
# Page 2 is kept as backup in case page 1 gives fewer than 10 reviews.
# This keeps total time at ~10-15 seconds instead of ~120 seconds.
MAX_REVIEW_PAGES      = int(os.getenv("TRUSTPILOT_MAX_PAGES",              "2"))
MAX_REVIEWS_PER_PAGE  = int(os.getenv("TRUSTPILOT_REVIEWS_PER_PAGE",       "20"))
REQUEST_DELAY_SECONDS = float(os.getenv("TRUSTPILOT_REQUEST_DELAY_SECONDS", "0.2"))
TARGET_REVIEW_COUNT   = int(os.getenv("TRUSTPILOT_TARGET_REVIEWS",         "20"))
PAGE_READY_TIMEOUT_MS = int(os.getenv("TRUSTPILOT_PAGE_READY_TIMEOUT_MS",  "4000"))
POST_LOAD_WAIT_MS     = int(os.getenv("TRUSTPILOT_POST_LOAD_WAIT_MS",      "500"))

# shared thread pool — max_workers=2 is enough since we scrape one brand at a time
_executor = ThreadPoolExecutor(max_workers=2)


# ── Windows Playwright fix ────────────────────────────────────────────────────

def _ensure_windows_playwright_policy() -> None:
    """
    Playwright launches a Node subprocess internally.
    On Windows, threads spawned from uvicorn's asyncio worker inherit
    SelectorEventLoop which does NOT support subprocess creation.
    Force WindowsProactorEventLoopPolicy so Playwright can start.
    """
    if os.name != "nt":
        return
    policy_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if policy_cls is None:
        return
    if not isinstance(asyncio.get_event_loop_policy(), policy_cls):
        asyncio.set_event_loop_policy(policy_cls())


# ── helpers ───────────────────────────────────────────────────────────────────

def extract_domain(website_url: str) -> str:
    """https://www.asimjofa.com  →  asimjofa.com"""
    parsed = urlparse(website_url.strip())
    netloc = parsed.netloc or parsed.path
    return netloc.replace("www.", "").strip("/")


def trustpilot_url_candidates(domain: str) -> List[str]:
    """
    Build prioritised Trustpilot URL list.
    Try the exact stored domain first, then common TLD variants
    (handles cases like mariab.pk vs mariab.ae on Trustpilot).
    """
    candidates = [f"https://www.trustpilot.com/review/{domain}"]
    base = re.split(r"\.(com|pk|ae|store|co|net|org)$", domain)[0]
    for tld in TLD_VARIANTS:
        alt = f"https://www.trustpilot.com/review/{base}{tld}"
        if alt not in candidates:
            candidates.append(alt)
    return candidates


def trustpilot_page_url(base_url: str, page_number: int) -> str:
    if page_number <= 1:
        return base_url
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}page={page_number}"


def parse_reviews_from_html(html: str, max_reviews: int = 20) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    tags = soup.find_all("p", attrs={"data-service-review-text-typography": True})
    if not tags:
        tags = soup.select("p[class*='typography_body']")
    texts = [t.get_text(strip=True) for t in tags]
    return [t for t in texts if len(t) > 15][:max_reviews]


# ── primary scraper (Playwright in thread) ────────────────────────────────────

def _scrape_in_thread(domain: str) -> List[str]:
    """
    Sync Playwright scraper — runs in a ThreadPoolExecutor worker
    so it stays outside the asyncio event loop (Windows-safe).
    """
    _ensure_windows_playwright_policy()
    from playwright.sync_api import sync_playwright

    candidates        = trustpilot_url_candidates(domain)
    collected_reviews: List[str] = []
    seen_reviews      = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="en-US",
            viewport={"width": 1280, "height": 800},
            extra_http_headers=BROWSER_HEADERS,
        )
        page = context.new_page()

        for base_url in candidates:
            logger.info(f"[scraper] Trying domain variant: {base_url}")
            reviews_before = len(collected_reviews)

            for page_number in range(1, MAX_REVIEW_PAGES + 1):

                # stop early if we already have enough reviews
                if len(collected_reviews) >= TARGET_REVIEW_COUNT:
                    logger.info(f"[scraper] Target reached ({TARGET_REVIEW_COUNT}), stopping")
                    break

                url = trustpilot_page_url(base_url, page_number)
                logger.info(f"[scraper] Page {page_number}: {url}")

                try:
                    page.goto(url, timeout=18000, wait_until="domcontentloaded")
                    page.wait_for_selector(
                        "p[data-service-review-text-typography], p[class*='typography_body']",
                        timeout=PAGE_READY_TIMEOUT_MS,
                    )
                except Exception as e:
                    logger.debug(f"[scraper] Nav/selector error on {url}: {e}")
                    time.sleep(REQUEST_DELAY_SECONDS)
                    continue

                # short post-load wait so dynamic content renders
                page.wait_for_timeout(int(POST_LOAD_WAIT_MS + random.random() * 150))
                html = page.content()

                if not html or "Page not found" in html:
                    time.sleep(REQUEST_DELAY_SECONDS)
                    continue
                if "TrustScore" not in html and "Categories" not in html:
                    # not a real Trustpilot company page
                    time.sleep(REQUEST_DELAY_SECONDS)
                    continue

                page_reviews = parse_reviews_from_html(html, max_reviews=MAX_REVIEWS_PER_PAGE)
                new_count = 0
                for text in page_reviews:
                    if text not in seen_reviews:
                        seen_reviews.add(text)
                        collected_reviews.append(text)
                        new_count += 1

                logger.info(
                    f"[scraper] +{new_count} new reviews on page {page_number} "
                    f"(total so far: {len(collected_reviews)})"
                )

                # no new reviews on this page → no point going to next page
                if new_count == 0:
                    logger.info("[scraper] No new reviews, stopping pagination")
                    break

                if len(collected_reviews) >= TARGET_REVIEW_COUNT:
                    break

                time.sleep(REQUEST_DELAY_SECONDS)

            # if we got reviews from this domain variant, stop trying others
            if len(collected_reviews) > reviews_before:
                break

        browser.close()

    return collected_reviews


# ── fallback scraper (plain HTTP, no browser) ─────────────────────────────────

def _scrape_with_http(domain: str) -> List[str]:
    """
    Lightweight fallback — used only if Playwright fails to start.
    Plain HTTP requests work on some Trustpilot pages that are
    not protected by Cloudflare JS challenge.
    """
    candidates        = trustpilot_url_candidates(domain)
    collected_reviews: List[str] = []
    seen_reviews      = set()

    for base_url in candidates:
        reviews_before = len(collected_reviews)

        for page_number in range(1, MAX_REVIEW_PAGES + 1):
            if len(collected_reviews) >= TARGET_REVIEW_COUNT:
                break

            url = trustpilot_page_url(base_url, page_number)
            logger.info(f"[http-fallback] {url}")

            try:
                resp = requests.get(
                    url,
                    headers={"User-Agent": USER_AGENT, **BROWSER_HEADERS},
                    timeout=15,
                )
            except Exception as e:
                logger.debug(f"[http-fallback] Request error: {e}")
                time.sleep(REQUEST_DELAY_SECONDS)
                continue

            if resp.status_code >= 400 or not resp.text:
                time.sleep(REQUEST_DELAY_SECONDS)
                continue
            if "Page not found" in resp.text:
                time.sleep(REQUEST_DELAY_SECONDS)
                continue

            page_reviews = parse_reviews_from_html(resp.text, max_reviews=MAX_REVIEWS_PER_PAGE)
            new_count = 0
            for text in page_reviews:
                if text not in seen_reviews:
                    seen_reviews.add(text)
                    collected_reviews.append(text)
                    new_count += 1

            logger.info(f"[http-fallback] +{new_count} reviews (total: {len(collected_reviews)})")

            if new_count == 0:
                break

            time.sleep(REQUEST_DELAY_SECONDS)

        if len(collected_reviews) > reviews_before:
            break

    return collected_reviews


# ── service class (async wrapper) ─────────────────────────────────────────────

class ReviewPlatformService:

    async def fetch_trustpilot_reviews(self, website_url: str) -> List[Dict]:
        """
        Async entry point — called from routes.py with `await`.
        Runs the sync Playwright scraper in a thread pool so the
        asyncio event loop is never blocked (and Windows works fine).
        Falls back to plain HTTP if Playwright cannot start.
        """
        domain = extract_domain(website_url)
        logger.info(f"Fetching Trustpilot reviews | domain: {domain}")

        loop = asyncio.get_running_loop()

        try:
            raw_texts: List[str] = await loop.run_in_executor(
                _executor, _scrape_in_thread, domain
            )
        except Exception as e:
            logger.warning(f"Playwright failed for {domain}: {e} — trying HTTP fallback")
            raw_texts = await loop.run_in_executor(
                _executor, _scrape_with_http, domain
            )

        if not raw_texts:
            logger.warning(f"No reviews found for {domain}")
            return []

        reviews = [
            {
                "content":  text,
                "source":   "trustpilot",
                "platform": "trustpilot",
                "is_real":  True,
            }
            for text in raw_texts
        ]

        logger.info(f"Returning {len(reviews)} reviews for {domain}")
        return reviews

    async def search_all_platforms(self, website_url: str) -> Dict:
        """Backward-compatibility wrapper."""
        reviews = await self.fetch_trustpilot_reviews(website_url)
        return {
            "trustpilot":  reviews,
            "total":       len(reviews),
            "by_platform": {"trustpilot": len(reviews)},
        }