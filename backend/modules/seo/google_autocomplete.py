import requests
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict


def get_google_suggestions(keyword: str, country: str = "pk") -> List[str]:
    """
    Google Autocomplete se real suggestions lo
    Yeh woh keywords hain jo log actually search karte hain
    """
    try:
        url = "http://suggestqueries.google.com/complete/search"
        params = {
            "client": "firefox",
            "q": keyword,
            "hl": "en",
            "gl": country.lower()[:2] if country else "pk"
        }
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data[1] if len(data) > 1 else []
    except Exception:
        pass
    return []


# Ek waqt mein kitni keywords validate karni hain.
#
# Pehle ye loop BILKUL sequential tha, aur har keyword se pehle 0.2s ka sleep
# bhi tha. 30 candidates × (0.2s sleep + 1-4 HTTP round trips) = ~30 second,
# jo poori keyword generation ka sab se bara hissa tha.
#
# Har keyword ki validation doosri se bilkul mustaqil hai, is liye inhein
# parallel chalana bilkul mehfooz hai. 8 par latency ~30s se ~4s ho jati hai
# aur Google ka public autocomplete endpoint is load par aaram se chalta hai.
# Isse zyada barhane ka faida kam aur throttle hone ka khatra zyada hai.
# Google Autocomplete keyword generation ka SAB SE BARA hissa hai — LLM 4.6s
# leta hai, ye 9.2s (measured, 51 candidates, 12 workers).
#
# Har candidate ke liye pehli request poora phrase check karti hai aur usi par
# ~96% validate ho jate hain (49/51 measured), yani requests ~= candidates.
# Matlab ye kaam network-latency-bound hai, CPU ya Google ki taraf se throttle
# ki wajah se nahi — workers barhana seedha waqt kam karta hai.
#
# 51 candidates / 24 workers = ~2 batches, 12 workers par ~5 the.
# Ye chhoti, unauthenticated GET requests hain aur nakaam hone par keyword
# sirf "unvalidated" ho jata hai (crash nahi), is liye ye mehfooz hai.
_VALIDATION_WORKERS = int(os.getenv("SEO_AUTOCOMPLETE_WORKERS", "24"))


def _validate_one(keyword: str, country: str) -> Dict:
    """Ek keyword ki validation — pehle poora phrase, phir core words."""
    core_words = _extract_core_words(keyword)

    is_validated = False
    matched_suggestion = ""
    all_suggestions: List[str] = []

    # Full keyword try karo
    suggestions = get_google_suggestions(keyword, country)
    all_suggestions = suggestions
    match = _check_match(keyword, suggestions)
    if match:
        is_validated = True
        matched_suggestion = match

    # Core words try karo agar full match nahi mila
    if not is_validated and core_words:
        core_query = " ".join(core_words[:3])
        suggestions = get_google_suggestions(core_query, country)
        all_suggestions = suggestions
        match = _check_match(keyword, suggestions)
        if match:
            is_validated = True
            matched_suggestion = match

    # Single core word try karo agar ab bhi nahi mila
    if not is_validated and core_words:
        for word in core_words[:2]:
            suggestions = get_google_suggestions(word, country)
            match = _check_match(keyword, suggestions)
            if match:
                is_validated = True
                matched_suggestion = match
                all_suggestions = suggestions
                break

    return {
        "keyword": keyword,
        "google_validated": is_validated,
        "matched_suggestion": matched_suggestion,
        "suggestions_found": len(all_suggestions),
    }


def validate_keywords_with_autocomplete(
    candidates: List[str],
    country: str = "pk"
) -> List[Dict]:
    """
    Har candidate keyword ko Google Autocomplete se validate karo.
    Agar Google suggest karta hai = real keyword.

    Candidates parallel mein jate hain (dekho _VALIDATION_WORKERS), magar
    natija HAMESHA usi tarteeb mein wapas aata hai jis mein candidates aaye
    the — caller isi tarteeb par bharosa karta hai.
    """
    if not candidates:
        return []

    workers = min(_VALIDATION_WORKERS, len(candidates))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_validate_one, kw, country): i
            for i, kw in enumerate(candidates)
        }
        results: List[Dict | None] = [None] * len(candidates)
        for future in as_completed(futures):
            i = futures[future]
            try:
                results[i] = future.result()
            except Exception:
                # Ek keyword ki nakami baaqi sab ko na girae — usay
                # "validate nahi hua" maan lo, jo pehle wala behaviour hai.
                results[i] = {
                    "keyword": candidates[i],
                    "google_validated": False,
                    "matched_suggestion": "",
                    "suggestions_found": 0,
                }

    return [r for r in results if r is not None]


def _extract_core_words(keyword: str) -> List[str]:
    """
    Keyword se filler words hatao, sirf important words rakho
    """
    filler_words = {
        "buy", "shop", "order", "purchase", "get", "find",
        "online", "price", "best", "top", "new", "cheap",
        "for", "the", "a", "an", "in", "on", "with", "and",
        "of", "to", "from", "by", "set", "piece"
    }
    words = keyword.lower().split()
    return [w for w in words if w not in filler_words and len(w) > 2]


def _check_match(keyword: str, suggestions: List[str]) -> str:
    """
    Keyword aur suggestions mein overlap check karo
    Returns matched suggestion or empty string
    """
    if not suggestions:
        return ""

    keyword_lower = keyword.lower().strip()
    keyword_words = set(keyword_lower.split())

    for suggestion in suggestions:
        suggestion_lower = suggestion.lower().strip()
        suggestion_words = set(suggestion_lower.split())

        # Exact match
        if keyword_lower == suggestion_lower:
            return suggestion

        # Substring match
        if keyword_lower in suggestion_lower or suggestion_lower in keyword_lower:
            return suggestion

        # Word overlap — agar 60% words match karein
        if len(keyword_words) >= 2:
            common = keyword_words & suggestion_words
            overlap = len(common) / min(len(keyword_words), len(suggestion_words))
            if overlap >= 0.6:
                return suggestion

        # Singular/plural match — "suit" vs "suits"
        keyword_stems = {w.rstrip("s") for w in keyword_words}
        suggestion_stems = {w.rstrip("s") for w in suggestion_words}
        common_stems = keyword_stems & suggestion_stems
        if len(keyword_words) >= 2:
            stem_overlap = len(common_stems) / min(len(keyword_stems), len(suggestion_stems))
            if stem_overlap >= 0.6:
                return suggestion

    return ""


def discover_keywords_from_seeds(
    seeds: List[str],
    country: str = "pk"
) -> List[str]:
    """
    Seeds se Google Autocomplete ke through naye keywords discover karo
    Yeh LLM se alag hain — yeh REAL search queries hain
    """
    discovered = set()

    for seed in seeds[:10]:
        time.sleep(0.3)
        suggestions = get_google_suggestions(seed, country)
        for s in suggestions:
            discovered.add(s.lower().strip())

        # Alphabet expansion — "lawn suit a", "lawn suit b" etc
        for letter in "abcdefghijklmnop":
            time.sleep(0.2)
            expanded = get_google_suggestions(f"{seed} {letter}", country)
            for s in expanded:
                discovered.add(s.lower().strip())

    return list(discovered)